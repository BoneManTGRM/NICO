from __future__ import annotations

import io
from typing import Any

from pypdf import PdfReader, PdfWriter

VERSION = "nico.express_pdf_renderer_truth.v21"
_PATCH_MARKER = "_nico_express_pdf_renderer_truth_v21"


def proportional_width(score: Any, maximum_width: float = 96.0) -> float:
    try:
        value = max(0.0, min(100.0, float(score)))
    except (TypeError, ValueError):
        value = 0.0
    return maximum_width * (value / 100.0)


def _text(value: Any, limit: int = 800) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any]:
    for item in result.get("sections") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == section_id:
            return item
    return {}


def _score_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    transparency = result.get("express_score_transparency")
    if isinstance(transparency, dict) and isinstance(transparency.get("records"), list):
        return [dict(item) for item in transparency["records"] if isinstance(item, dict)]
    return []


def _replacement_score_page(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    class ScoreBar(Flowable):
        def __init__(self, score: Any, width: float = 96.0, height: float = 8.0) -> None:
            super().__init__()
            self.score = max(0.0, min(100.0, float(score or 0)))
            self.width = width
            self.height = height
            self.fill_width = proportional_width(self.score, width)

        def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
            return self.width, self.height

        def draw(self) -> None:
            self.canv.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.canv.setFillColor(colors.HexColor("#f8fafc"))
            self.canv.roundRect(0, 0, self.width, self.height, 2, stroke=1, fill=1)
            if self.fill_width > 0:
                if self.score >= 75:
                    fill = colors.HexColor("#059669")
                elif self.score >= 45:
                    fill = colors.HexColor("#d97706")
                else:
                    fill = colors.HexColor("#dc2626")
                self.canv.setFillColor(fill)
                self.canv.roundRect(0, 0, self.fill_width, self.height, 2, stroke=0, fill=1)

    records = _score_records(result)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.66 * inch,
        title="NICO Express Score Contribution and Constraints",
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ScoreTruthTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=26, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    body = ParagraphStyle("ScoreTruthBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=10.5, textColor=colors.HexColor("#334155"), spaceAfter=4)
    label = ParagraphStyle("ScoreTruthLabel", parent=body, fontName="Helvetica-Bold", fontSize=7.4, leading=9.2, textColor=colors.HexColor("#64748b"))

    def p(value: Any, style: Any = body) -> Paragraph:
        import html
        return Paragraph(html.escape(_text(value)), style)

    rows: list[list[Any]] = [[p("Control", label), p("Presented", label), p("Exact proportional contribution", label), p("Primary constraint", label)]]
    geometry: list[dict[str, Any]] = []
    for item in records:
        score = int(item.get("presented_score") or 0)
        width = proportional_width(score)
        geometry.append({"section_id": item.get("section_id"), "score": score, "maximum_width": 96.0, "rendered_width": width, "ratio": score / 100.0})
        rows.append([p(item.get("label") or item.get("section_id")), p(f"{score}/100"), ScoreBar(score), p(item.get("rationale") or "No material constraint retained.")])
    result["express_pdf_bar_geometry"] = {"version": VERSION, "render_mode": "reportlab_vector_geometry", "records": geometry}
    table = Table(rows, colWidths=[1.55 * inch, 0.75 * inch, 1.65 * inch, 3.1 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story = [p("Score Contribution and Constraints", title), p("Each bar is a measured ReportLab vector whose filled width equals score/100 of the available track. A score of 0 renders zero fill; low scores remain visibly short."), Spacer(1, 0.08 * inch), table]
    doc.build(story)
    return buffer.getvalue()


def _replacement_decision_page(result: dict[str, Any], section_id: str, page_title: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    section = _section(result, section_id)
    record = next((item for item in _score_records(result) if item.get("section_id") == section_id), {})
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.55 * inch, leftMargin=0.55 * inch, topMargin=0.55 * inch, bottomMargin=0.66 * inch, title=page_title, author="NICO", invariant=1)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DecisionTruthTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=25, textColor=colors.HexColor("#0f172a"), spaceAfter=9)
    h2 = ParagraphStyle("DecisionTruthH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor("#075985"), spaceBefore=5, spaceAfter=3)
    body = ParagraphStyle("DecisionTruthBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=10.6, textColor=colors.HexColor("#334155"), spaceAfter=4)
    label = ParagraphStyle("DecisionTruthLabel", parent=body, fontName="Helvetica-Bold", fontSize=7.4, leading=9.2, textColor=colors.HexColor("#64748b"))

    def p(value: Any, style: Any = body) -> Paragraph:
        import html
        return Paragraph(html.escape(_text(value)), style)

    def bullets(values: Any, maximum: int) -> list[Paragraph]:
        items = [str(item) for item in values or [] if str(item).strip()]
        output = [p(f"• {item}") for item in items[:maximum]]
        if not output:
            output = [p("No retained item.")]
        return output

    score_table = Table([
        [p("Source score", label), p(f"{record.get('source_score', section.get('score', 0))}/100"), p("Presented score", label), p(f"{record.get('presented_score', 0)}/100")],
        [p("Status", label), p(str(record.get("status") or section.get("status") or "unknown").upper()), p("Confidence", label), p(record.get("confidence") or "unknown")],
    ], colWidths=[1.1 * inch, 2.4 * inch, 1.1 * inch, 2.45 * inch])
    score_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story: list[Any] = [p(page_title, title), score_table, Spacer(1, 0.08 * inch), p(section.get("summary") or "No section summary retained."), p("Exact evidence", h2), *bullets(section.get("evidence"), 7), p("Open findings", h2), *bullets(section.get("findings"), 6), p("Limitations", h2), *bullets(section.get("unavailable"), 5), p("Score rationale", h2), p(record.get("rationale") or "No score rationale retained.")]
    doc.build(story)
    return buffer.getvalue()


def replace_renderer_pages(pdf_bytes: bytes, result: dict[str, Any]) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    score_replaced = False
    architecture_replaced = False
    for page in reader.pages:
        text = page.extract_text() or ""
        if "Score Contribution and Constraints" in text:
            for replacement in PdfReader(io.BytesIO(_replacement_score_page(result))).pages:
                writer.add_page(replacement)
            score_replaced = True
            continue
        if "Architecture, Complexity, and Ownership Decision Record" in text:
            for replacement in PdfReader(io.BytesIO(_replacement_decision_page(result, "architecture_debt", "Architecture Decision Record"))).pages:
                writer.add_page(replacement)
            for replacement in PdfReader(io.BytesIO(_replacement_decision_page(result, "velocity_complexity", "Velocity, Complexity, and Ownership Decision Record"))).pages:
                writer.add_page(replacement)
            architecture_replaced = True
            continue
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    result["express_pdf_renderer_truth"] = {
        "status": "complete" if score_replaced and architecture_replaced else "degraded",
        "version": VERSION,
        "score_page_replaced": score_replaced,
        "architecture_velocity_split": architecture_replaced,
        "actual_vector_geometry": score_replaced,
        "page_count": len(writer.pages),
        "human_review_required": True,
    }
    return output.getvalue()


def install_express_pdf_renderer_truth_v21() -> dict[str, Any]:
    from nico import express_report_premium_v14 as premium

    current = premium._premium_pdf
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    def truthful_premium_pdf(result: dict[str, Any]) -> bytes:
        return replace_renderer_pages(current(result), result)

    setattr(truthful_premium_pdf, _PATCH_MARKER, True)
    setattr(truthful_premium_pdf, "_nico_previous", current)
    premium._premium_pdf = truthful_premium_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "actual_vector_geometry": True,
        "architecture_velocity_split": True,
        "human_review_required": True,
    }


__all__ = ["VERSION", "install_express_pdf_renderer_truth_v21", "proportional_width", "replace_renderer_pages"]
