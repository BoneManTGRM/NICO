from __future__ import annotations

import html
import io
from typing import Any, Iterable, Mapping

from pypdf import PdfReader

from nico.comprehensive_client_review_companion_v5 import SECTION_COUNT

VERSION = "nico.comprehensive-client-review-companion.v7"
SECTIONS_PER_PAGE = 2
COMPANION_PAGE_COUNT = (SECTION_COUNT + SECTIONS_PER_PAGE - 1) // SECTIONS_PER_PAGE
_MARKER = "__nico_comprehensive_review_companion_v7__"


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _unique(
    values: Iterable[Any],
    *,
    limit: int,
    item_limit: int = 430,
) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _text(raw, item_limit)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def render_paired_substantive_review_pdf(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    """Render two complete bounded review worksheets per physical page.

    Every one of the eight substantive sections retains its status, summary,
    evidence, limitations, decision questions, and acceptance record. The layout
    removes unused vertical space only; complete structured evidence remains in
    JSON and CSV artifacts.
    """

    from nico import comprehensive_client_review_companion_v5 as v5
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        KeepInFrame,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    sections = v5.substantive_review_sections(canonical, spanish=spanish)
    if len(sections) != SECTION_COUNT:
        raise ValueError(
            f"Comprehensive review companion requires {SECTION_COUNT} sections, got {len(sections)}"
        )

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "NICOReviewV7Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=10.6,
        leading=12.2,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2,
    )
    heading = ParagraphStyle(
        "NICOReviewV7Heading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=6.6,
        leading=7.6,
        textColor=colors.HexColor("#075985"),
        spaceBefore=1.2,
        spaceAfter=.7,
    )
    body = ParagraphStyle(
        "NICOReviewV7Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=5.8,
        leading=6.7,
        textColor=colors.HexColor("#334155"),
        spaceAfter=.6,
    )
    small = ParagraphStyle(
        "NICOReviewV7Small",
        parent=body,
        fontSize=5.35,
        leading=6.15,
        textColor=colors.HexColor("#475569"),
        spaceAfter=.45,
    )
    warning = ParagraphStyle(
        "NICOReviewV7Warning",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=5.55,
        leading=6.45,
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.45,
        borderPadding=2,
        spaceAfter=1.5,
    )
    boundary = ParagraphStyle(
        "NICOReviewV7Boundary",
        parent=small,
        textColor=colors.HexColor("#475569"),
        backColor=colors.HexColor("#f1f5f9"),
        borderColor=colors.HexColor("#cbd5e1"),
        borderWidth=.35,
        borderPadding=2,
        spaceBefore=.8,
    )

    def p(value: Any, style: ParagraphStyle = body, limit: int = 700) -> Paragraph:
        if not spanish:
            return Paragraph(html.escape(_text(value, limit)), style)
        rendered = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
        if len(rendered) > limit:
            rendered = rendered[: limit - 3].rstrip()
            clause_boundary = max(rendered.rfind("; "), rendered.rfind(". "))
            if clause_boundary >= limit // 2:
                rendered = rendered[:clause_boundary].rstrip(" ·;,:-")
            elif " " in rendered:
                rendered = rendered.rsplit(" ", 1)[0].rstrip(" ·;,:-")
            rendered += "..."
        return Paragraph(html.escape(rendered), style)

    def footer(canvas: Any, doc: Any) -> None:
        page = int(doc.page)
        first = (page - 1) * SECTIONS_PER_PAGE + 1
        last = min(SECTION_COUNT, first + SECTIONS_PER_PAGE - 1)
        canvas.saveState()
        canvas.setFont("Helvetica", 6.3)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            .48 * inch,
            .29 * inch,
            (
                "NICO | revisión integral del cliente | borrador automatizado"
                if spanish
                else "NICO | Comprehensive client review | automated draft"
            ),
        )
        canvas.drawRightString(
            8.02 * inch,
            .29 * inch,
            (
                f"Página de revisión {page} de {COMPANION_PAGE_COUNT} | "
                f"Secciones {first}-{last} de {SECTION_COUNT}"
                if spanish
                else f"Review page {page} of {COMPANION_PAGE_COUNT} | "
                f"Sections {first}-{last} of {SECTION_COUNT}"
            ),
        )
        canvas.restoreState()

    def section_block(section: Mapping[str, Any], section_number: int) -> KeepInFrame:
        evidence = _unique(
            section.get("evidence") or [],
            limit=4,
            item_limit=900 if spanish else 430,
        )
        findings = _unique(section.get("findings") or [], limit=3)
        can_conclude = _unique(section.get("can_conclude") or [], limit=3)
        cannot_conclude = _unique(
            [
                *(section.get("cannot_conclude") or []),
                *(section.get("limitations") or []),
            ],
            limit=4,
        )
        required_input = _unique(section.get("required_input") or [], limit=3)
        questions = _unique(section.get("questions") or [], limit=3)

        content: list[Any] = [
            p(
                f"{section_number}. {section['title']}",
                title,
            ),
            p(
                "BORRADOR AUTOMATIZADO | DECISIÓN HUMANA PENDIENTE | ENTREGA BLOQUEADA"
                if spanish
                else "AUTOMATED DRAFT | HUMAN DECISION PENDING | CLIENT DELIVERY BLOCKED",
                warning,
            ),
        ]
        status_table = Table(
            [
                [p("Estado" if spanish else "Status", small), p(section["status"], small)],
                [
                    p("Resumen" if spanish else "Summary", small),
                    p(section["summary"], small, 800),
                ],
            ],
            colWidths=[.82 * inch, 6.62 * inch],
        )
        status_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), .2, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ]
            )
        )
        content.extend(
            [
                status_table,
                p("Evidencia conservada" if spanish else "Retained evidence", heading),
            ]
        )
        if evidence:
            content.extend(p(f"- {item}", small, 900 if spanish else 430) for item in evidence)
        else:
            content.append(
                p(
                    "- No se conservó evidencia estructurada adicional."
                    if spanish
                    else "- No additional structured evidence was retained.",
                    small,
                )
            )
        if findings:
            content.append(
                p("Observaciones prioritarias" if spanish else "Priority observations", heading)
            )
            content.extend(p(f"- {item}", small, 430) for item in findings)

        left: list[Any] = [
            p("Puede concluirse" if spanish else "What can be concluded", heading)
        ]
        left.extend(p(f"- {item}", small, 430) for item in can_conclude)
        left.append(
            p("No puede concluirse" if spanish else "What cannot be concluded", heading)
        )
        left.extend(p(f"- {item}", small, 430) for item in cannot_conclude)

        right: list[Any] = [
            p("Insumos requeridos del cliente" if spanish else "Required client input", heading)
        ]
        right.extend(p(f"- {item}", small, 430) for item in required_input)
        right.extend(
            [
                p("Decisión recomendada" if spanish else "Recommended decision", heading),
                p(section["recommended_decision"], boundary, 600),
                p("Disposición del revisor" if spanish else "Reviewer disposition", heading),
            ]
        )
        right.extend(p(f"[ ] {item}", small, 430) for item in questions)

        columns = Table(
            [[
                KeepInFrame(3.58 * inch, 1.72 * inch, left, mode="shrink"),
                KeepInFrame(3.58 * inch, 1.72 * inch, right, mode="shrink"),
            ]],
            colWidths=[3.72 * inch, 3.72 * inch],
        )
        columns.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), .2, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), .2, colors.HexColor("#e2e8f0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ]
            )
        )
        content.extend(
            [
                Spacer(1, .015 * inch),
                columns,
                p("Registro de decisión" if spanish else "Decision record", heading),
                p(
                    "Resultado: [ ] aceptar evidencia  [ ] solicitar evidencia  [ ] rechazar conclusión  [ ] diferir"
                    if spanish
                    else "Outcome: [ ] accept evidence  [ ] request evidence  [ ] reject conclusion  [ ] defer",
                    small,
                ),
                p(
                    "Revisor / fecha / evidencia: _________________________________________________"
                    if spanish
                    else "Reviewer / date / acceptance evidence: __________________________________________",
                    small,
                ),
                p(
                    "La disposición de esta sección no autoriza por sí sola la entrega. La evidencia completa permanece en los artefactos estructurados."
                    if spanish
                    else "Section disposition alone does not authorize delivery. Complete retained evidence remains in the structured artifacts.",
                    boundary,
                ),
            ]
        )
        return KeepInFrame(
            7.52 * inch,
            4.42 * inch,
            content,
            mode="shrink",
        )

    story: list[Any] = []
    for index, section in enumerate(sections, start=1):
        story.append(section_block(section, index))
        if index % SECTIONS_PER_PAGE == 1 and index < SECTION_COUNT:
            story.append(Spacer(1, .11 * inch))
        elif index < SECTION_COUNT:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.48 * inch,
        rightMargin=.48 * inch,
        topMargin=.37 * inch,
        bottomMargin=.51 * inch,
        invariant=1,
        title="NICO Comprehensive Client Review",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    reader = PdfReader(io.BytesIO(pdf))
    if len(reader.pages) != COMPANION_PAGE_COUNT:
        raise ValueError(
            "Paired Comprehensive review companion must be exactly "
            f"{COMPANION_PAGE_COUNT} pages, got {len(reader.pages)}."
        )
    for page_number, page in enumerate(reader.pages, start=1):
        text = " ".join((page.extract_text() or "").casefold().split())
        first = (page_number - 1) * SECTIONS_PER_PAGE
        expected = sections[first : first + SECTIONS_PER_PAGE]
        missing = [
            str(section["title"])
            for section in expected
            if _text(section["title"]).casefold() not in text
        ]
        if missing:
            raise ValueError(
                f"paired review page {page_number} omitted section(s): "
                + ", ".join(missing)
            )
        if text.count("decision record" if not spanish else "registro de decisión") < len(expected):
            raise ValueError(
                f"paired review page {page_number} omitted a section decision record"
            )
    return pdf


def install_comprehensive_review_companion_v7() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4
    from nico import comprehensive_client_review_companion_v5 as v5
    from nico import comprehensive_client_review_companion_v6 as v6

    if getattr(completion.render_comprehensive_review_companion_pdf, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "page_count": COMPANION_PAGE_COUNT,
            "section_count": SECTION_COUNT,
            "sections_per_page": SECTIONS_PER_PAGE,
        }

    setattr(render_paired_substantive_review_pdf, _MARKER, True)
    for module in (v2, v3, v4, v5, v6):
        module.render_comprehensive_review_companion_pdf = (
            render_paired_substantive_review_pdf
        )
    v4.COMPANION_PAGE_COUNT = COMPANION_PAGE_COUNT
    v5.COMPANION_PAGE_COUNT = COMPANION_PAGE_COUNT
    v6.COMPANION_PAGE_COUNT = COMPANION_PAGE_COUNT
    completion.render_comprehensive_review_companion_pdf = (
        render_paired_substantive_review_pdf
    )
    return {
        "status": "installed",
        "version": VERSION,
        "page_count": COMPANION_PAGE_COUNT,
        "section_count": SECTION_COUNT,
        "sections_per_page": SECTIONS_PER_PAGE,
        "all_review_sections_retained": True,
        "all_section_decision_records_retained": True,
        "complete_evidence_retained_in_structured_artifacts": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "COMPANION_PAGE_COUNT",
    "SECTIONS_PER_PAGE",
    "VERSION",
    "install_comprehensive_review_companion_v7",
    "render_paired_substantive_review_pdf",
]
