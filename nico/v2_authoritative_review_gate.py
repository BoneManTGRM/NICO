from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY

VERSION = "nico.v2.authoritative-review-gate.v2"
_MARKER = "__nico_authoritative_review_gate_v2__"


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


def authoritative_review_gate_markdown(*, spanish: bool) -> str:
    if spanish:
        return "\n".join([
            "## Puerta de revisión humana y aceptación", "",
            ES_BOUNDARY, "",
            "El borrador automatizado está completo como paquete de revisión, pero no es un informe final aprobado.", "",
            "- Estado automatizado: Completo.",
            "- Revisión humana: Obligatoria antes de cualquier entrega al cliente.",
            "- Aceptación: Pendiente para el paquete inmutable exacto.",
            "- Entrega al cliente: Bloqueada hasta la aprobación explícita.",
            "- Responsabilidad del revisor: Confirmar identidad, puntuación, evidencia, limitaciones, hallazgos y plan de remediación.",
            "- Cambio de estado permitido: Solo un revisor autorizado puede declarar FINAL APROBADO y ENTREGA AL CLIENTE AUTORIZADA.",
        ])
    return "\n".join([
        "## Human Review and Acceptance Gate", "",
        EN_BOUNDARY, "",
        "The automated draft is complete as a review package, but it is not an approved final report.", "",
        "- Automated status: Complete.",
        "- Human review: Required before any client delivery.",
        "- Acceptance: Pending for the exact immutable package.",
        "- Client delivery: Blocked until explicit approval.",
        "- Reviewer responsibility: Confirm identity, scores, evidence, limitations, findings, and remediation plan.",
        "- Permitted state change: Only an authorized reviewer may declare APPROVED FINAL and CLIENT DELIVERY AUTHORIZED.",
    ])


def ensure_authoritative_review_gate(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> str:
    localized = _is_spanish(canonical, spanish)
    heading = "## Puerta de revisión humana y aceptación" if localized else "## Human Review and Acceptance Gate"
    if heading in markdown:
        return markdown
    gate = authoritative_review_gate_markdown(spanish=localized)
    for marker in ("## Puerta de revisión y entrega", "## Delivery Status", "## Review and Delivery Gate"):
        if marker in markdown:
            return markdown.replace(marker, f"{gate}\n\n{marker}", 1)
    return markdown.rstrip() + "\n\n" + gate + "\n"


def install_authoritative_review_gate() -> dict[str, Any]:
    from nico import v2_authoritative_premium_report as report
    current: Callable[..., str] = report._clean_markdown
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def wrapped(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> str:
        cleaned = current(markdown, canonical, spanish=spanish)
        return ensure_authoritative_review_gate(cleaned, canonical, spanish=spanish)

    setattr(wrapped, _MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    report._clean_markdown = wrapped
    return {
        "status": "installed", "version": VERSION,
        "bound": report._clean_markdown is wrapped,
        "markdown_html_pdf_share_gate": True,
        "client_delivery_remains_blocked": True,
        "automated_draft_language_required": True,
    }


__all__ = ["VERSION", "authoritative_review_gate_markdown", "ensure_authoritative_review_gate", "install_authoritative_review_gate"]
