from __future__ import annotations

import html
import io
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive_pdf_layout_polish.v1"
_MARKER = "__nico_comprehensive_pdf_layout_polish_v1__"

_TOC_FIRST_ROW_Y = 690.0
_TOC_ROW_PITCH = 14.0
_TOC_FONT_SIZE = 7.5
from nico.comprehensive_four_phase_pdf_v1 import PHASE_BOX_TOP_Y

_TOC_MATRIX_TOP_Y = PHASE_BOX_TOP_Y
_TOC_MIN_CLEARANCE = 6.0
_TOC_ROWS_PER_PAGE = int((_TOC_FIRST_ROW_Y - _TOC_FONT_SIZE - _TOC_MATRIX_TOP_Y - _TOC_MIN_CLEARANCE) // _TOC_ROW_PITCH) + 1

_REVIEW_TITLE_FONT_SIZE = 12.0
_REVIEW_HEADING_FONT_SIZE = 9.0
_REVIEW_BODY_FONT_SIZE = 9.0
_REVIEW_SMALL_FONT_SIZE = 9.0


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


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

    # Balance complete entries across the already budgeted pages. The final page
    # owns the phase box; no one-entry continuation is created by a fixed chunk.
    import math
    rows_per_page = max(1, math.ceil(len(records) / toc_page_count))
    if rows_per_page > _TOC_ROWS_PER_PAGE:
        raise ValueError("Contents page budget is too small for legible entries")
    chunks = [records[index:index + rows_per_page]
              for index in range(0, len(records), rows_per_page)] or [[]]

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
            final_page_number = semantic._final_page_index(
                int(record["source_page_index"]), toc_page_count
            ) + 1
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
            f"{total_pages} páginas del informe (sin certificado)"
            if spanish
            else f"{total_pages} report pages (certificate excluded)"
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


def _render_polished_review_pdf(canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
    """Flow the authoritative eight-section projection without further cuts."""
    from pathlib import Path
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Flowable
    from nico import comprehensive_client_review_companion_v5 as v5

    sections = v5.substantive_review_sections(canonical, spanish=spanish)
    if len(sections) != v5.SECTION_COUNT:
        raise ValueError(f"Comprehensive review companion requires {v5.SECTION_COUNT} sections, got {len(sections)}")
    # Private aliases keep this worksheet change out of TOC/matrix typography.
    for name, filename in (("NICOReviewText", "Vera.ttf"), ("NICOReviewBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(Path(reportlab.__file__).parent / "fonts" / filename)))
    body = ParagraphStyle("ReviewBody", fontName="NICOReviewText", fontSize=_REVIEW_BODY_FONT_SIZE,
                          leading=12, spaceAfter=4, splitLongWords=1, allowWidows=0,
                          allowOrphans=0, textColor=colors.HexColor("#334155"))
    title = ParagraphStyle("ReviewTitle", parent=body, fontName="NICOReviewBold",
                           fontSize=_REVIEW_TITLE_FONT_SIZE, leading=16, spaceBefore=12, spaceAfter=6, keepWithNext=True)
    heading = ParagraphStyle("ReviewHeading", parent=body, fontName="NICOReviewBold",
                             spaceBefore=5, keepWithNext=True)
    warning = ParagraphStyle("ReviewWarning", parent=body, fontName="NICOReviewBold",
                             textColor=colors.HexColor("#92400e"), keepWithNext=True)

    def paragraph(value: Any, style: Any = body) -> Paragraph:
        text = str(value)
        glyphs = pdfmetrics.getFont(style.fontName).face.charToGlyph
        unsupported = next((ord(char) for char in text if not char.isspace() and ord(char) not in glyphs), None)
        if unsupported is not None:
            raise ValueError(f"review PDF font cannot preserve Unicode U+{unsupported:04X}")
        return Paragraph(html.escape(text), style)

    class SectionEnd(Flowable):
        def wrap(self, *_args):
            return 0, 0
        def draw(self):
            pass

    class ReviewDocument(SimpleDocTemplate):
        active_section = None
        def afterFlowable(self, flowable):
            if hasattr(flowable, "review_section"):
                self.active_section = flowable.review_section
                self.section_pages.append((self.active_section[1], self.page - 1))
                self.review_structure.append(('section', self.active_section[0]))
            elif hasattr(flowable, "review_decision_section"):
                self.review_structure.append(('decision', flowable.review_decision_section))
            elif isinstance(flowable, SectionEnd):
                self.review_structure.append(('end', self.active_section[0]))
                self.active_section = None

    class CountedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.page_states = []
        def showPage(self):
            self.page_states.append(dict(self.__dict__))
            self._startPage()
        def save(self):
            total = len(self.page_states)
            for state in self.page_states:
                self.__dict__.update(state)
                self.saveState()
                self.setFont("NICOReviewText", 9)
                self.setFillColor(colors.HexColor("#475569"))
                self.drawString(42, 34, "Decisión humana pendiente | Entrega bloqueada" if spanish
                                else "Human decision pending | Client delivery blocked")
                self.drawString(42, 21, "NICO | borrador automatizado" if spanish else "NICO | automated draft")
                self.drawRightString(570, 21, (f"Página de revisión {self._pageNumber} de {total}" if spanish
                                             else f"Review page {self._pageNumber} of {total}"))
                self.restoreState()
                super().showPage()
            super().save()

    def page_header(canvas, doc):
        if doc.active_section is not None:
            section_id, label = doc.active_section
            continuation = "continuación" if spanish else "continued"
            header = paragraph(f"{label} [{section_id}] — {continuation}", heading)
            _, height = header.wrap(528, 60)
            if height > 48:
                raise ValueError("review continuation heading exceeds reserved header space")
            header.drawOn(canvas, 42, 780 - height)

    labels = [
        ("status", "Estado", "Status"), ("summary", "Resumen", "Summary"),
        ("evidence_state", "Estado de evidencia", "Evidence state"),
        ("runtime_observation_established", "Observación de ejecución establecida", "Runtime observation established"),
        ("independently_verified", "Verificado independientemente", "Independently verified"),
        ("resource_evidence_state", "Estado de evidencia de recursos", "Resource evidence state"),
        ("resource_commitment_established", "Compromiso de recursos establecido", "Resource commitment established"),
        ("evidence", "Evidencia conservada", "Retained evidence"),
        ("findings", "Observaciones prioritarias", "Priority observations"),
        ("can_conclude", "Puede concluirse", "What can be concluded"),
        ("cannot_conclude", "No puede concluirse", "What cannot be concluded"),
        ("limitations", "Limitaciones", "Limitations"),
        ("required_input", "Insumos requeridos del cliente", "Required client input"),
        ("recommended_decision", "Decisión recomendada", "Recommended decision"),
        ("questions", "Disposición del revisor", "Reviewer disposition"),
    ]
    story = []
    for index, section in enumerate(sections, 1):
        section_id = str(section["id"])
        section_title = paragraph(f"{index}. {section['title']}", title)
        section_title.review_section = (section_id, str(section["title"]))
        story.extend([section_title, paragraph(
            f"ID: {section_id} | " + (f"Sección {section['section_number']} de {section['section_count']}" if spanish
                                     else f"Section {section['section_number']} of {section['section_count']}")),
            paragraph("BORRADOR AUTOMATIZADO | DECISIÓN HUMANA PENDIENTE | ENTREGA BLOQUEADA" if spanish
                      else "AUTOMATED DRAFT | HUMAN DECISION PENDING | CLIENT DELIVERY BLOCKED", warning)])
        for key, es, en in labels:
            if key not in section:
                continue
            story.append(paragraph(es if spanish else en, heading))
            value = section[key]
            if isinstance(value, (list, tuple)):
                for item in value:
                    story.append(paragraph(("[ ] " if key == "questions" else "- ") + str(item)))
            else:
                story.append(paragraph(str(value).lower() if isinstance(value, bool) else value))
        decision_heading = paragraph("Registro de decisión" if spanish else "Decision record", heading)
        decision_heading.review_decision_section = section_id
        story.extend([
            decision_heading,
            paragraph("Resultado: [ ] aceptar evidencia  [ ] solicitar evidencia  [ ] rechazar conclusión  [ ] diferir" if spanish
                      else "Outcome: [ ] accept evidence  [ ] request evidence  [ ] reject conclusion  [ ] defer"),
            paragraph("Revisor / fecha / evidencia: _________________________________________________" if spanish
                      else "Reviewer / date / acceptance evidence: __________________________________________"),
            paragraph("La disposición de esta sección no autoriza por sí sola la entrega. La evidencia completa permanece en los artefactos estructurados." if spanish
                      else "Section disposition alone does not authorize delivery. Complete retained evidence remains in the structured artifacts."),
            SectionEnd(), Spacer(1, 8),
        ])
    buffer = io.BytesIO()
    document = ReviewDocument(buffer, pagesize=letter, leftMargin=42, rightMargin=42,
                              topMargin=72, bottomMargin=48, invariant=1,
                              title="NICO Comprehensive Client Review", author="NICO")
    document.section_pages = []
    document.review_structure = []
    document.build(story, onFirstPage=page_header, onLaterPages=page_header, canvasmaker=CountedCanvas)
    # Validate renderer-owned flowables after layout, not unrestricted evidence
    # text: user evidence may legitimately quote the decision-record heading.
    expected_structure = [(kind, str(section['id'])) for section in sections
                          for kind in ('section', 'decision', 'end')]
    if document.review_structure != expected_structure:
        raise ValueError("flowing review omitted or reordered a section decision record")
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(buffer.getvalue())), import_outline=False)
    for label, page_index in document.section_pages:
        writer.add_outline_item(label, page_index)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    reader = PdfReader(io.BytesIO(pdf))
    text = " ".join(" ".join(page.extract_text() or "" for page in reader.pages).split())
    cursor = 0
    for section in sections:
        marker = f"ID: {section['id']}"
        position = text.find(marker, cursor)
        if position < 0:
            raise ValueError(f"flowing review omitted or reordered section: {section['id']}")
        cursor = position + len(marker)
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

    setattr(_render_polished_review_pdf, "_nico_review_flowing", True)
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
        "review_companion_pages": "content_dependent",
        "review_section_count": v5.SECTION_COUNT,
        "review_continuation_pages": True,
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
