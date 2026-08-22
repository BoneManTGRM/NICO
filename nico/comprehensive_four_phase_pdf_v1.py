from __future__ import annotations

import io
from typing import Any, Mapping

from nico.comprehensive_four_phase_model_v1 import (
    _EN,
    _ES,
    _spanish,
    _status,
    _text,
    build_four_phase_program,
)

def _overlay(canonical: Mapping[str, Any], spanish: bool, size: tuple[float, float]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    width, _height = size
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=size, invariant=1)
    styles = getSampleStyleSheet()
    style = lambda name, font, size, leading, color: ParagraphStyle(
        name, parent=styles["BodyText"], fontName=font, fontSize=size, leading=leading, textColor=color
    )
    heading = style("fp-heading", "Helvetica-Bold", 8.2, 9.2, colors.HexColor("#0C2740"))
    header = style("fp-header", "Helvetica-Bold", 5.2 if spanish else 5.5, 6.7, colors.white)
    cell = style("fp-cell", "Helvetica", 4.85 if spanish else 5.1, 5.7, colors.HexColor("#243B53"))
    status = style("fp-status", "Helvetica-Bold", 4.85 if spanish else 5.1, 5.7, colors.HexColor("#8A4B08"))
    page.setFillColor(colors.white)
    page.setStrokeColor(colors.HexColor("#AFC5D3"))
    page.roundRect(48, 46, width - 96, 146, 7, fill=1, stroke=1)
    title = Paragraph((_ES if spanish else _EN).upper(), heading)
    title.wrapOn(page, width - 116, 14)
    title.drawOn(page, 58, 175)
    headers = ["Fase", "Alcance", "Estado", "Límite de evidencia"] if spanish else ["Phase", "Scope", "Status", "Evidence boundary"]
    data = [[Paragraph(item, header) for item in headers]]
    program = canonical.get("four_phase_program")
    program = program if isinstance(program, Mapping) else build_four_phase_program(canonical)
    for phase in program.get("phases") or []:
        data.append(
            [
                Paragraph(str(phase.get("phase")), cell),
                Paragraph(_text(phase.get("title_es" if spanish else "title_en")), cell),
                Paragraph(_status(_text(phase.get("status")), spanish), status),
                Paragraph(_text(phase.get("evidence_boundary_es" if spanish else "evidence_boundary_en"), 500), cell),
            ]
        )
    table = Table(data, colWidths=[34, 133, 135, width - 418], rowHeights=[13, 25, 25, 25, 25])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2740")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F9FC")]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AFC5D3")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    table.wrapOn(page, width - 116, 120)
    table.drawOn(page, 58, 53)
    page.save()
    return buffer.getvalue()


def apply_four_phase_pdf(pdf: bytes, canonical: Mapping[str, Any], *, spanish: bool | None = None) -> bytes:
    from pypdf import PdfReader, PdfWriter

    spanish = _spanish(canonical) if spanish is None else spanish
    reader = PdfReader(io.BytesIO(pdf))
    if len(reader.pages) < 2:
        raise ValueError("NICO Comprehensive PDF requires a table-of-contents page")
    marker = _ES if spanish else _EN
    if marker.casefold() in _text(reader.pages[1].extract_text(), 40000).casefold():
        return pdf
    size = (float(reader.pages[1].mediabox.width), float(reader.pages[1].mediabox.height))
    overlay = PdfReader(io.BytesIO(_overlay(canonical, spanish, size)))
    reader.pages[1].merge_page(overlay.pages[0])
    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    outline_titles: list[str] = []

    def collect(items: Any) -> None:
        for item in items or []:
            if isinstance(item, list):
                collect(item)
            else:
                outline_titles.append(_text(getattr(item, "title", item)).casefold())

    collect(reader.outline)
    if marker.casefold() not in outline_titles:
        parent = writer.add_outline_item(marker, 1)
        markers = (
            ("Review-Required Candidate Register", "Registro de candidatos que requieren revisión"),
            ("Functional QA", "QA funcional"),
            ("Historical Trends and Change Failure", "Tendencias históricas y fallos de cambio"),
            ("Human Review and Acceptance Gate", "Revisión humana y puerta de aceptación"),
        )
        fallbacks = (27, 32, 33, max(1, len(reader.pages) - 3))
        program = canonical.get("four_phase_program")
        program = program if isinstance(program, Mapping) else build_four_phase_program(canonical)
        for phase, pair, fallback in zip(program.get("phases") or [], markers, fallbacks):
            page_index = next(
                (
                    index
                    for index, page in enumerate(reader.pages)
                    if any(value.casefold() in _text(page.extract_text(), 30000).casefold() for value in pair)
                ),
                max(0, min(fallback, len(reader.pages) - 1)),
            )
            writer.add_outline_item(
                _text(phase.get("title_es" if spanish else "title_en")),
                page_index,
                parent=parent,
            )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()



__all__ = ["apply_four_phase_pdf"]
