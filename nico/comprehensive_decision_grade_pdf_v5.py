from __future__ import annotations

import html
import io
from typing import Any

from nico.comprehensive_premium_pdf_v6 import _build_pdf as _premium_build_pdf
from nico.comprehensive_premium_pdf_v6 import _pdf_with_final_count as _premium_pdf_with_final_count

VERSION = "nico.comprehensive_decision_grade_pdf.v6"


def _text(value: Any, limit: int = 2200) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _supplement_pdf(stages: list[dict[str, Any]], pages_needed: int, run_id: str) -> bytes:
    """Build bounded appendix pages without unsafe PDF extraction characters.

    Phase 6 no longer calls this function to pad reports to an artificial page
    minimum. It remains as a compatibility boundary for explicit evidence
    supplement requests and regression tests that verify text extraction safety.
    """

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "P6S-H1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "P6S-H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=16,
        textColor=colors.HexColor("#075985"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "P6S-Body",
        parent=styles["BodyText"],
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "P6S-Small",
        parent=body,
        fontSize=7.1,
        leading=9.5,
        textColor=colors.HexColor("#475569"),
    )

    def paragraph(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    p = paragraph

    def list_item(value: Any) -> Paragraph:
        # A literal hyphen is used because ReportLab's default Helvetica bullet
        # can extract as DEL (U+007F) in some PDF readers.
        return p(f"- {_text(value, 2100)}", small)

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            .55 * inch,
            .36 * inch,
            f"NICO Comprehensive · {_text(run_id, 44)} · EVIDENCE DETAIL",
        )
        canvas.drawRightString(7.95 * inch, .36 * inch, f"Supplement {document.page}")
        canvas.restoreState()

    safe_stages = [item for item in stages if isinstance(item, dict)] or [
        {
            "title": "Evidence package",
            "stage_id": "package",
            "status": "complete",
            "summary": "No additional stage detail was retained.",
        }
    ]
    story: list[Any] = []
    bounded_pages = max(0, min(100, int(pages_needed)))
    for page_index in range(bounded_pages):
        stage = safe_stages[page_index % len(safe_stages)]
        story.extend(
            [
                paragraph("Evidence Appendix Detail", h1),
                paragraph(
                    f"{stage.get('title') or stage.get('stage_id')} — {_text(stage.get('status')).upper()}",
                    h2,
                ),
                paragraph(f"Stage ID: {stage.get('stage_id')}", small),
                paragraph(stage.get("summary") or "No additional summary retained.", body),
                Spacer(1, .08 * inch),
                paragraph("Retained evidence", h2),
            ]
        )
        evidence = list(stage.get("evidence") or [])
        findings = list(stage.get("findings") or [])
        unavailable = list(stage.get("unavailable") or [])
        story.extend(list_item(value) for value in evidence[:18])
        if findings:
            story.append(paragraph("Findings", h2))
            story.extend(list_item(value) for value in findings[:10])
        if unavailable:
            story.append(paragraph("Unavailable or limited evidence", h2))
            story.extend(list_item(value) for value in unavailable[:10])
        if not evidence and not findings and not unavailable:
            story.append(list_item("No additional machine-readable evidence was retained for this stage."))
        if page_index < bounded_pages - 1:
            story.append(PageBreak())

    if not story:
        story.append(paragraph("No evidence supplement pages were requested.", body))

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=.55 * inch,
        leftMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.6 * inch,
        invariant=1,
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _build_pdf(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
    final_page_count: int | None = None,
) -> bytes:
    """Build only evidence-bearing report pages.

    Earlier releases padded every report to a fixed minimum page count by
    repeating stage evidence. Phase 6 removes that artificial page contract:
    report length now follows unique decision-relevant content only.
    """

    return _premium_build_pdf(
        identity,
        assessment,
        stages,
        roadmap,
        staffing,
        limitations,
        generated_at,
        final_page_count,
    )


def _pdf_with_final_count(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> tuple[bytes, int]:
    """Return the natural report and its deterministic final page count."""

    return _premium_pdf_with_final_count(
        identity,
        assessment,
        stages,
        roadmap,
        staffing,
        limitations,
        generated_at,
    )


__all__ = ["VERSION", "_supplement_pdf", "_build_pdf", "_pdf_with_final_count"]
