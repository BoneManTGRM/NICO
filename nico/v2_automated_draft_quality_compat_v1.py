from __future__ import annotations

import hashlib
import html
import io
import re
import unicodedata
from copy import deepcopy
from typing import Any, Mapping

from nico.client_text_status_sanitizer_v1 import sanitize_client_text_status
from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_STATUS,
    DELIVERY_STATUS,
    EN_BOUNDARY,
    ES_BOUNDARY,
    REPORT_FINALITY,
    apply_automated_draft_truth,
)

VERSION = "nico.v2.automated-draft-quality-compat.v2"
_MARKER = "__nico_automated_draft_quality_compat_v1__"

_PDF_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
        EN_BOUNDARY,
    ),
    (
        "FINAL REPORT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED",
        "AUTOMATED DRAFT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED",
    ),
    (
        "FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED",
        "AUTOMATED DRAFT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED",
    ),
    (
        "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED",
        EN_BOUNDARY,
    ),
    (
        "DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY NOT AUTHORIZED",
        "AUTOMATED DRAFT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED",
    ),
    (
        "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
        "AUTOMATED DRAFT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED",
    ),
    (
        "INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA BLOQUEADA",
        ES_BOUNDARY,
    ),
    (
        "INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
        ES_BOUNDARY,
    ),
    ("AUTOMATED FINAL", "AUTOMATED DRAFT"),
    (" · FINAL Page", " · AUTOMATED DRAFT Page"),
    (" · FINAL Página", " · BORRADOR AUTOMATIZADO Página"),
    (
        "The package is a final automated assessment pending human approval",
        "The package is an automated draft pending human approval",
    ),
    (
        "The report is a final automated assessment pending human approval.",
        "The report is an automated draft pending human approval.",
    ),
    (
        "The automated assessment is complete only as a draft.",
        "The automated draft assessment is complete and pending human approval.",
    ),
)

_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    *_PDF_REPLACEMENTS,
    (
        "The package is a review-gated final: automated evidence and recommendations are not client approval or delivery authorization.",
        "The package is an automated draft pending human approval; automated evidence and recommendations are not client approval or delivery authorization.",
    ),
)

# These sentences describe a possible later human-authorized state. They are not
# assertions about the current automated package. Removal is exact and narrow so a
# second current-state assertion in the same PDF remains detectable.
_AUTHORIZED_FUTURE_STATE_GUIDANCE: tuple[str, ...] = (
    (
        "Only an authorized reviewer may change the status to APPROVED FINAL "
        "and CLIENT DELIVERY AUTHORIZED."
    ),
    (
        "Solo un revisor autorizado puede cambiar el estado a FINAL APROBADO "
        "y ENTREGA AL CLIENTE AUTORIZADA."
    ),
    (
        "Automation cannot change this package to APPROVED FINAL or CLIENT DELIVERY AUTHORIZED."
    ),
    (
        "La automatización no puede cambiar este paquete a FINAL APROBADO ni "
        "ENTREGA AL CLIENTE AUTORIZADA."
    ),
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _semantic(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def _contains_legacy_bare_draft(value: str) -> bool:
    normalized = _semantic(value)
    normalized = normalized.replace("automated draft", "")
    normalized = normalized.replace("borrador automatizado", "")
    return bool(
        re.search(
            r"\bdraft\b|\bdraft only\b|\bcomplete only as a draft\b|\bborrador solamente\b",
            normalized,
            re.IGNORECASE,
        )
    )


def _current_state_finality_scope(value: str) -> str:
    """Remove only exact explanatory sentences about a possible future state."""

    current = _semantic(value)
    for guidance in _AUTHORIZED_FUTURE_STATE_GUIDANCE:
        current = current.replace(_semantic(guidance), " ")
    return " ".join(current.split())


def _contains_unapproved_finality(value: str) -> bool:
    current_state = _current_state_finality_scope(value)
    return any(
        marker in current_state
        for marker in (
            "final report",
            "informe final",
            "automated final",
            "final aprobado",
            "approved final",
            "client delivery authorized",
            "entrega al cliente autorizada",
        )
    )


def _status_overlay(*, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.setFillColor(colors.HexColor("#f0a23a"))
    page.setFont("Helvetica-Bold", 7.2)
    page.drawString(42, 76, ES_BOUNDARY if spanish else EN_BOUNDARY)
    page.save()
    return buffer.getvalue()


def _normalize_review_text(value: str, *, spanish: bool) -> str:
    output = str(value or "")
    for previous, replacement in _TEXT_REPLACEMENTS:
        output = output.replace(previous, replacement)
    output = sanitize_client_text_status(output)
    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    if _semantic(boundary) not in _semantic(output):
        if "<html" in output.casefold():
            insertion = f'<p class="warning">{html.escape(boundary)}</p>'
            if "</article>" in output:
                output = output.replace("</article>", insertion + "</article>", 1)
            elif "</body>" in output:
                output = output.replace("</body>", insertion + "</body>", 1)
            else:
                output += insertion
        else:
            heading = "## Estado de entrega" if spanish else "## Delivery Status"
            output = output.rstrip() + f"\n\n{heading}\n{boundary}\n"
    return output


def _validate_review_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    expected_sections: list[Mapping[str, Any]],
    spanish: bool,
) -> None:
    from pypdf import PdfReader

    from nico.v2_pdf_control_character_guard import _assert_no_control_glyphs

    if not pdf.startswith(b"%PDF"):
        raise ValueError("report quality repair produced an invalid PDF")
    _assert_no_control_glyphs(pdf)
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized = _semantic(extracted)

    if _contains_legacy_bare_draft(extracted):
        raise ValueError("review PDF retained legacy bare DRAFT language")
    if _contains_unapproved_finality(extracted):
        raise ValueError("unapproved review PDF retained final-delivery language")

    if spanish:
        if (
            "borrador automatizado" not in normalized
            or "aprobacion humana pendiente" not in normalized
            or "entrega al cliente bloqueada" not in normalized
        ):
            raise ValueError("Spanish review PDF omitted automated-draft approval semantics")
    elif (
        "automated draft" not in normalized
        or "pending human approval" not in normalized
        or "client delivery blocked" not in normalized
    ):
        raise ValueError("review PDF omitted automated-draft pending-approval semantics")

    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    for required in (_text(identity.get("run_id")), _text(identity.get("commit_sha"))):
        if required and required not in extracted:
            raise ValueError(f"review PDF omitted required identity text: {required}")

    if expected_sections:
        scorecard_pages = [
            page.extract_text() or ""
            for page in reader.pages
            if "Canonical Technical Scorecard" in (page.extract_text() or "")
        ]
        if len(scorecard_pages) != 1:
            raise ValueError("review PDF must contain exactly one technical scorecard")
        scorecard_text = scorecard_pages[0]
        for section in expected_sections:
            label = _text(section.get("label") or section.get("id"))
            score = section.get("presented_score", section.get("score"))
            if label and label not in scorecard_text:
                raise ValueError(f"scorecard omitted canonical control row: {label}")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                score_label = f"{int(round(score))}/100"
                if score_label not in scorecard_text:
                    raise ValueError(
                        f"scorecard omitted canonical score {score_label} for {label}"
                    )


def install_automated_draft_quality_compat() -> dict[str, Any]:
    from nico import v2_localized_report_quality_repairs as localized
    from nico import v2_report_quality_repairs as quality

    if getattr(quality._validate_final_pdf, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "automated_draft_is_valid_unapproved_state": True,
            "future_approval_guidance_is_not_current_finality": True,
            "legacy_bare_draft_remains_blocked": True,
            "unapproved_finality_remains_blocked": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    quality._FINAL_PDF_REPLACEMENTS = _PDF_REPLACEMENTS
    quality._FINAL_TEXT_REPLACEMENTS = _TEXT_REPLACEMENTS
    quality._final_status_overlay = _status_overlay
    quality._normalize_final_text = _normalize_review_text
    setattr(_validate_review_pdf, _MARKER, True)
    setattr(_validate_review_pdf, "_nico_previous", quality._validate_final_pdf)
    quality._validate_final_pdf = _validate_review_pdf

    localized._replace_pdf_text = quality._replace_pdf_text
    localized._normalize_final_text = _normalize_review_text
    localized._validate_final_pdf = _validate_review_pdf

    return {
        "status": "installed",
        "version": VERSION,
        "bound": quality._validate_final_pdf is _validate_review_pdf,
        "english_runtime_compat_bound": True,
        "spanish_runtime_compat_bound": True,
        "automated_draft_is_valid_unapproved_state": True,
        "future_approval_guidance_is_not_current_finality": True,
        "legacy_bare_draft_remains_blocked": True,
        "legacy_bare_draft_language_absent": True,
        "unapproved_finality_remains_blocked": True,
        "scorecard_and_identity_validation_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _project_result(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    canonical = apply_automated_draft_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    markdown = _normalize_review_text(
        str(result.get("markdown") or ""),
        spanish=_semantic(
            canonical.get("report_language") or canonical.get("locale")
        ).startswith("es"),
    )
    rendered_html = _normalize_review_text(
        str(result.get("html") or ""),
        spanish=_semantic(
            canonical.get("report_language") or canonical.get("locale")
        ).startswith("es"),
    )
    result.update(
        {
            "json": canonical,
            "markdown": markdown,
            "html": rendered_html,
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "report_finality": REPORT_FINALITY,
            "approval_status": APPROVAL_STATUS,
            "delivery_status": DELIVERY_STATUS,
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
        }
    )
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update(
        {
            "automated_draft_quality_compat_version": VERSION,
            "automated_draft_is_valid_unapproved_state": True,
            "future_approval_guidance_is_not_current_finality": True,
            "legacy_bare_draft_remains_blocked": True,
            "legacy_bare_draft_language_absent": True,
            "unapproved_finality_language_absent": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    result["premium_report_renderer"] = contract
    return result


def repair_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    install_automated_draft_quality_compat()
    from nico.v2_report_quality_runtime_compat import repair_rendered_report as delegate

    return _project_result(delegate(package))


def repair_localized_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    install_automated_draft_quality_compat()
    from nico.v2_localized_report_quality_repairs import (
        repair_localized_rendered_report as delegate,
    )

    return _project_result(delegate(package))


__all__ = [
    "VERSION",
    "_contains_unapproved_finality",
    "_current_state_finality_scope",
    "install_automated_draft_quality_compat",
    "repair_localized_rendered_report",
    "repair_rendered_report",
]
