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


def _overlay(
    canonical: Mapping[str, Any],
    spanish: bool,
    size: tuple[float, float],
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    width, _height = size
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=size, invariant=1)
    styles = getSampleStyleSheet()

    def style(
        name: str,
        font: str,
        size: float,
        leading: float,
        color: Any,
    ) -> ParagraphStyle:
        return ParagraphStyle(
            name,
            parent=styles["BodyText"],
            fontName=font,
            fontSize=size,
            leading=leading,
            textColor=color,
        )

    heading = style(
        "fp-heading",
        "Helvetica-Bold",
        8.2,
        9.2,
        colors.HexColor("#0C2740"),
    )
    header = style(
        "fp-header",
        "Helvetica-Bold",
        5.2 if spanish else 5.5,
        6.7,
        colors.white,
    )
    cell = style(
        "fp-cell",
        "Helvetica",
        4.85 if spanish else 5.1,
        5.7,
        colors.HexColor("#243B53"),
    )
    status = style(
        "fp-status",
        "Helvetica-Bold",
        4.85 if spanish else 5.1,
        5.7,
        colors.HexColor("#8A4B08"),
    )
    page.setFillColor(colors.white)
    page.setStrokeColor(colors.HexColor("#AFC5D3"))
    page.roundRect(48, 46, width - 96, 146, 7, fill=1, stroke=1)
    title = Paragraph((_ES if spanish else _EN).upper(), heading)
    title.wrapOn(page, width - 116, 14)
    title.drawOn(page, 58, 175)
    headers = (
        ["Fase", "Alcance", "Estado", "Límite de evidencia"]
        if spanish
        else ["Phase", "Scope", "Status", "Evidence boundary"]
    )
    data = [[Paragraph(item, header) for item in headers]]
    program = canonical.get("four_phase_program")
    program = (
        program
        if isinstance(program, Mapping)
        else build_four_phase_program(canonical)
    )
    for phase in program.get("phases") or []:
        data.append(
            [
                Paragraph(str(phase.get("phase")), cell),
                Paragraph(
                    _text(phase.get("title_es" if spanish else "title_en")),
                    cell,
                ),
                Paragraph(
                    _status(_text(phase.get("status")), spanish),
                    status,
                ),
                Paragraph(
                    _text(
                        phase.get(
                            "evidence_boundary_es"
                            if spanish
                            else "evidence_boundary_en"
                        ),
                        500,
                    ),
                    cell,
                ),
            ]
        )
    table = Table(
        data,
        colWidths=[34, 133, 135, width - 418],
        rowHeights=[13, 25, 25, 25, 25],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2740")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F5F9FC")],
                ),
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


def _page_lines(page: Any) -> list[str]:
    return [
        _text(line, 240)
        for line in str(page.extract_text() or "").splitlines()
        if _text(line, 240)
    ]


def four_phase_target_page_index(reader: Any, *, spanish: bool) -> int:
    """Resolve the real final table-of-contents page, not a pre-navigation index."""

    exact_titles = {"Índice"} if spanish else {"Table of Contents"}
    for index, page in enumerate(reader.pages):
        if any(line in exact_titles for line in _page_lines(page)[:12]):
            return index
    return 1 if len(reader.pages) >= 2 else 0


def _outline_titles(items: Any) -> list[str]:
    output: list[str] = []
    for item in items or []:
        if isinstance(item, list):
            output.extend(_outline_titles(item))
        else:
            output.append(_text(getattr(item, "title", item), 240))
    return output


def _program(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    value = canonical.get("four_phase_program")
    return value if isinstance(value, Mapping) else build_four_phase_program(canonical)


def _phase_bookmark_targets(
    page_count: int,
) -> tuple[tuple[tuple[str, ...], int], ...]:
    return (
        (
            (
                "Review-Required Candidate Register",
                "Registro de candidatos que requieren revisión",
                "Dependency, Security, and Static Analysis",
                "Dependencias, seguridad y análisis estático",
                "Dependency / Library Ecosystem",
                "Ecosistema de dependencias y bibliotecas",
            ),
            min(6, max(0, page_count - 1)),
        ),
        (
            (
                "Human Review and Acceptance Gate",
                "Puerta de revisión humana y aceptación",
                "Review-Required Candidate Register",
                "Registro de candidatos que requieren revisión",
            ),
            max(0, page_count - 3),
        ),
        (
            (
                "Functional QA",
                "QA funcional",
                "Platform Parity",
                "Paridad de plataformas",
                "Historical Trends and Change Failure",
                "Tendencias históricas y fallos de cambio",
            ),
            min(11, max(0, page_count - 1)),
        ),
        (
            (
                "Human Review and Exact-Artifact Approval Record",
                "Registro de revisión humana y aprobación de artefactos exactos",
                "Human Review and Acceptance Gate",
                "Puerta de revisión humana y aceptación",
            ),
            max(0, page_count - 1),
        ),
    )


def assert_four_phase_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    spanish: bool | None = None,
) -> dict[str, Any]:
    """Fail closed unless the final PDF has one TOC matrix and complete bookmarks."""

    from pypdf import PdfReader

    spanish = _spanish(canonical) if spanish is None else spanish
    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("NICO Comprehensive four-phase publication requires a PDF page")

    target_index = four_phase_target_page_index(reader, spanish=spanish)
    marker = _ES if spanish else _EN
    target_text = _text(reader.pages[target_index].extract_text(), 200_000)
    program = _program(canonical)
    phase_titles = [
        _text(phase.get("title_es" if spanish else "title_en"))
        for phase in program.get("phases") or []
    ]
    missing_on_target = [
        value
        for value in (marker, *phase_titles)
        if value.casefold() not in target_text.casefold()
    ]
    if missing_on_target:
        raise ValueError(
            "four-phase PDF table-of-contents publication omitted: "
            + ", ".join(missing_on_target)
        )

    all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if all_text.casefold().count(marker.casefold()) != 1:
        raise ValueError("four-phase PDF matrix must appear exactly once")

    outline_titles = _outline_titles(reader.outline)
    outline_keys = {title.casefold() for title in outline_titles}
    missing_bookmarks = [
        value
        for value in (marker, *phase_titles)
        if value.casefold() not in outline_keys
    ]
    if missing_bookmarks:
        raise ValueError(
            "four-phase PDF bookmarks omitted: " + ", ".join(missing_bookmarks)
        )
    return {
        "target_page_index": target_index,
        "target_page_number": target_index + 1,
        "page_count": len(reader.pages),
        "matrix_count": 1,
        "bookmark_count": len(phase_titles) + 1,
    }


def apply_four_phase_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    spanish: bool | None = None,
) -> bytes:
    """Publish the phase matrix on the final TOC without changing page count."""

    from pypdf import PdfReader, PdfWriter

    spanish = _spanish(canonical) if spanish is None else spanish
    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("NICO Comprehensive four-phase publication requires a PDF page")

    target_index = four_phase_target_page_index(reader, spanish=spanish)
    marker = _ES if spanish else _EN
    program = _program(canonical)
    phase_titles = [
        _text(phase.get("title_es" if spanish else "title_en"))
        for phase in program.get("phases") or []
    ]
    target_text = _text(reader.pages[target_index].extract_text(), 200_000)
    matrix_present = marker.casefold() in target_text.casefold()
    existing_outline = _outline_titles(reader.outline)
    existing_keys = {title.casefold() for title in existing_outline}
    all_bookmarks_present = all(
        value.casefold() in existing_keys for value in (marker, *phase_titles)
    )
    if matrix_present and all_bookmarks_present:
        return pdf

    if not matrix_present:
        target_page = reader.pages[target_index]
        size = (
            float(target_page.mediabox.width),
            float(target_page.mediabox.height),
        )
        overlay = PdfReader(io.BytesIO(_overlay(canonical, spanish, size)))
        target_page.merge_page(overlay.pages[0])

    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    if marker.casefold() not in existing_keys:
        parent = writer.add_outline_item(marker, target_index)
        for phase, (candidates, fallback) in zip(
            program.get("phases") or [],
            _phase_bookmark_targets(len(reader.pages)),
        ):
            page_index = next(
                (
                    index
                    for index, page in enumerate(reader.pages)
                    if index != target_index
                    and any(
                        value.casefold()
                        in _text(page.extract_text(), 30_000).casefold()
                        for value in candidates
                    )
                ),
                fallback,
            )
            writer.add_outline_item(
                _text(phase.get("title_es" if spanish else "title_en")),
                page_index,
                parent=parent,
            )
    else:
        for title in phase_titles:
            if title.casefold() not in existing_keys:
                writer.add_outline_item(title, target_index)

    output = io.BytesIO()
    writer.write(output)
    rendered = output.getvalue()
    assert_four_phase_pdf(rendered, canonical, spanish=spanish)
    return rendered


__all__ = [
    "apply_four_phase_pdf",
    "assert_four_phase_pdf",
    "four_phase_target_page_index",
]
