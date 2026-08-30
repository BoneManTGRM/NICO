from __future__ import annotations

import io
import math
import re
from typing import Any, Mapping

from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS

VERSION = "nico.comprehensive_semantic_navigation.v1.4"
_TOC_ROWS_PER_PAGE = 39

# Known historic/localized heading variants are recognition aliases only.
# Presentation labels always come from the canonical semantic manifest.
_TITLE_ALIASES_BY_SECTION_ID: dict[str, tuple[str, ...]] = {
    "dependency_library_ecosystem": ("Ecosistema de dependencias",),
    "secrets_exposure_review": ("Revisión de secretos",),
    "functional_qa": ("Control de calidad funcional",),
    "stakeholder_business_alignment": (
        "Alineación con partes interesadas y negocio",
    ),
    "dependency_security_static_analysis": (
        "Análisis de dependencias, seguridad y análisis estático",
    ),
    "human_review_acceptance_gate": (
        "Puerta de revisión y aceptación humana",
        "Revisión humana y aceptación",
    ),
    "human_review_exact_artifact_approval": (
        "Registro de revisión humana y aprobación del artefacto exacto",
    ),
}

_NUMBERED_HEADING = re.compile(r"^\s*\d+\.\s*")
_SUFFIXES = (" ·", " |", " —", " -", ":")
_SPANISH_MARKERS = (
    "BORRADOR AUTOMATIZADO",
    "APROBACIÓN HUMANA PENDIENTE",
    "ENTREGA AL CLIENTE BLOQUEADA",
    "TABLA DE CONTENIDO",
    "PÁGINA DEL DOCUMENTO",
)
_TECHNICAL_SCORECARD_SECTION_IDS = {
    "code_audit",
    "dependency_library_ecosystem",
    "secrets_exposure_review",
    "static_analysis",
    "ci_cd_analysis",
    "architecture_technical_debt",
    "velocity_complexity",
}
_TECHNICAL_SCORECARD_PAGE_MARKERS = (
    "canonical technical scorecard",
    "cuadro de puntuación técnica",
)
_SCORECARD_PLAIN_STATUS = re.compile(
    r"^(?:"
    r"strong|moderate|weak|exceptional|pending|not\s+scored|"
    r"provisional\s+(?:strong|moderate)|"
    r"sólido|solido|moderado|débil|debil|excepcional|pendiente|"
    r"no\s+calificado|provisional\s+(?:sólido|solido|moderado)"
    r")(?:\s+[—-])?(?:\s+\d{1,3}(?:\.\d+)?(?:/100)?)?$",
    re.I,
)
_SCORECARD_PLAIN_SCORE = re.compile(r"^\d{1,3}(?:\.\d+)?(?:/100)?$", re.I)


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _spanish_document(reader: Any) -> bool:
    sample = "\n".join(
        (reader.pages[index].extract_text() or "")
        for index in range(min(10, len(reader.pages)))
    ).upper()
    return any(marker in sample for marker in _SPANISH_MARKERS)


def _canonical_sections() -> tuple[Mapping[str, Any], ...]:
    return tuple(CANONICAL_TOC_SECTIONS)


def _section_aliases(section: Mapping[str, Any]) -> tuple[str, ...]:
    values = [
        _text(section.get("title_en"), 240),
        _text(section.get("title_es"), 240),
        *_TITLE_ALIASES_BY_SECTION_ID.get(_text(section.get("section_id"), 120), ()),
    ]
    return tuple(value for value in dict.fromkeys(values) if value)


def _heading_candidate(raw_line: str) -> tuple[str, bool]:
    normalized = _text(raw_line, 400)
    if not normalized:
        return "", False
    numbered = bool(_NUMBERED_HEADING.match(normalized))
    return _NUMBERED_HEADING.sub("", normalized).strip(), numbered


def _visible_heading_match(candidate: str, marker: str) -> bool:
    folded = candidate.casefold()
    target = _text(marker, 300).casefold()
    if not target:
        return False
    if folded == target:
        return True
    return any(folded.startswith(target + suffix.casefold()) for suffix in _SUFFIXES)


def _section_for_line(raw_line: str) -> tuple[Mapping[str, Any], bool] | None:
    candidate, numbered = _heading_candidate(raw_line)
    if not candidate:
        return None
    for section in _canonical_sections():
        if any(
            _visible_heading_match(candidate, alias)
            for alias in _section_aliases(section)
        ):
            return section, numbered
    return None


def _section_for_visible_heading(
    lines: list[str],
    line_index: int,
) -> tuple[Mapping[str, Any], bool, int] | None:
    """Recognize one heading, including a bounded adjacent-line visual wrap."""

    direct = _section_for_line(lines[line_index])
    if direct is not None:
        section, numbered = direct
        return section, numbered, line_index

    joined = _text(lines[line_index], 400)
    if not joined:
        return None
    for cursor in range(line_index + 1, min(len(lines), line_index + 3)):
        following = _text(lines[cursor], 240)
        if not following:
            break
        joined = f"{joined} {following}"
        wrapped = _section_for_line(joined)
        if wrapped is not None:
            section, numbered = wrapped
            return section, numbered, cursor
    return None


def _scorecard_table_followup(next_nonempty: str) -> bool:
    """Return True when the next line looks like compact scorecard-cell content.

    Real semantic control sections in NICO use richer status lines such as
    ``STRONG · 96/100`` or ``PROVISIONAL STRONG · HUMAN REVIEW REQUIRED``. Scorecard
    table rows use plain status/score cells, and the final row may have no following
    extracted line at all. Treat only those bounded forms as table context so a real
    compacted section on the same physical page remains eligible for navigation.
    """

    normalized = _text(next_nonempty, 180).strip().rstrip(".")
    if not normalized:
        return True
    return bool(
        _SCORECARD_PLAIN_STATUS.fullmatch(normalized)
        or _SCORECARD_PLAIN_SCORE.fullmatch(normalized)
    )


def _occurrence_quality(
    *,
    raw_line: str,
    numbered: bool,
    next_nonempty: str,
) -> tuple[int, int]:
    candidate, _ = _heading_candidate(raw_line)
    exact_without_status = 1
    for suffix in _SUFFIXES:
        if suffix.casefold() in candidate.casefold():
            exact_without_status = 0
            break
    boundary_after = (
        3
        if (
            "AUTOMATED DRAFT" in next_nonempty.upper()
            or "BORRADOR AUTOMATIZADO" in next_nonempty.upper()
        )
        else 0
    )
    return boundary_after + (2 if numbered else 0) + exact_without_status, int(numbered)


def semantic_entry_records(reader: Any) -> tuple[list[dict[str, Any]], bool]:
    """Discover one canonical navigation target per semantic section.

    All recognition is governed by ``CANONICAL_TOC_SECTIONS``. Several semantic
    sections may intentionally resolve to one physical source page. When a section is
    rendered more than once, a dedicated client-review/supplement occurrence is preferred
    over an earlier summary occurrence; ties resolve to the earliest source location.
    """

    spanish = _spanish_document(reader)
    occurrences: dict[str, list[dict[str, Any]]] = {}

    for source_index, page in enumerate(reader.pages):
        if source_index == 0:
            continue
        page_text = page.extract_text() or ""
        lines = [line for line in page_text.splitlines()]
        page_folded = page_text.casefold()
        for line_index, raw_line in enumerate(lines):
            match = _section_for_visible_heading(lines, line_index)
            if match is None:
                continue
            section, numbered, heading_end_index = match
            section_id = _text(section.get("section_id"), 120)
            if not section_id:
                continue
            next_nonempty = ""
            for following in lines[heading_end_index + 1 :]:
                if _text(following):
                    next_nonempty = _text(following, 300)
                    break
            if (
                any(marker in page_folded for marker in _TECHNICAL_SCORECARD_PAGE_MARKERS)
                and section_id in _TECHNICAL_SCORECARD_SECTION_IDS
                and _scorecard_table_followup(next_nonempty)
            ):
                # Scorecard table cells repeat control names. Do not let those cells steal
                # navigation from a real semantic heading, including when a last scorecard
                # row has no following extracted status cell. Rich section-status lines are
                # intentionally not classified as scorecard-cell follow-up, so safe
                # compaction may still place a real section on this same physical page.
                continue
            quality, numbered_score = _occurrence_quality(
                raw_line=raw_line,
                numbered=numbered,
                next_nonempty=next_nonempty,
            )
            occurrences.setdefault(section_id, []).append(
                {
                    "section_id": section_id,
                    "title": _text(
                        section.get("title_es") if spanish else section.get("title_en"),
                        240,
                    ),
                    "source_page_index": source_index,
                    "source_line_index": line_index,
                    "quality": quality,
                    "numbered_score": numbered_score,
                }
            )

    chosen: list[dict[str, Any]] = []
    manifest_order = {
        _text(section.get("section_id"), 120): index
        for index, section in enumerate(_canonical_sections())
    }
    for section in _canonical_sections():
        section_id = _text(section.get("section_id"), 120)
        candidates = occurrences.get(section_id) or []
        if not candidates:
            continue
        # Higher quality means a dedicated review/supplement heading is preferred.
        # Earlier source location is the deterministic tie-breaker.
        best = sorted(
            candidates,
            key=lambda item: (
                -int(item["quality"]),
                int(item["source_page_index"]),
                int(item["source_line_index"]),
            ),
        )[0]
        chosen.append(dict(best))

    chosen.sort(
        key=lambda item: (
            int(item["source_page_index"]),
            int(item["source_line_index"]),
            manifest_order.get(str(item["section_id"]), 10_000),
        )
    )
    return chosen, spanish


def semantic_entries(reader: Any, _fallback: Any = None) -> list[tuple[str, int]]:
    """Compatibility view: ``(localized title, zero-based source page index)``."""

    records, _spanish = semantic_entry_records(reader)
    return [
        (str(record["title"]), int(record["source_page_index"]))
        for record in records
    ]


def _fit_title(value: str, *, max_width: float, font_name: str, font_size: float) -> str:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    title = _text(value, 180)
    if stringWidth(title, font_name, font_size) <= max_width:
        return title
    while title and stringWidth(title + "...", font_name, font_size) > max_width:
        title = title[:-1]
    return title.rstrip() + "..."


def _toc_pdf(
    records: list[dict[str, Any]],
    *,
    total_pages: int,
    toc_page_count: int,
    spanish: bool,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

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
        y = 690
        for record in chunk:
            title = _fit_title(
                str(record["title"]),
                max_width=445,
                font_name="Helvetica",
                font_size=7.7,
            )
            final_page_number = (
                int(record["source_page_index"]) + toc_page_count + 1
            )
            pdf.setFont("Helvetica", 7.7)
            pdf.drawString(54, y, title)
            pdf.setFont("Helvetica-Bold", 7.7)
            pdf.drawRightString(558, y, str(final_page_number))
            y -= 15.8

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


def _page_overlay(
    page_number: int,
    total_pages: int,
    *,
    spanish: bool,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillGray(0.42)
    pdf.drawCentredString(
        letter[0] / 2,
        16,
        (
            f"Página del documento {page_number} de {total_pages}"
            if spanish
            else f"Document page {page_number} of {total_pages}"
        ),
    )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _remove_existing_toc(reader: Any) -> list[Any]:
    """Defensively avoid stacking a second generated TOC on reprocessing.

    Normal production input reaches this function before final navigation exists. This
    guard is only for safe artifact regeneration/recovery paths.
    """

    pages = list(reader.pages)
    if len(pages) < 2:
        return pages
    body_start = 1
    while body_start < len(pages):
        text = (pages[body_start].extract_text() or "").casefold()
        if "table of contents" not in text and "tabla de contenido" not in text:
            break
        body_start += 1
    if body_start > 1:
        return [pages[0], *pages[body_start:]]
    return pages


def semantic_renumber_and_outline(pdf_bytes: bytes) -> bytes:
    """Rebuild final TOC, bookmarks and physical page labels from semantic sections."""

    from pypdf import PdfReader, PdfWriter
    from nico import comprehensive_manifest_navigation_v1 as navigation

    initial_reader = PdfReader(io.BytesIO(pdf_bytes))
    if not initial_reader.pages:
        raise ValueError("final Comprehensive PDF contains no pages")

    source_pages = _remove_existing_toc(initial_reader)
    if len(source_pages) != len(initial_reader.pages):
        source_buffer = io.BytesIO()
        source_writer = PdfWriter()
        for page in source_pages:
            source_writer.add_page(page)
        source_writer.write(source_buffer)
        reader = PdfReader(io.BytesIO(source_buffer.getvalue()))
    else:
        reader = initial_reader

    records, spanish = semantic_entry_records(reader)
    if not records:
        raise ValueError(
            "final Comprehensive PDF contains no canonical semantic navigation sections"
        )

    toc_page_count = max(1, math.ceil(len(records) / _TOC_ROWS_PER_PAGE))
    total_pages = len(reader.pages) + toc_page_count
    toc_reader = PdfReader(
        io.BytesIO(
            _toc_pdf(
                records,
                total_pages=total_pages,
                toc_page_count=toc_page_count,
                spanish=spanish,
            )
        )
    )
    if len(toc_reader.pages) != toc_page_count:
        raise ValueError("semantic TOC page-count contract failed")

    writer = PdfWriter()
    assembled: list[tuple[Any, bool]] = [(reader.pages[0], True)]
    assembled.extend((page, False) for page in toc_reader.pages)
    assembled.extend((page, True) for page in reader.pages[1:])

    for index, (source, rewrite_labels) in enumerate(assembled, start=1):
        writer.add_page(source)
        page = writer.pages[-1]
        if rewrite_labels:
            navigation._rewrite_local_page_labels(page, writer)
        overlay = PdfReader(
            io.BytesIO(
                _page_overlay(
                    index,
                    total_pages,
                    spanish=spanish,
                )
            )
        ).pages[0]
        page.merge_page(overlay, over=True)

    for toc_index in range(toc_page_count):
        try:
            if spanish:
                title = (
                    "Tabla de contenido"
                    if toc_index == 0
                    else f"Tabla de contenido {toc_index + 1}"
                )
            else:
                title = (
                    "Table of Contents"
                    if toc_index == 0
                    else f"Table of Contents {toc_index + 1}"
                )
            writer.add_outline_item(title, 1 + toc_index)
        except Exception:
            pass

    for record in records:
        try:
            writer.add_outline_item(
                str(record["title"]),
                int(record["source_page_index"]) + toc_page_count,
            )
        except Exception:
            pass

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


__all__ = [
    "VERSION",
    "semantic_entries",
    "semantic_entry_records",
    "semantic_renumber_and_outline",
]
