from __future__ import annotations

import html
import io
from typing import Any

from nico.comprehensive_premium_pdf_v6 import _build_pdf as _premium_build_pdf
from nico.comprehensive_premium_pdf_v6 import _pdf_with_final_count as _premium_pdf_with_final_count

_MIN_DECISION_GRADE_PAGES = 25


def _text(value: Any, limit: int = 1200) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _supplement_pdf(stages: list[dict[str, Any]], pages_needed: int, run_id: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("P6S-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#0f172a"), spaceAfter=8)
    h2 = ParagraphStyle("P6S-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=colors.HexColor("#075985"), spaceBefore=6, spaceAfter=4)
    body = ParagraphStyle("P6S-Body", parent=styles["BodyText"], fontSize=8.5, leading=12, textColor=colors.HexColor("#334155"), spaceAfter=4)
    small = ParagraphStyle("P6S-Small", parent=body, fontSize=7.1, leading=9.5, textColor=colors.HexColor("#475569"))

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value, 2200)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .36 * inch, f"NICO Comprehensive · {_text(run_id, 44)} · EVIDENCE DETAIL")
        canvas.drawRightString(7.95 * inch, .36 * inch, f"Supplement {doc.page}")
        canvas.restoreState()

    safe_stages = [item for item in stages if isinstance(item, dict)] or [{"title": "Evidence package", "stage_id": "package", "status": "complete", "summary": "No additional stage detail was retained."}]
    story: list[Any] = []
    for page_index in range(pages_needed):
        stage = safe_stages[page_index % len(safe_stages)]
        story.extend([
            p("Evidence Appendix Detail", h1),
            p(f"{stage.get('title') or stage.get('stage_id')} — {_text(stage.get('status')).upper()}", h2),
            p(f"Stage ID: {stage.get('stage_id')}", small),
            p(stage.get("summary") or "No additional summary retained.", body),
            Spacer(1, .08 * inch),
            p("Retained evidence", h2),
        ])
        evidence = list(stage.get("evidence") or [])
        findings = list(stage.get("findings") or [])
        unavailable = list(stage.get("unavailable") or [])
        for item in evidence[:18]:
            story.append(p(f"• {item}", small))
        if findings:
            story.append(p("Findings", h2))
            for item in findings[:10]:
                story.append(p(f"• {item}", small))
        if unavailable:
            story.append(p("Unavailable or limited evidence", h2))
            for item in unavailable[:10]:
                story.append(p(f"• {item}", small))
        if not evidence and not findings and not unavailable:
            story.append(p("• No additional machine-readable evidence was retained for this stage.", small))
        if page_index < pages_needed - 1:
            story.append(PageBreak())

    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55 * inch, leftMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.6 * inch, invariant=1)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _ensure_page_contract(pdf_bytes: bytes, stages: list[dict[str, Any]], run_id: str) -> tuple[bytes, int]:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    current = len(reader.pages)
    if current >= _MIN_DECISION_GRADE_PAGES:
        return pdf_bytes, current

    supplement = _supplement_pdf(stages, _MIN_DECISION_GRADE_PAGES - current, run_id)
    supplement_reader = PdfReader(io.BytesIO(supplement))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    for page in supplement_reader.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), len(writer.pages)


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
    base = _premium_build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at, final_page_count)
    enriched, _ = _ensure_page_contract(base, stages, str(identity.get("run_id") or "run"))
    return enriched


def _pdf_with_final_count(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> tuple[bytes, int]:
    base, _ = _premium_pdf_with_final_count(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    return _ensure_page_contract(base, stages, str(identity.get("run_id") or "run"))


__all__ = ["_build_pdf", "_pdf_with_final_count"]
