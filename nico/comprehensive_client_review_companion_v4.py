from __future__ import annotations

import html
import io
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter

from nico.comprehensive_client_review_companion_v2 import (
    MAX_CLIENT_REVIEW_PAGES,
    MIN_CLIENT_REVIEW_PAGES,
    merge_review_companion_markdown,
    review_sections,
)
from nico.comprehensive_client_review_companion_v3 import (
    render_comprehensive_review_companion_pdf as _render_v3,
)

VERSION = "nico.comprehensive-client-review-companion.v4"
COMPANION_PAGE_COUNT = 32
_MARKER = "__nico_comprehensive_review_companion_v4__"


def _text(value: Any, limit: int = 900) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _render_action_planning_supplement(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    sections = review_sections(canonical, spanish=spanish)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "NICOReviewV4Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    heading = ParagraphStyle(
        "NICOReviewV4Heading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=colors.HexColor("#075985"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "NICOReviewV4Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.3,
        leading=10.8,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "NICOReviewV4Small",
        parent=body,
        fontSize=7.3,
        leading=9.2,
        textColor=colors.HexColor("#475569"),
        spaceAfter=3,
    )
    warning = ParagraphStyle(
        "NICOReviewV4Warning",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.7,
        borderPadding=7,
        spaceAfter=8,
    )
    boundary = ParagraphStyle(
        "NICOReviewV4Boundary",
        parent=small,
        textColor=colors.HexColor("#475569"),
        backColor=colors.HexColor("#f1f5f9"),
        borderColor=colors.HexColor("#cbd5e1"),
        borderWidth=.5,
        borderPadding=6,
        spaceBefore=5,
    )

    def p(value: Any, style: ParagraphStyle = body, limit: int = 900) -> Paragraph:
        return Paragraph(html.escape(_text(value, limit)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .35 * inch, "NICO | Action and acceptance planning | automated draft")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Plan {doc.page}")
        canvas.restoreState()

    story: list[Any] = []
    for index, section in enumerate(sections):
        story.extend(
            [
                p(
                    f"{section['title']}: "
                    + ("plan de accion y aceptacion" if spanish else "Action and acceptance plan"),
                    title,
                ),
                p(
                    "BORRADOR AUTOMATIZADO | NO ES UN COMPROMISO APROBADO"
                    if spanish
                    else "AUTOMATED DRAFT | NOT AN APPROVED COMMITMENT",
                    warning,
                ),
            ]
        )
        posture = Table(
            [
                [p("Estado" if spanish else "Current status", small), p(section["status"], small)],
                [p("Base" if spanish else "Evidence basis", small), p(section["summary"] or ("No disponible" if spanish else "Unavailable"), small)],
            ],
            colWidths=[1.35 * inch, 6.05 * inch],
        )
        posture.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend(
            [
                posture,
                p("Disposicion propuesta" if spanish else "Proposed disposition", heading),
                p(
                    "[ ] aceptar como hecho  [ ] aceptar como riesgo  [ ] solicitar evidencia  [ ] excluir del alcance  [ ] diferir"
                    if spanish
                    else "[ ] accept as fact  [ ] accept as risk  [ ] request evidence  [ ] exclude from scope  [ ] defer",
                    body,
                ),
                p("Plan de accion" if spanish else "Action plan", heading),
                p(
                    "Accion aprobada / responsable: ____________________________________________________________"
                    if spanish
                    else "Approved action / accountable owner: __________________________________________________",
                    body,
                ),
                p(
                    "Dependencias / secuencia: _________________________________________________________________"
                    if spanish
                    else "Dependencies / sequence: ______________________________________________________________",
                    body,
                ),
                p(
                    "Fecha objetivo / presupuesto autorizado: ___________________________________________________"
                    if spanish
                    else "Target date / authorized budget: ______________________________________________________",
                    body,
                ),
                p("Evidencia de aceptacion requerida" if spanish else "Required acceptance evidence", heading),
            ]
        )
        for question in section["questions"]:
            story.append(p(f"[ ] {question}", body, 520))
        story.extend(
            [
                p(
                    "Prueba, artefacto o aprobacion que cerrara esta seccion: _____________________________________"
                    if spanish
                    else "Test, artifact, or approval that will close this section: ________________________________",
                    body,
                ),
                p(
                    "Riesgo residual aceptado por / fecha: _______________________________________________________"
                    if spanish
                    else "Residual risk accepted by / date: _____________________________________________________",
                    body,
                ),
                Spacer(1, .06 * inch),
                p(
                    "Este plan permanece bloqueado hasta que una persona autorizada confirme alcance, responsable, evidencia de salida y presupuesto cuando corresponda."
                    if spanish
                    else "This plan remains blocked until an authorized person confirms scope, owner, exit evidence, and budget where applicable.",
                    boundary,
                ),
            ]
        )
        if index < len(sections) - 1:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        invariant=1,
        title="NICO Comprehensive Action and Acceptance Planning",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if page_count != 8:
        raise ValueError(f"Action-planning supplement must be exactly 8 pages, got {page_count}.")
    return pdf


def render_comprehensive_review_companion_pdf(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    review_pdf = _render_v3(canonical, spanish=spanish)
    planning_pdf = _render_action_planning_supplement(canonical, spanish=spanish)
    writer = PdfWriter()
    for source in (review_pdf, planning_pdf):
        for page in PdfReader(io.BytesIO(source)).pages:
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if page_count != COMPANION_PAGE_COUNT:
        raise ValueError(
            f"Comprehensive review companion must be exactly {COMPANION_PAGE_COUNT} pages, got {page_count}."
        )
    return pdf


def install_comprehensive_review_companion_v4() -> dict[str, Any]:
    from nico import comprehensive_client_review_companion_v2 as companion_v2
    from nico import comprehensive_client_review_companion_v3 as companion_v3
    from nico import client_report_completion_v2 as completion

    if getattr(companion_v2.render_comprehensive_review_companion_pdf, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "page_count": COMPANION_PAGE_COUNT,
            "bound": completion.render_comprehensive_review_companion_pdf is companion_v2.render_comprehensive_review_companion_pdf,
        }

    setattr(render_comprehensive_review_companion_pdf, _MARKER, True)
    companion_v2.render_comprehensive_review_companion_pdf = render_comprehensive_review_companion_pdf
    companion_v3.render_comprehensive_review_companion_pdf = render_comprehensive_review_companion_pdf
    completion.render_comprehensive_review_companion_pdf = render_comprehensive_review_companion_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "page_count": COMPANION_PAGE_COUNT,
        "bound": completion.render_comprehensive_review_companion_pdf is render_comprehensive_review_companion_pdf,
        "raw_stage_dump_restored": False,
        "action_planning_is_approved_commitment": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "COMPANION_PAGE_COUNT",
    "MAX_CLIENT_REVIEW_PAGES",
    "MIN_CLIENT_REVIEW_PAGES",
    "VERSION",
    "install_comprehensive_review_companion_v4",
    "merge_review_companion_markdown",
    "render_comprehensive_review_companion_pdf",
    "review_sections",
]
