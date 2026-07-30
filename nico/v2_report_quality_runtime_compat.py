from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any, Mapping

from nico.v2_report_quality_repairs import (
    VERSION,
    _is_spanish,
    _replace_pdf_text,
    _scorecard_page,
    _validate_final_pdf,
    _normalize_final_text,
)

_SCORECARD_TITLES = (
    "Canonical Technical Scorecard",
    "Technical Scorecard and Weighting",
    "Tarjeta de puntuación técnica y ponderación",
    "Cuadro de mando técnico y ponderación",
)


def _is_scorecard_page(text: str) -> bool:
    normalized = " ".join(str(text or "").split()).casefold()
    return any(title.casefold() in normalized for title in _SCORECARD_TITLES)


def repair_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    """Repair premium reports across all currently supported scorecard headings.

    This preserves canonical scores and evidence. It only replaces the existing
    scorecard page when canonical section rows exist and validates every row.
    """
    from pypdf import PdfReader, PdfWriter

    result = deepcopy(dict(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, Mapping)]
    raw = base64.b64decode(str(result.get("pdf_base64") or ""))
    if not raw.startswith(b"%PDF"):
        raise ValueError("report quality repair requires a valid PDF")

    reader = PdfReader(io.BytesIO(raw))
    writer = PdfWriter()
    replaced = False
    replacement_pages = PdfReader(io.BytesIO(_scorecard_page(canonical))).pages if sections else []
    for page in reader.pages:
        text = page.extract_text() or ""
        if sections and not replaced and _is_scorecard_page(text):
            for replacement_page in replacement_pages:
                writer.add_page(replacement_page)
            replaced = True
        else:
            writer.add_page(page)
    if sections and not replaced:
        observed = [" ".join((page.extract_text() or "").split())[:160] for page in reader.pages[:6]]
        raise ValueError(f"technical scorecard page was not found for safe replacement; observed={observed}")

    output = io.BytesIO()
    writer.write(output)
    spanish = _is_spanish(canonical)
    pdf, finality_replacements = _replace_pdf_text(output.getvalue(), spanish=spanish)
    _validate_final_pdf(pdf, canonical, expected_sections=sections, spanish=spanish)

    markdown = _normalize_final_text(str(result.get("markdown") or ""), spanish=spanish)
    rendered_html = _normalize_final_text(str(result.get("html") or ""), spanish=spanish)
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update({
        "report_quality_repairs_version": VERSION,
        "runtime_compatibility_version": "nico.v2.report-quality-runtime-compat.v1",
        "scorecard_word_jumble_removed": replaced,
        "scorecard_cells_wrapped": replaced,
        "scorecard_replacement_skipped_no_sections": not bool(sections),
        "scorecard_rows_verified": bool(sections),
        "stale_draft_language_removed": True,
        "final_pending_approval_semantics_verified": True,
        "pdf_text_replacements": finality_replacements,
    })
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    result.update({
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "pdf_page_count": page_count,
        "core_report_page_count": page_count,
        "final_package_page_count": page_count,
        "status": "review_required",
        "assessment_state": "review_required",
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "premium_report_renderer": contract,
    })
    return result


__all__ = ["repair_rendered_report"]
