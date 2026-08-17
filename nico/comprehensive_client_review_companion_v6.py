from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from pypdf import PdfReader

from nico.comprehensive_client_review_companion_v5 import SECTION_COUNT

VERSION = "nico.comprehensive-client-review-companion.v6.1"
COMPANION_PAGE_COUNT = SECTION_COUNT
_MARKER = "__nico_comprehensive_review_companion_v6__"


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


def merge_compact_substantive_review_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    from nico import comprehensive_client_review_companion_v5 as v5

    output = v5.merge_substantive_review_markdown(
        markdown,
        canonical,
        spanish=spanish,
    )
    # Legacy section extraction could leave a heading token with no label. Such a
    # token has no client meaning and must not survive the final Markdown/HTML.
    output = re.sub(r"(?m)^#{1,6}\s*$\n?", "", output)
    return output.strip() + "\n"


def render_compact_substantive_review_pdf(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    """Render one decision-useful worksheet per Comprehensive review section.

    Complete evidence remains in JSON and CSV. The PDF retains bounded evidence,
    conclusions, limitations, requested input, and the human decision record on
    one physical page per section. The section provider is resolved at execution
    time so the final canonical truth and bounded parity wording installed later
    in the runtime chain are consumed by this renderer.
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
        "NICOReviewV6Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15.2,
        leading=17.6,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )
    heading = ParagraphStyle(
        "NICOReviewV6Heading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10.1,
        textColor=colors.HexColor("#075985"),
        spaceBefore=2.5,
        spaceAfter=1.6,
    )
    body = ParagraphStyle(
        "NICOReviewV6Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.4,
        leading=8.8,
        textColor=colors.HexColor("#334155"),
        spaceAfter=1.5,
    )
    small = ParagraphStyle(
        "NICOReviewV6Small",
        parent=body,
        fontSize=6.9,
        leading=8.15,
        textColor=colors.HexColor("#475569"),
        spaceAfter=1.15,
    )
    warning = ParagraphStyle(
        "NICOReviewV6Warning",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.0,
        leading=8.25,
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.55,
        borderPadding=3.2,
        spaceAfter=3,
    )
    boundary = ParagraphStyle(
        "NICOReviewV6Boundary",
        parent=small,
        textColor=colors.HexColor("#475569"),
        backColor=colors.HexColor("#f1f5f9"),
        borderColor=colors.HexColor("#cbd5e1"),
        borderWidth=.4,
        borderPadding=3,
        spaceBefore=2,
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
        canvas.saveState()
        canvas.setFont("Helvetica", 6.7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            .48 * inch,
            .31 * inch,
            "NICO | Comprehensive client review | automated draft",
        )
        canvas.drawRightString(
            8.02 * inch,
            .31 * inch,
            f"Section {doc.page} of {SECTION_COUNT} | Page 1 of 1",
        )
        canvas.restoreState()

    story: list[Any] = []
    for index, section in enumerate(sections, start=1):
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
            p(section["title"], title),
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
                [p("Resumen" if spanish else "Summary", small), p(section["summary"], small, 800)],
            ],
            colWidths=[1.0 * inch, 6.45 * inch],
        )
        status_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
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
                KeepInFrame(3.58 * inch, 3.55 * inch, left, mode="shrink"),
                KeepInFrame(3.58 * inch, 3.55 * inch, right, mode="shrink"),
            ]],
            colWidths=[3.72 * inch, 3.72 * inch],
        )
        columns.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), .25, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#e2e8f0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        content.extend(
            [
                Spacer(1, .03 * inch),
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
        story.append(
            KeepInFrame(
                7.52 * inch,
                9.55 * inch,
                content,
                mode="shrink",
            )
        )
        if index < SECTION_COUNT:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.48 * inch,
        rightMargin=.48 * inch,
        topMargin=.42 * inch,
        bottomMargin=.55 * inch,
        invariant=1,
        title="NICO Comprehensive Client Review",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if page_count != COMPANION_PAGE_COUNT:
        raise ValueError(
            f"Compact Comprehensive review companion must be exactly {COMPANION_PAGE_COUNT} pages, got {page_count}."
        )
    return pdf


def install_comprehensive_review_companion_v6() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4
    from nico import comprehensive_client_review_companion_v5 as v5

    if getattr(completion.render_comprehensive_review_companion_pdf, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "page_count": COMPANION_PAGE_COUNT,
            "section_count": SECTION_COUNT,
        }

    setattr(render_compact_substantive_review_pdf, _MARKER, True)
    for module in (v2, v3, v4, v5):
        module.merge_review_companion_markdown = merge_compact_substantive_review_markdown
        module.render_comprehensive_review_companion_pdf = render_compact_substantive_review_pdf
    v5.COMPANION_PAGE_COUNT = COMPANION_PAGE_COUNT
    completion.merge_review_companion_markdown = merge_compact_substantive_review_markdown
    completion.render_comprehensive_review_companion_pdf = render_compact_substantive_review_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "page_count": COMPANION_PAGE_COUNT,
        "section_count": SECTION_COUNT,
        "one_review_sheet_per_section": True,
        "complete_evidence_retained_in_structured_artifacts": True,
        "orphan_markdown_headings_removed": True,
        "duplicate_limitation_lines_removed": True,
        "minimum_authored_body_font_points": 6.9,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "COMPANION_PAGE_COUNT",
    "VERSION",
    "install_comprehensive_review_companion_v6",
    "merge_compact_substantive_review_markdown",
    "render_compact_substantive_review_pdf",
]
