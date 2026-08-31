from __future__ import annotations

import html
import io
from typing import Any, Iterable, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive_pdf_layout_polish.v1"
_MARKER = "__nico_comprehensive_pdf_layout_polish_v1__"

_TOC_ROWS_PER_PAGE = 35
_TOC_FIRST_ROW_Y = 690.0
_TOC_ROW_PITCH = 14.0
_TOC_FONT_SIZE = 7.5
_TOC_MATRIX_TOP_Y = 192.0
_TOC_MIN_CLEARANCE = 6.0

_REVIEW_TITLE_FONT_SIZE = 12.0
_REVIEW_HEADING_FONT_SIZE = 8.0
_REVIEW_BODY_FONT_SIZE = 7.4
_REVIEW_SMALL_FONT_SIZE = 6.8
_REVIEW_SECTION_HEIGHT_IN = 5.01
_REVIEW_COLUMNS_HEIGHT_IN = 2.18


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


def _toc_last_row_baseline() -> float:
    return _TOC_FIRST_ROW_Y - ((_TOC_ROWS_PER_PAGE - 1) * _TOC_ROW_PITCH)


def _validate_toc_geometry() -> None:
    lowest_text_edge = _toc_last_row_baseline() - _TOC_FONT_SIZE
    required_edge = _TOC_MATRIX_TOP_Y + _TOC_MIN_CLEARANCE
    if lowest_text_edge < required_edge:
        raise ValueError(
            "Comprehensive TOC geometry overlaps the four-phase assessment matrix"
        )


def _render_polished_toc_pdf(
    records: list[dict[str, Any]],
    *,
    total_pages: int,
    toc_page_count: int,
    spanish: bool,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from nico import comprehensive_semantic_navigation_v1 as semantic

    _validate_toc_geometry()
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setTitle("Tabla de contenido de NICO" if spanish else "NICO Table of Contents")
    pdf.setAuthor("NICO")

    chunks = [
        records[index : index + _TOC_ROWS_PER_PAGE]
        for index in range(0, len(records), _TOC_ROWS_PER_PAGE)
    ] or [[]]

    for chunk_index, chunk in enumerate(chunks, start=1):
        pdf.setFillColorRGB(0.06, 0.09, 0.16)
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(48, 744, "Tabla de contenido" if spanish else "Table of Contents")
        pdf.setFillColorRGB(0.57, 0.25, 0.04)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(
            48,
            722,
            (
                "BORRADOR AUTOMATIZADO | APROBACIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA"
                if spanish
                else "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED"
            ),
        )
        pdf.setStrokeColorRGB(0.80, 0.84, 0.89)
        pdf.line(48, 710, 564, 710)
        pdf.setFillColorRGB(0.20, 0.25, 0.33)
        y = _TOC_FIRST_ROW_Y
        for record in chunk:
            title = semantic._fit_title(
                str(record["title"]),
                max_width=445,
                font_name="Helvetica",
                font_size=_TOC_FONT_SIZE,
            )
            final_page_number = int(record["source_page_index"]) + toc_page_count + 1
            pdf.setFont("Helvetica", _TOC_FONT_SIZE)
            pdf.drawString(54, y, title)
            pdf.setFont("Helvetica-Bold", _TOC_FONT_SIZE)
            pdf.drawRightString(558, y, str(final_page_number))
            y -= _TOC_ROW_PITCH

        pdf.setFont("Helvetica", 7)
        pdf.setFillColorRGB(0.39, 0.45, 0.55)
        pdf.drawString(
            48,
            36,
            (
                "NICO | paquete de revisión técnica basado en evidencia"
                if spanish
                else "NICO | evidence-bound technical review package"
            ),
        )
        footer = (
            f"{total_pages} páginas físicas"
            if spanish
            else f"{total_pages} physical pages"
        )
        if toc_page_count > 1:
            footer += (
                f" | contenido {chunk_index}/{toc_page_count}"
                if spanish
                else f" | TOC {chunk_index}/{toc_page_count}"
            )
        pdf.drawRightString(564, 36, footer)
        pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def _render_polished_sparse_group(texts: list[str]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer
    from nico import comprehensive_pdf_reflow_v1 as reflow

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "NICOReflowPolishedHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13.5,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=6,
        spaceAfter=4,
        keepWithNext=True,
    )
    body = ParagraphStyle(
        "NICOReflowPolishedBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.1,
        leading=11.6,
        textColor=colors.HexColor("#334155"),
        spaceAfter=2.5,
        allowWidows=0,
        allowOrphans=0,
    )
    bullet = ParagraphStyle(
        "NICOReflowPolishedBullet",
        parent=body,
        leftIndent=12,
        firstLineIndent=-8,
    )
    eyebrow = ParagraphStyle(
        "NICOReflowPolishedEyebrow",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#b45309"),
        spaceAfter=3,
    )

    story: list[Any] = []
    for page_index, source_text in enumerate(texts):
        lines = reflow._content_lines(source_text)
        if not lines:
            continue
        title = lines[0] if reflow._ordinary_sparse_stage(source_text) else ""
        section_story: list[Any] = []
        if page_index:
            section_story.append(Spacer(1, 0.045 * inch))
        for line_index, line in enumerate(lines):
            escaped = html.escape(line)
            if title and line_index == 0:
                section_story.append(Paragraph(escaped, heading))
            elif "AUTOMATED DRAFT" in line.upper() or "PENDING HUMAN APPROVAL" in line.upper():
                section_story.append(Paragraph(escaped, eyebrow))
            elif line.startswith(("-", "•")):
                section_story.append(Paragraph(escaped, bullet))
            else:
                section_story.append(Paragraph(escaped, body))
        if section_story:
            # Each source section already fit on its original physical page. Keeping the
            # section together prevents a title or final evidence bullets from being
            # stranded on the next compacted page while still allowing an oversized
            # section to split if ReportLab determines it cannot fit on a blank page.
            story.append(KeepTogether(section_story))

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.58 * inch,
        rightMargin=0.58 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.58 * inch,
        title="NICO Comprehensive compact report sections",
        author="NICO",
        invariant=1,
    )
    document.build(story)
    return buffer.getvalue()


def _render_polished_review_pdf(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    from nico import comprehensive_client_review_companion_v5 as v5
    from nico.comprehensive_client_review_companion_v5 import SECTION_COUNT
    from nico.comprehensive_client_review_companion_v7 import (
        COMPANION_PAGE_COUNT,
        SECTIONS_PER_PAGE,
    )
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
        "NICOReviewPolishedTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=_REVIEW_TITLE_FONT_SIZE,
        leading=14.2,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2.0,
    )
    heading = ParagraphStyle(
        "NICOReviewPolishedHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=_REVIEW_HEADING_FONT_SIZE,
        leading=9.4,
        textColor=colors.HexColor("#075985"),
        spaceBefore=1.4,
        spaceAfter=.8,
    )
    body = ParagraphStyle(
        "NICOReviewPolishedBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=_REVIEW_BODY_FONT_SIZE,
        leading=8.8,
        textColor=colors.HexColor("#334155"),
        spaceAfter=.7,
        allowWidows=0,
        allowOrphans=0,
    )
    small = ParagraphStyle(
        "NICOReviewPolishedSmall",
        parent=body,
        fontSize=_REVIEW_SMALL_FONT_SIZE,
        leading=8.1,
        textColor=colors.HexColor("#475569"),
        spaceAfter=.5,
    )
    warning = ParagraphStyle(
        "NICOReviewPolishedWarning",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8.0,
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.45,
        borderPadding=2.2,
        spaceAfter=1.4,
    )
    boundary = ParagraphStyle(
        "NICOReviewPolishedBoundary",
        parent=small,
        textColor=colors.HexColor("#475569"),
        backColor=colors.HexColor("#f1f5f9"),
        borderColor=colors.HexColor("#cbd5e1"),
        borderWidth=.35,
        borderPadding=2.2,
        spaceBefore=.5,
    )

    def paragraph(
        value: Any,
        style: ParagraphStyle = body,
        limit: int = 700,
    ) -> Paragraph:
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
            limit=3,
            item_limit=900 if spanish else 430,
        )
        findings = _unique(section.get("findings") or [], limit=2)
        can_conclude = _unique(section.get("can_conclude") or [], limit=2)
        cannot_conclude = _unique(
            [
                *(section.get("cannot_conclude") or []),
                *(section.get("limitations") or []),
            ],
            limit=3,
        )
        required_input = _unique(section.get("required_input") or [], limit=2)
        questions = _unique(section.get("questions") or [], limit=3)

        content: list[Any] = [
            paragraph(f"{section_number}. {section['title']}", title),
            paragraph(
                "BORRADOR AUTOMATIZADO | DECISIÓN HUMANA PENDIENTE | ENTREGA BLOQUEADA"
                if spanish
                else "AUTOMATED DRAFT | HUMAN DECISION PENDING | CLIENT DELIVERY BLOCKED",
                warning,
            ),
        ]
        status_table = Table(
            [
                [
                    paragraph("Estado" if spanish else "Status", small),
                    paragraph(section["status"], small),
                ],
                [
                    paragraph("Resumen" if spanish else "Summary", small),
                    paragraph(section["summary"], small, 800),
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
                    ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
                ]
            )
        )
        content.extend(
            [
                status_table,
                paragraph("Evidencia conservada" if spanish else "Retained evidence", heading),
            ]
        )
        if evidence:
            content.extend(
                paragraph(f"- {item}", small, 900 if spanish else 430)
                for item in evidence
            )
        else:
            content.append(
                paragraph(
                    "- No se conservó evidencia estructurada adicional."
                    if spanish
                    else "- No additional structured evidence was retained.",
                    small,
                )
            )
        if findings:
            content.append(
                paragraph(
                    "Observaciones prioritarias" if spanish else "Priority observations",
                    heading,
                )
            )
            content.extend(paragraph(f"- {item}", small, 430) for item in findings)

        left: list[Any] = [
            paragraph("Puede concluirse" if spanish else "What can be concluded", heading)
        ]
        left.extend(paragraph(f"- {item}", small, 430) for item in can_conclude)
        left.append(
            paragraph(
                "No puede concluirse" if spanish else "What cannot be concluded",
                heading,
            )
        )
        left.extend(paragraph(f"- {item}", small, 430) for item in cannot_conclude)

        right: list[Any] = [
            paragraph(
                "Insumos requeridos del cliente" if spanish else "Required client input",
                heading,
            )
        ]
        right.extend(paragraph(f"- {item}", small, 430) for item in required_input)
        right.extend(
            [
                paragraph("Decisión recomendada" if spanish else "Recommended decision", heading),
                paragraph(section["recommended_decision"], boundary, 600),
                paragraph("Disposición del revisor" if spanish else "Reviewer disposition", heading),
            ]
        )
        right.extend(paragraph(f"[ ] {item}", small, 430) for item in questions)

        columns = Table(
            [[
                KeepInFrame(
                    3.58 * inch,
                    _REVIEW_COLUMNS_HEIGHT_IN * inch,
                    left,
                    mode="shrink",
                ),
                KeepInFrame(
                    3.58 * inch,
                    _REVIEW_COLUMNS_HEIGHT_IN * inch,
                    right,
                    mode="shrink",
                ),
            ]],
            colWidths=[3.72 * inch, 3.72 * inch],
        )
        columns.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), .2, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), .2, colors.HexColor("#e2e8f0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
                ]
            )
        )
        content.extend(
            [
                Spacer(1, .01 * inch),
                columns,
                paragraph("Registro de decisión" if spanish else "Decision record", heading),
                paragraph(
                    "Resultado: [ ] aceptar evidencia  [ ] solicitar evidencia  [ ] rechazar conclusión  [ ] diferir"
                    if spanish
                    else "Outcome: [ ] accept evidence  [ ] request evidence  [ ] reject conclusion  [ ] defer",
                    small,
                ),
                paragraph(
                    "Revisor / fecha / evidencia: _________________________________________________"
                    if spanish
                    else "Reviewer / date / acceptance evidence: __________________________________________",
                    small,
                ),
                paragraph(
                    "La disposición de esta sección no autoriza por sí sola la entrega. La evidencia completa permanece en los artefactos estructurados."
                    if spanish
                    else "Section disposition alone does not authorize delivery. Complete retained evidence remains in the structured artifacts.",
                    boundary,
                ),
            ]
        )
        return KeepInFrame(
            7.52 * inch,
            _REVIEW_SECTION_HEIGHT_IN * inch,
            content,
            mode="shrink",
        )

    story: list[Any] = []
    for index, section in enumerate(sections, start=1):
        story.append(section_block(section, index))
        if index % SECTIONS_PER_PAGE == 1 and index < SECTION_COUNT:
            story.append(Spacer(1, .06 * inch))
        elif index < SECTION_COUNT:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.48 * inch,
        rightMargin=.48 * inch,
        # Two fixed-height review sections plus their spacer require 10.08 inches.
        # These margins leave 10.133 inches inside ReportLab's padded frame while
        # keeping the footer below the content frame.
        topMargin=.30 * inch,
        bottomMargin=.40 * inch,
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
        extracted = " ".join((page.extract_text() or "").casefold().split())
        first = (page_number - 1) * SECTIONS_PER_PAGE
        expected = sections[first : first + SECTIONS_PER_PAGE]
        missing = [
            str(section["title"])
            for section in expected
            if _text(section["title"]).casefold() not in extracted
        ]
        if missing:
            raise ValueError(
                f"paired review page {page_number} omitted section(s): "
                + ", ".join(missing)
            )
        decision_marker = "registro de decisión" if spanish else "decision record"
        if extracted.count(decision_marker) < len(expected):
            raise ValueError(
                f"paired review page {page_number} omitted a section decision record"
            )
    return pdf


def install_comprehensive_pdf_layout_polish_v1() -> dict[str, Any]:
    """Bind presentation-only PDF layout fixes at the final worker boundary."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4
    from nico import comprehensive_client_review_companion_v5 as v5
    from nico import comprehensive_client_review_companion_v6 as v6
    from nico import comprehensive_client_review_companion_v7 as v7
    from nico import comprehensive_client_review_companion_v7_rebind as rebind
    from nico import comprehensive_pdf_reflow_v1 as reflow
    from nico import comprehensive_semantic_navigation_v1 as semantic

    already_installed = all(
        getattr(value, _MARKER, False)
        for value in (
            semantic._toc_pdf,
            reflow._render_group,
            v7.render_paired_substantive_review_pdf,
        )
    )

    for value in (
        _render_polished_toc_pdf,
        _render_polished_sparse_group,
        _render_polished_review_pdf,
    ):
        setattr(value, _MARKER, True)

    semantic._TOC_ROWS_PER_PAGE = _TOC_ROWS_PER_PAGE
    semantic._toc_pdf = _render_polished_toc_pdf
    reflow._render_group = _render_polished_sparse_group

    v7.render_paired_substantive_review_pdf = _render_polished_review_pdf
    rebind.render_paired_substantive_review_pdf = _render_polished_review_pdf
    for module in (v2, v3, v4, v5, v6):
        module.render_comprehensive_review_companion_pdf = _render_polished_review_pdf
    v6.render_compact_substantive_review_pdf = _render_polished_review_pdf
    completion.render_comprehensive_review_companion_pdf = _render_polished_review_pdf

    _validate_toc_geometry()
    return {
        "artifact_schema": VERSION,
        "status": "already_installed" if already_installed else "installed",
        "bound": True,
        "toc_rows_per_page": _TOC_ROWS_PER_PAGE,
        "toc_single_page_capacity_above_four_phase_matrix": True,
        "toc_last_row_baseline": _toc_last_row_baseline(),
        "sparse_section_keep_together": True,
        "review_companion_pages": v7.COMPANION_PAGE_COUNT,
        "review_sections_per_page": v7.SECTIONS_PER_PAGE,
        "review_body_font_size": _REVIEW_BODY_FONT_SIZE,
        "review_small_font_size": _REVIEW_SMALL_FONT_SIZE,
        "canonical_truth_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_pdf_layout_polish_v1",
]
