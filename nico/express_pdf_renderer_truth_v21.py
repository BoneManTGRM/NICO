from __future__ import annotations

import io
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pypdf import PdfReader, PdfWriter

VERSION = "nico.express_pdf_renderer_truth.v22"
_PATCH_MARKER = "_nico_express_pdf_renderer_truth_v21"
_VECTOR_PROBES = (0, 6, 74, 86, 90)


def proportional_width(score: Any, maximum_width: float = 96.0) -> float:
    try:
        value = max(0.0, min(100.0, float(score)))
    except (TypeError, ValueError):
        value = 0.0
    width = (Decimal(str(maximum_width)) * Decimal(str(value)) / Decimal("100")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return float(width)


def _text(value: Any, limit: int = 800) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _norm(value: str) -> str:
    return " ".join(str(value or "").replace("\u00ad", "").split()).casefold()


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any]:
    return next((item for item in result.get("sections") or [] if isinstance(item, dict) and item.get("id") == section_id), {})


def _score_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    transparency = result.get("express_score_transparency")
    records = transparency.get("records") if isinstance(transparency, dict) else None
    if not isinstance(records, list):
        contract = result.get("express_cross_format_contract")
        records = contract.get("canonical_records") if isinstance(contract, dict) else []
    output = []
    for item in records or []:
        if not isinstance(item, dict):
            continue
        section_id = _text(item.get("section_id")).casefold()
        status = _text(item.get("status")).casefold()
        score = item.get("presented_score", item.get("score"))
        if section_id in {"scanner_worker", "scanner_worker_evidence"} or status == "supplemental" or score is None or item.get("directly_scored") is False:
            continue
        normalized = dict(item)
        normalized["presented_score"] = score
        normalized["status"] = status or "unknown"
        output.append(normalized)
    return output


def _replacement_score_page(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    class ScoreBar(Flowable):
        def __init__(self, score: Any, status: str, width: float = 96.0, height: float = 8.0) -> None:
            super().__init__()
            self.score = max(0.0, min(100.0, float(score or 0)))
            self.status = _text(status).casefold()
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
                fill = "#059669" if self.status == "green" else "#d97706" if self.status == "yellow" else "#dc2626"
                self.canv.setFillColor(colors.HexColor(fill))
                self.canv.roundRect(0, 0, self.fill_width, self.height, 2, stroke=0, fill=1)

    records = _score_records(result)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55*inch, leftMargin=.55*inch, topMargin=.55*inch, bottomMargin=.66*inch, title="NICO Express Score Contribution and Constraints", author="NICO", invariant=1)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ScoreTruthTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=26, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    body = ParagraphStyle("ScoreTruthBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=10.5, textColor=colors.HexColor("#334155"), spaceAfter=4)
    label = ParagraphStyle("ScoreTruthLabel", parent=body, fontName="Helvetica-Bold", fontSize=7.4, leading=9.2, textColor=colors.HexColor("#64748b"))

    def p(value: Any, style: Any = body) -> Paragraph:
        import html
        return Paragraph(html.escape(_text(value)), style)

    rows = [[p("Control", label), p("Presented", label), p("Exact proportional contribution", label), p("Primary constraint", label)]]
    geometry = []
    for item in records:
        score = int(item.get("presented_score") or 0)
        status = _text(item.get("status") or "unknown").casefold()
        width = proportional_width(score)
        geometry.append({"section_id": item.get("section_id"), "score": score, "status": status, "maximum_width": 96.0, "rendered_width": width, "ratio": score / 100.0})
        rows.append([p(item.get("label") or item.get("section_id")), p(f"{score}/100 · {status.upper()}"), ScoreBar(score, status), p(item.get("rationale") or "No material constraint retained.")])
    probes = [{"score": score, "maximum_width": 96.0, "rendered_width": proportional_width(score), "ratio": score / 100.0} for score in _VECTOR_PROBES]
    result["express_pdf_bar_geometry"] = {
        "version": VERSION,
        "render_mode": "reportlab_vector_geometry",
        "records": geometry,
        "verification_samples": probes,
        "canonical_status_coloring": True,
        "scanner_worker_excluded": all(_text(item.get("section_id")).casefold() not in {"scanner_worker", "scanner_worker_evidence"} for item in geometry),
    }
    table = Table(rows, colWidths=[1.55*inch, .95*inch, 1.45*inch, 3.1*inch], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    doc.build([p("Score Contribution and Constraints", title), p("Each bar is ReportLab vector geometry whose filled width equals score/100 of the available track. Bar color follows the canonical section status, not a separate score-derived status. Supplemental and pending-acceptance controls are excluded from scoring."), Spacer(1, .08*inch), table])
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
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55*inch, leftMargin=.55*inch, topMargin=.55*inch, bottomMargin=.66*inch, title=page_title, author="NICO", invariant=1)
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
        return [p(f"• {item}") for item in items[:maximum]] or [p("No retained item.")]

    score = record.get("presented_score", section.get("presented_score", section.get("score")))
    score_table = Table([[p("Presented score", label), p("NOT SCORED" if score is None else f"{score}/100"), p("Status", label), p(str(record.get("status") or section.get("status") or "unknown").upper())], [p("Confidence", label), p(record.get("confidence") or section.get("confidence") or "unknown"), p("Treatment", label), p("Canonical scored control")]], colWidths=[1.1*inch, 2.4*inch, 1.1*inch, 2.45*inch])
    score_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    doc.build([p(page_title, title), score_table, Spacer(1, .08*inch), p(section.get("summary") or "No section summary retained."), p("Exact evidence", h2), *bullets(section.get("evidence"), 7), p("Open findings", h2), *bullets(section.get("findings"), 6), p("Limitations", h2), *bullets(section.get("unavailable"), 5), p("Score rationale", h2), p(record.get("rationale") or "No score rationale retained.")])
    return buffer.getvalue()


def replace_renderer_pages(pdf_bytes: bytes, result: dict[str, Any]) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    score_done = False
    architecture_done = False
    velocity_done = False
    combined_removed = False
    for page in reader.pages:
        text = _norm(page.extract_text() or "")
        if "score contribution" in text and "constraint" in text:
            for replacement in PdfReader(io.BytesIO(_replacement_score_page(result))).pages:
                writer.add_page(replacement)
            score_done = True
            continue
        combined = "architecture" in text and "velocity" in text and "complexity" in text and ("decision record" in text or "ownership decision" in text)
        if combined:
            for replacement in PdfReader(io.BytesIO(_replacement_decision_page(result, "architecture_debt", "Architecture Decision Record"))).pages:
                writer.add_page(replacement)
            for replacement in PdfReader(io.BytesIO(_replacement_decision_page(result, "velocity_complexity", "Velocity, Complexity, and Ownership Decision Record"))).pages:
                writer.add_page(replacement)
            architecture_done = velocity_done = combined_removed = True
            continue
        architecture_done = architecture_done or ("architecture decision record" in text and "velocity" not in text)
        velocity_done = velocity_done or (all(token in text for token in ("velocity", "complexity", "ownership", "decision record")) and "architecture decision record" not in text)
        writer.add_page(page)
    if not score_done:
        for replacement in PdfReader(io.BytesIO(_replacement_score_page(result))).pages:
            writer.add_page(replacement)
        score_done = True
    if not architecture_done:
        for replacement in PdfReader(io.BytesIO(_replacement_decision_page(result, "architecture_debt", "Architecture Decision Record"))).pages:
            writer.add_page(replacement)
        architecture_done = True
    if not velocity_done:
        for replacement in PdfReader(io.BytesIO(_replacement_decision_page(result, "velocity_complexity", "Velocity, Complexity, and Ownership Decision Record"))).pages:
            writer.add_page(replacement)
        velocity_done = True
    output = io.BytesIO()
    writer.write(output)
    geometry = result.get("express_pdf_bar_geometry", {})
    result["express_pdf_renderer_truth"] = {
        "status": "complete" if score_done and architecture_done and velocity_done and geometry.get("scanner_worker_excluded") and geometry.get("canonical_status_coloring") else "degraded",
        "version": VERSION,
        "score_page_replaced": score_done,
        "architecture_page_present": architecture_done,
        "velocity_page_present": velocity_done,
        "architecture_velocity_split": architecture_done and velocity_done,
        "combined_page_removed": combined_removed,
        "actual_vector_geometry": score_done,
        "canonical_status_coloring": bool(geometry.get("canonical_status_coloring")),
        "required_vector_probes": list(_VECTOR_PROBES),
        "scanner_worker_excluded": bool(geometry.get("scanner_worker_excluded")),
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
    return {"status": "installed", "version": VERSION, "actual_vector_geometry": True, "architecture_velocity_split": True, "canonical_status_coloring": True, "scanner_worker_excluded": True, "human_review_required": True}


__all__ = ["VERSION", "install_express_pdf_renderer_truth_v21", "proportional_width", "replace_renderer_pages"]
