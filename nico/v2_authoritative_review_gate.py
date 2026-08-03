from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from pypdf import PdfReader

from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status
from nico.client_text_status_sanitizer_v1 import sanitize_client_text_status
from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_STATUS,
    DELIVERY_STATUS,
    EN_BOUNDARY,
    ES_BOUNDARY,
    REPORT_FINALITY,
    apply_automated_draft_truth,
)

VERSION = "nico.v2.authoritative-review-gate.v4"
_MARKER = "__nico_authoritative_review_gate_v4__"
_PROJECT_MARKER = "__nico_authoritative_review_projection_v4__"
_HTML_MARKER = "__nico_authoritative_review_html_v4__"
_PDF_MARKER = "__nico_authoritative_review_pdf_v4__"
_REBUILD_MARKER = "__nico_authoritative_review_rebuild_v4__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _is_spanish(canonical: Mapping[str, Any], explicit: bool) -> bool:
    if explicit:
        return True
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or identity.get("report_language")
    ).casefold()
    return language.startswith("es")


def _sanitize_status_text(value: str) -> str:
    return (
        sanitize_client_text_status(value)
        .replace(
            "INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
            "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
        )
        .replace(
            "INFORME FINAL · APROBACIÓN PENDIENTE",
            "BORRADOR AUTOMATIZADO · APROBACIÓN PENDIENTE",
        )
        .replace(
            "FINAL PENDING APPROVAL",
            "AUTOMATED DRAFT PENDING APPROVAL",
        )
    )


def authoritative_review_gate_markdown(*, spanish: bool) -> str:
    if spanish:
        return "\n".join(
            [
                "## Puerta de revisión humana y aceptación",
                "",
                ES_BOUNDARY,
                "",
                "El borrador automatizado está completo como paquete de revisión, pero no está aprobado para entrega.",
                "",
                "- Estado automatizado: Completo.",
                "- Revisión humana: Obligatoria antes de cualquier entrega al cliente.",
                "- Aceptación: Pendiente para el paquete inmutable exacto.",
                "- Entrega al cliente: Bloqueada hasta la aprobación explícita.",
                "- Responsabilidad del revisor: Confirmar identidad, puntuación, evidencia, limitaciones, hallazgos y plan de remediación.",
                "- Cambio de estado permitido: Solo un revisor autorizado puede aprobar el paquete exacto y autorizar la entrega al cliente.",
            ]
        )
    return "\n".join(
        [
            "## Human Review and Acceptance Gate",
            "",
            EN_BOUNDARY,
            "",
            "The automated draft is complete as a review package, but it is not approved for delivery.",
            "",
            "- Automated status: Complete.",
            "- Human review: Required before any client delivery.",
            "- Acceptance: Pending for the exact immutable package.",
            "- Client delivery: Blocked until explicit approval.",
            "- Reviewer responsibility: Confirm identity, scores, evidence, limitations, findings, and remediation plan.",
            "- Permitted state change: Only an authorized reviewer may approve the exact package and authorize client delivery.",
        ]
    )


def ensure_authoritative_review_gate(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    localized = _is_spanish(canonical, spanish)
    heading = (
        "## Puerta de revisión humana y aceptación"
        if localized
        else "## Human Review and Acceptance Gate"
    )
    if heading in markdown:
        return markdown
    gate = authoritative_review_gate_markdown(spanish=localized)
    for marker in (
        "## Puerta de revisión y entrega",
        "## Delivery Status",
        "## Review and Delivery Gate",
    ):
        if marker in markdown:
            return markdown.replace(marker, f"{gate}\n\n{marker}", 1)
    return markdown.rstrip() + "\n\n" + gate + "\n"


def install_authoritative_review_gate() -> dict[str, Any]:
    from nico import v2_authoritative_premium_report as report

    current_clean: Callable[..., str] = report._clean_markdown
    if not getattr(current_clean, _MARKER, False):

        @wraps(current_clean)
        def clean_wrapped(
            markdown: str,
            canonical: Mapping[str, Any],
            *,
            spanish: bool,
        ) -> str:
            cleaned = _sanitize_status_text(
                current_clean(markdown, canonical, spanish=spanish)
            )
            return ensure_authoritative_review_gate(
                cleaned,
                canonical,
                spanish=spanish,
            )

        setattr(clean_wrapped, _MARKER, True)
        setattr(clean_wrapped, "_nico_previous", current_clean)
        report._clean_markdown = clean_wrapped

    current_project = report.project_authoritative_canonical
    if not getattr(current_project, _PROJECT_MARKER, False):

        @wraps(current_project)
        def project_wrapped(value: Mapping[str, Any]) -> dict[str, Any]:
            return apply_automated_draft_truth(current_project(value))

        setattr(project_wrapped, _PROJECT_MARKER, True)
        setattr(project_wrapped, "_nico_previous", current_project)
        report.project_authoritative_canonical = project_wrapped

    current_html = report._html_from_markdown
    if not getattr(current_html, _HTML_MARKER, False):

        @wraps(current_html)
        def html_wrapped(
            markdown: str,
            title: str,
            *,
            spanish: bool,
        ) -> str:
            return _sanitize_status_text(
                current_html(markdown, title, spanish=spanish)
            )

        setattr(html_wrapped, _HTML_MARKER, True)
        setattr(html_wrapped, "_nico_previous", current_html)
        report._html_from_markdown = html_wrapped

    current_pdf = report._pdf_from_markdown
    if not getattr(current_pdf, _PDF_MARKER, False):

        @wraps(current_pdf)
        def pdf_wrapped(
            markdown: str,
            canonical: Mapping[str, Any],
            *,
            spanish: bool,
        ) -> tuple[bytes, int]:
            pdf, _ = current_pdf(markdown, canonical, spanish=spanish)
            sanitized = sanitize_client_pdf_status(pdf)
            return sanitized, len(PdfReader(io.BytesIO(sanitized)).pages)

        setattr(pdf_wrapped, _PDF_MARKER, True)
        setattr(pdf_wrapped, "_nico_previous", current_pdf)
        report._pdf_from_markdown = pdf_wrapped

    current_rebuild = report.rebuild_authoritative_premium_artifacts
    if not getattr(current_rebuild, _REBUILD_MARKER, False):

        @wraps(current_rebuild)
        def rebuild_wrapped(package: Mapping[str, Any]) -> dict[str, Any]:
            result = deepcopy(current_rebuild(package))
            canonical = apply_automated_draft_truth(
                result.get("json")
                if isinstance(result.get("json"), Mapping)
                else {}
            )
            markdown = _sanitize_status_text(str(result.get("markdown") or ""))
            rendered_html = _sanitize_status_text(str(result.get("html") or ""))
            pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
            pdf = sanitize_client_pdf_status(pdf)
            result.update(
                {
                    "json": canonical,
                    "markdown": markdown,
                    "html": rendered_html,
                    "pdf_base64": base64.b64encode(pdf).decode("ascii"),
                    "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                    "markdown_sha256": hashlib.sha256(
                        markdown.encode("utf-8")
                    ).hexdigest(),
                    "html_sha256": hashlib.sha256(
                        rendered_html.encode("utf-8")
                    ).hexdigest(),
                    "report_finality": REPORT_FINALITY,
                    "approval_status": APPROVAL_STATUS,
                    "delivery_status": DELIVERY_STATUS,
                    "human_review_required": True,
                    "human_review_completed": False,
                    "client_delivery_allowed": False,
                }
            )
            return result

        setattr(rebuild_wrapped, _REBUILD_MARKER, True)
        setattr(rebuild_wrapped, "_nico_previous", current_rebuild)
        report.rebuild_authoritative_premium_artifacts = rebuild_wrapped

    return {
        "status": "installed",
        "version": VERSION,
        "bound": getattr(report._clean_markdown, _MARKER, False),
        "canonical_projection_bound": getattr(
            report.project_authoritative_canonical,
            _PROJECT_MARKER,
            False,
        ),
        "html_status_sanitizer_bound": getattr(
            report._html_from_markdown,
            _HTML_MARKER,
            False,
        ),
        "pdf_status_sanitizer_bound": getattr(
            report._pdf_from_markdown,
            _PDF_MARKER,
            False,
        ),
        "rebuild_status_truth_bound": getattr(
            report.rebuild_authoritative_premium_artifacts,
            _REBUILD_MARKER,
            False,
        ),
        "markdown_html_pdf_share_gate": True,
        "client_delivery_remains_blocked": True,
        "automated_draft_language_required": True,
        "approval_language_reserved_for_approved_packages": True,
    }


__all__ = [
    "VERSION",
    "authoritative_review_gate_markdown",
    "ensure_authoritative_review_gate",
    "install_authoritative_review_gate",
]
