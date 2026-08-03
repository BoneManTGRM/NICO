from __future__ import annotations

import html
import io
from typing import Any, Mapping

from nico.comprehensive_client_review_companion_v2 import (
    MAX_CLIENT_REVIEW_PAGES,
    MIN_CLIENT_REVIEW_PAGES,
    merge_review_companion_markdown,
    review_sections,
)

VERSION = "nico.comprehensive-client-review-companion.v3"
COMPANION_PAGE_COUNT = 24
_MARKER = "__nico_comprehensive_review_companion_v3__"


def _text(value: Any, limit: int = 900) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def render_comprehensive_review_companion_pdf(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    """Render exactly three bounded client-review pages for each restored section."""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    sections = review_sections(canonical, spanish=spanish)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "NICOReviewV3Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    heading = ParagraphStyle(
        "NICOReviewV3Heading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#075985"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "NICOReviewV3Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.4,
        leading=11,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "NICOReviewV3Small",
        parent=body,
        fontSize=7.4,
        leading=9.4,
        textColor=colors.HexColor("#475569"),
        spaceAfter=3,
    )
    warning = ParagraphStyle(
        "NICOReviewV3Warning",
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
        "NICOReviewV3Boundary",
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
        canvas.drawString(.55 * inch, .35 * inch, "NICO | Comprehensive client review | automated draft")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Review {doc.page}")
        canvas.restoreState()

    story: list[Any] = []
    total_pages = len(sections) * 3
    page_number = 0

    for section in sections:
        page_number += 1
        story.extend(
            [
                p(section["title"], title),
                p(
                    "BORRADOR AUTOMATIZADO | REVISION HUMANA REQUERIDA"
                    if spanish
                    else "AUTOMATED DRAFT | HUMAN REVIEW REQUIRED",
                    warning,
                ),
            ]
        )
        status_table = Table(
            [
                [p("Estado" if spanish else "Status", small), p(section["status"], small)],
                [p("Resumen" if spanish else "Summary", small), p(section["summary"] or ("No disponible" if spanish else "Unavailable"), small)],
            ],
            colWidths=[1.2 * inch, 6.2 * inch],
        )
        status_table.setStyle(
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
                status_table,
                p("Evidencia conservada" if spanish else "Retained evidence", heading),
            ]
        )
        evidence = section["evidence"] or [
            "No se conservo evidencia estructurada adicional."
            if spanish
            else "No additional structured evidence was retained."
        ]
        for item in evidence[:6]:
            story.append(p(f"- {item}", body, 440))
        story.extend(
            [
                Spacer(1, .08 * inch),
                p(
                    "Esta pagina describe solo la postura automatizada y la evidencia conservada; no representa aceptacion del cliente."
                    if spanish
                    else "This page describes only the automated posture and retained evidence; it does not represent client acceptance.",
                    boundary,
                ),
            ]
        )
        if page_number < total_pages:
            story.append(PageBreak())

        page_number += 1
        story.extend(
            [
                p(
                    f"{section['title']}: " + ("limites e interpretacion" if spanish else "Limits and interpretation"),
                    title,
                ),
                p(
                    "PENDIENTE DE REVISION HUMANA | ENTREGA BLOQUEADA"
                    if spanish
                    else "PENDING HUMAN REVIEW | DELIVERY BLOCKED",
                    warning,
                ),
                p("Observaciones conservadas" if spanish else "Retained observations", heading),
            ]
        )
        findings = section["findings"] or [
            "No se conservo una observacion estructurada adicional."
            if spanish
            else "No additional structured observation was retained."
        ]
        for item in findings[:3]:
            story.append(p(f"- {item}", body, 440))
        story.append(p("Limitaciones conservadas" if spanish else "Retained limitations", heading))
        limitations = section["limitations"] or [
            "No se conservo una limitacion adicional."
            if spanish
            else "No additional limitation was retained."
        ]
        for item in limitations[:6]:
            story.append(p(f"- {item}", body, 440))
        story.extend(
            [
                p("Limite de interpretacion" if spanish else "Interpretation boundary", heading),
                p(
                    "La ausencia de evidencia adicional no constituye una aprobacion, una prueba de paridad, una validacion funcional ni una autorizacion de presupuesto."
                    if spanish
                    else "Absence of additional evidence is not approval, parity proof, functional validation, or budget authorization.",
                    boundary,
                ),
                p(
                    "El revisor debe distinguir hechos retenidos, inferencias, datos no disponibles y decisiones de aceptacion."
                    if spanish
                    else "The reviewer must distinguish retained facts, inferences, unavailable data, and acceptance decisions.",
                    small,
                ),
            ]
        )
        if page_number < total_pages:
            story.append(PageBreak())

        page_number += 1
        story.extend(
            [
                p(
                    f"{section['title']}: " + ("hoja de decision" if spanish else "Review worksheet"),
                    title,
                ),
                p(
                    "DECISION HUMANA PENDIENTE | ENTREGA BLOQUEADA"
                    if spanish
                    else "HUMAN DECISION PENDING | DELIVERY BLOCKED",
                    warning,
                ),
                p("Decisiones del revisor" if spanish else "Reviewer decisions", heading),
            ]
        )
        for item in section["questions"]:
            story.append(p(f"[ ] {item}", body, 520))
        story.extend(
            [
                p("Registro de decision" if spanish else "Decision record", heading),
                p(
                    "Resultado: [ ] aceptar evidencia  [ ] solicitar mas evidencia  [ ] rechazar conclusion  [ ] diferir decision"
                    if spanish
                    else "Outcome: [ ] accept evidence  [ ] request more evidence  [ ] reject conclusion  [ ] defer decision",
                    body,
                ),
                p(
                    "Riesgo residual / responsable / criterio de salida: __________________________________________"
                    if spanish
                    else "Residual risk / owner / exit criterion: ________________________________________________",
                    body,
                ),
                p(
                    "Revisor / fecha / evidencia de aceptacion: _________________________________________________"
                    if spanish
                    else "Reviewer / date / acceptance evidence: _________________________________________________",
                    body,
                ),
                p(
                    "La aprobacion de esta seccion no autoriza por si sola la entrega del paquete completo."
                    if spanish
                    else "Section approval alone does not authorize delivery of the complete package.",
                    boundary,
                ),
            ]
        )
        if page_number < total_pages:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        invariant=1,
        title="NICO Comprehensive Client Review Companion",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if page_count != COMPANION_PAGE_COUNT:
        raise ValueError(
            f"Comprehensive review companion must be exactly {COMPANION_PAGE_COUNT} pages, got {page_count}."
        )
    return pdf


def install_comprehensive_review_companion_v3() -> dict[str, Any]:
    from nico import comprehensive_client_review_companion_v2 as companion
    from nico import client_report_completion_v2 as completion

    if getattr(companion.render_comprehensive_review_companion_pdf, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "page_count": COMPANION_PAGE_COUNT,
            "bound": completion.render_comprehensive_review_companion_pdf is companion.render_comprehensive_review_companion_pdf,
        }

    setattr(render_comprehensive_review_companion_pdf, _MARKER, True)
    companion.render_comprehensive_review_companion_pdf = render_comprehensive_review_companion_pdf
    completion.render_comprehensive_review_companion_pdf = render_comprehensive_review_companion_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "page_count": COMPANION_PAGE_COUNT,
        "bound": completion.render_comprehensive_review_companion_pdf is render_comprehensive_review_companion_pdf,
        "raw_stage_dump_restored": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


from pypdf import PdfReader


__all__ = [
    "COMPANION_PAGE_COUNT",
    "MAX_CLIENT_REVIEW_PAGES",
    "MIN_CLIENT_REVIEW_PAGES",
    "VERSION",
    "install_comprehensive_review_companion_v3",
    "merge_review_companion_markdown",
    "render_comprehensive_review_companion_pdf",
    "review_sections",
]
