from __future__ import annotations

import base64
import hashlib
import html
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
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
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
    cell = ParagraphStyle(
        "LocalizedQualityScorecardCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.6,
        textColor=colors.HexColor("#334155"),
        wordWrap="CJK",
    )
    header = ParagraphStyle(
        "LocalizedQualityScorecardHeader",
        parent=cell,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    def paragraph(value: Any, style: ParagraphStyle = cell) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    rows: list[list[Any]] = [
        [
            paragraph("Control", header),
            paragraph("Puntuación", header),
            paragraph("Ejecución", header),
            paragraph("Garantía", header),
        ]
    ]
    for section in sections:
        score = section.get(
            "score_value",
            section.get("presented_score", section.get("score")),
        )
        score_label = (
            f"{int(round(score))}/100"
            if isinstance(score, (int, float)) and not isinstance(score, bool)
            else "SIN PUNTUACIÓN"
        )
        execution = _spanish_status(
            section.get("execution_status")
            or section.get("presented_status")
            or section.get("status")
        )
        rows.append(
            [
                paragraph(_safe_es(section.get("label") or section.get("id"))),
                paragraph(score_label),
                paragraph(execution),
                paragraph(_spanish_assurance(section)),
            ]
        )

    table = LongTable(
        rows,
        colWidths=[2.35 * inch, 1.05 * inch, 1.25 * inch, 2.75 * inch],
        repeatRows=1,
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#075985")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        invariant=1,
    )
    document.build(
        [
            Spacer(1, 0.05 * inch),
            Paragraph("Cuadro de puntuación técnica", title),
            table,
        ]
    )
    return buffer.getvalue()


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
    for page in reader.pages:
        page_text = page.extract_text() or ""
        normalized = _normalized(page_text)
        is_scorecard = (
            "cuadro de puntuacion tecnica" in normalized
            or "canonical technical scorecard" in normalized
        )
        if not replaced and is_scorecard:
            for replacement_page in replacement.pages:
                writer.add_page(replacement_page)
            replaced = True
        else:
            writer.add_page(page)

    if not replaced:
        raise ValueError("localized canonical scorecard page was not found for safe replacement")

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), True, sections


def _validate_spanish_scorecard(
    pdf: bytes,
    sections: list[Mapping[str, Any]],
) -> None:
    from pypdf import PdfReader
    from nico.comprehensive_spanish_presentation_parity_v1 import _safe_es

    if not sections:
        return
    reader = PdfReader(io.BytesIO(pdf))
    scorecard_pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        normalized = _normalized(text)
        if "cuadro de puntuacion tecnica" in normalized:
            scorecard_pages.append(text)
    if len(scorecard_pages) != 1:
        raise ValueError("final Spanish premium PDF must contain exactly one technical scorecard")

    scorecard_text = scorecard_pages[0]
    for section in sections:
        label = _safe_es(section.get("label") or section.get("id"))
        score = section.get(
            "score_value",
            section.get("presented_score", section.get("score")),
        )
        if label and label not in scorecard_text:
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

    scorecard_pdf, replaced, sections = _replace_spanish_scorecard(raw, canonical)
    pdf, finality_replacements = _replace_pdf_text(scorecard_pdf, spanish=True)
    _validate_final_pdf(
        pdf,
        canonical,
        expected_sections=[],
        spanish=True,
    )
    _validate_spanish_scorecard(pdf, sections)

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
