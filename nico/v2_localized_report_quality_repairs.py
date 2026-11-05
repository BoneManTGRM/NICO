from __future__ import annotations

import base64
import hashlib
import io
import unicodedata
from copy import deepcopy
from typing import Any, Mapping

from nico.v2_report_quality_repairs import (
    _is_spanish,
    _normalize_final_text,
    _replace_pdf_text,
    _text,
    _validate_final_pdf,
    repair_rendered_report as _repair_english_report,
)

VERSION = "nico.v2.localized-report-quality-repairs.v1"


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _spanish_status(value: Any) -> str:
    raw = _text(value).replace("_", " ").strip()
    translated = {
        "strong": "Fuerte",
        "moderate": "Moderado",
        "weak": "Débil",
        "critical": "Crítico",
        "complete": "Completa",
        "completed": "Completa",
        "review limited": "Revisión limitada",
        "evidence evaluated": "Evidencia evaluada",
        "verified": "Verificada",
        "not scored": "Sin puntuación",
        "pending": "Pendiente",
        "unknown": "Desconocido",
        "exceptional": "Excepcional",
        "provisional strong": "Fuerte provisional",
        "provisional moderate": "Moderado provisional",
    }
    return translated.get(raw.casefold(), raw.title() or "Pendiente")


def _spanish_assurance(section: Mapping[str, Any]) -> str:
    value = _text(
        section.get("assurance_label")
        or section.get("assurance_status")
        or section.get("evidence_assurance")
    )
    translated = {
        "verified with completed scanners": "Verificada con analizadores completos",
        "review limited": "Revisión limitada",
        "evidence bound": "Basada en evidencia",
        "verified": "Verificada",
        "complete": "Completa",
    }
    return translated.get(value.replace("_", " ").casefold(), value.replace("_", " ").title() or "Revisión limitada")


def _spanish_scorecard_page(canonical: Mapping[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer
    from nico.comprehensive_spanish_presentation_parity_v1 import _safe_es

    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    sections = [
        item
        for item in assessment.get("sections") or []
        if isinstance(item, Mapping)
    ]
    if not sections:
        raise ValueError("localized scorecard replacement requires canonical section rows")

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "LocalizedQualityScorecardTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=12,
    )
    # Use the same complete columns, score precedence and flowing layout as the
    # canonical renderer. The former Spanish-only table discarded summaries and
    # substituted execution/assurance for canonical status.
    from nico.comprehensive_report_package import _scorecard_pdf_table

    labels = {"Control": "Control", "Status": "Estado", "Score": "Puntuación",
              "Summary": "Resumen", "NOT SCORED": "SIN PUNTUACIÓN",
              "GRAY": "GRIS", "GREEN": "VERDE", "YELLOW": "AMARILLO", "RED": "ROJO"}
    def localize(value: str) -> str:
        return labels.get(value, _spanish_status(value).upper())

    from nico.comprehensive_spanish_canonical_report_v87 import _render_inputs
    # The replacement receives retained canonical truth, which may still contain
    # English authored summaries. Reuse the canonical literal-aware projection.
    _, localized_assessment, _, _ = _render_inputs(canonical)
    projected = [dict(section) for section in localized_assessment.get("sections") or []
                 if isinstance(section, Mapping)]
    # Match the existing English final-repair display rule, not the earlier
    # intermediate table's truncation. Only copied presentation rows are rounded.
    for section in projected:
        score = section.get("presented_score", section.get("score"))
        section["presented_score"] = (int(round(score))
            if isinstance(score, (int, float)) and not isinstance(score, bool) else None)
    table = _scorecard_pdf_table(projected, width=7.4 * inch - 12, localized=localize)
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        invariant=1,
    )
    from nico.report_score_explanation import LABELS_ES, score_explanation
    from nico.comprehensive_engagement_metadata_v1 import reportlab_literal_markup

    localize = lambda value: LABELS_ES.get(value, value)
    explanation_style = ParagraphStyle(
        "LocalizedQualityScoreExplanation", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=9.2, leading=13.5, spaceAfter=6,
    )
    explanation = [localize("Technical-to-adjusted score explanation"),
                   *score_explanation(assessment, localize)]
    document.build(
        [
            Spacer(1, 0.05 * inch),
            Paragraph("Cuadro de puntuación técnica", title),
            table,
            Spacer(1, 0.1 * inch),
            KeepTogether([Paragraph(reportlab_literal_markup(line, len(line)), explanation_style)
                          for line in explanation]),
        ]
    )
    # Mark the complete generated block so later rebinding can replace all owned
    # continuation pages without guessing from body text.
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject
    reader = PdfReader(io.BytesIO(buffer.getvalue()))
    writer = PdfWriter()
    for index, page in enumerate(reader.pages):
        page[NameObject("/NICOScorecardPage")] = NumberObject(index)
        page[NameObject("/NICOScorecardPages")] = NumberObject(len(reader.pages))
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class _ScorecardOwnershipUnavailable(ValueError):
    """Legacy pages cannot establish a safe replacement range."""


def _replace_spanish_scorecard(
    pdf: bytes,
    canonical: Mapping[str, Any],
) -> tuple[bytes, bool, list[Mapping[str, Any]]]:
    from pypdf import PdfReader, PdfWriter

    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    sections = [
        item
        for item in assessment.get("sections") or []
        if isinstance(item, Mapping)
    ]
    if not sections:
        return pdf, False, sections

    replacement = PdfReader(io.BytesIO(_spanish_scorecard_page(canonical)))
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    replaced = False
    index = 0
    while index < len(reader.pages):
        page = reader.pages[index]
        normalized = _normalized(page.extract_text() or "")
        is_scorecard = ("cuadro de puntuacion tecnica" in normalized
                        or "canonical technical scorecard" in normalized)
        if not replaced and is_scorecard:
            from nico.v2_report_quality_repairs import _owned_scorecard_page_count
            count = _owned_scorecard_page_count(reader, index)
            if count is None:
                raise _ScorecardOwnershipUnavailable(
                    "unmarked localized scorecard continuation ownership unavailable")
            for replacement_page in replacement.pages:
                writer.add_page(replacement_page)
            index += count
            replaced = True
        else:
            writer.add_page(page)
            index += 1

    if not replaced:
        raise ValueError("localized canonical scorecard page was not found for safe replacement")

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), True, sections


def _validate_spanish_scorecard(
    pdf: bytes,
    sections: list[Mapping[str, Any]],
    canonical: Mapping[str, Any] | None = None,
) -> None:
    from pypdf import PdfReader
    from nico.comprehensive_spanish_presentation_parity_v1 import _safe_es

    if not sections:
        return
    reader = PdfReader(io.BytesIO(pdf))
    texts = [page.extract_text() or "" for page in reader.pages]
    starts = [index for index, text in enumerate(texts)
              if "cuadro de puntuacion tecnica" in _normalized(text)]
    if len(starts) != 1:
        raise ValueError("final Spanish premium PDF must contain exactly one technical scorecard")
    expected = _spanish_scorecard_page(canonical or {"assessment": {"sections": sections}})
    expected_reader = PdfReader(io.BytesIO(expected))
    stop = starts[0] + len(expected_reader.pages)
    if stop > len(texts):
        raise ValueError("final Spanish premium PDF truncated the technical scorecard")
    scorecard_text = "\n".join(texts[starts[0]:stop])
    # Check complete rendered content, including summaries and continuation rows,
    # within the renderer-owned page range rather than anywhere in the report.
    from collections import Counter
    import re
    def tokens(value: str) -> Counter:
        return Counter(re.findall(r"\w+", _normalized(value)))
    expected_tokens = tokens("\n".join(page.extract_text() or "" for page in expected_reader.pages))
    if expected_tokens - tokens(scorecard_text):
        raise ValueError("Spanish scorecard omitted canonical presentation content")
    for section in sections:
        label = _safe_es(section.get("label") or section.get("id"))
        score = section.get("presented_score", section.get("score"))
        if label and re.sub(r"\s+", "", _normalized(label)) not in re.sub(r"\s+", "", _normalized(scorecard_text)):
            raise ValueError(f"Spanish scorecard omitted canonical control row: {label}")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            score_label = f"{int(round(score))}/100"
            if score_label not in scorecard_text:
                raise ValueError(
                    f"Spanish scorecard omitted canonical score {score_label} for {label}"
                )


def repair_localized_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the report-quality repair without replacing Spanish pages with English ones."""
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    if not _is_spanish(canonical):
        return _repair_english_report(package)

    from pypdf import PdfReader

    result = deepcopy(dict(package))
    raw = base64.b64decode(str(result.get("pdf_base64") or ""))
    if not raw.startswith(b"%PDF"):
        raise ValueError("localized report quality repair requires a valid PDF")

    try:
        scorecard_pdf, replaced, sections = _replace_spanish_scorecard(raw, canonical)
    except _ScorecardOwnershipUnavailable:
        from nico.v2_report_quality_repairs import _repair_unavailable
        return _repair_unavailable(package)
    pdf, finality_replacements = _replace_pdf_text(scorecard_pdf, spanish=True)
    _validate_final_pdf(
        pdf,
        canonical,
        expected_sections=[],
        spanish=True,
    )
    _validate_spanish_scorecard(pdf, sections, canonical)

    markdown = _normalize_final_text(str(result.get("markdown") or ""), spanish=True)
    rendered_html = _normalize_final_text(str(result.get("html") or ""), spanish=True)
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update(
        {
            "localized_report_quality_repairs_version": VERSION,
            "scorecard_word_jumble_removed": replaced,
            "scorecard_cells_wrapped": replaced,
            "scorecard_replacement_skipped_no_sections": not bool(sections),
            "scorecard_rows_verified": bool(sections),
            "spanish_scorecard_layout_preserved": True,
            "stale_draft_language_removed": True,
            "final_pending_approval_semantics_verified": True,
            "pdf_text_replacements": finality_replacements,
        }
    )
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    result.update(
        {
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
        }
    )
    return result


__all__ = ["VERSION", "repair_localized_rendered_report"]
