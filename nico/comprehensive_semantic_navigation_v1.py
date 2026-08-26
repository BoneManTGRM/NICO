from __future__ import annotations

import io
import math
from typing import Any, Callable

VERSION = "nico.comprehensive_semantic_navigation.v1"
_TOC_ROWS_PER_PAGE = 39

# Client-visible semantic navigation. Sparse-page reflow may place several of these
# sections on one physical page; each remains independently navigable and may therefore
# share a page number with other semantic sections.
_EN_SEMANTIC_TITLES = (
    "Comprehensive Technical Assessment",
    "Executive Decision Brief",
    "Priority Constraints and Decision Risks",
    "Canonical Technical Scorecard",
    "Code audit",
    "Code Audit",
    "Dependency / Library Ecosystem",
    "Secrets Exposure Review",
    "Static Analysis",
    "CI/CD Analysis",
    "Architecture & Technical Debt",
    "Velocity / Complexity",
    "Authorization and Scope",
    "Historical Trends and Change Failure",
    "Risk Reduction and Executive Briefing",
    "Executive Risk Register and Decision Briefing",
    "Architecture and Data Flow",
    "CI/CD, Architecture, Complexity, and Velocity",
    "Dependency, Security, and Static Analysis",
    "Developer Delivery Process",
    "Review-Required Candidate Register",
    "CI/CD Operational Readiness and Historical Health",
    "Client Evidence Summary",
    "Functional QA",
    "Platform Parity",
    "Stakeholder and Business Alignment",
    "Requirements Traceability",
    "Six-Month Roadmap",
    "Staffing, Sequencing, and Cost",
    "Compact Finding and Remediation Register",
    "Complete Exact-Source Index",
    "Human Review and Acceptance Gate",
    "Client Artifact Manifest",
    "Human Review and Exact-Artifact Approval Record",
)
_ES_SEMANTIC_TITLES = (
    "Evaluación Técnica Integral",
    "Resumen ejecutivo para decisiones",
    "Restricciones prioritarias y riesgos de decisión",
    "Cuadro de puntuación técnica",
    "Auditoría de código",
    "Ecosistema de dependencias y bibliotecas",
    "Revisión de exposición de secretos",
    "Análisis estático",
    "Análisis de CI/CD",
    "Arquitectura y deuda técnica",
    "Velocidad y complejidad",
    "Autorización y alcance",
    "Tendencias históricas y fallos de cambio",
    "Reducción de riesgo y resumen ejecutivo",
    "Arquitectura y flujo de datos",
    "CI/CD, arquitectura, complejidad y velocidad",
    "Dependencias, seguridad y análisis estático",
    "Proceso de entrega de desarrollo",
    "Registro de candidatos que requieren revisión",
    "Preparación operativa y salud histórica de CI/CD",
    "Resumen de evidencia del cliente",
    "QA funcional",
    "Control de calidad funcional",
    "Paridad de plataformas",
    "Alineación comercial y de partes interesadas",
    "Alineación con partes interesadas y negocio",
    "Trazabilidad de requisitos",
    "Hoja de ruta de seis meses",
    "Personal, secuencia y costo",
    "Registro compacto de hallazgos y remediación",
    "Índice completo de fuentes exactas",
    "Puerta de revisión y aceptación humana",
    "Manifiesto de artefactos del cliente",
    "Registro de revisión humana y aprobación del artefacto exacto",
)
_SEMANTIC_TITLES = tuple(
    dict.fromkeys((*_EN_SEMANTIC_TITLES, *_ES_SEMANTIC_TITLES))
)


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _line_semantic_title(line: str) -> str:
    normalized = _text(line, 180)
    if not normalized:
        return ""
    folded = normalized.casefold()
    for title in _SEMANTIC_TITLES:
        target = title.casefold()
        if folded == target:
            return title
        if folded.startswith(target + " ·") or folded.startswith(target + " |"):
            return title
    return ""


def _semantic_titles_for_page(text: str, fallback: Callable[[str], str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in str(text or "").splitlines():
        title = _line_semantic_title(raw)
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(title)

    primary = _text(fallback(text), 120)
    if primary and primary != "Report page" and primary.casefold() not in seen:
        # Preserve specialized integrity/register pages that are not part of the semantic
        # catalog without allowing the first heading to suppress later headings on the
        # same compacted physical page.
        output.insert(0, primary)
    return output


def semantic_entries(reader: Any, fallback: Callable[[str], str]) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    used: set[str] = set()
    for original_index, page in enumerate(reader.pages[1:], start=1):
        text = page.extract_text() or ""
        for title in _semantic_titles_for_page(text, fallback):
            key = title.casefold()
            if key in used:
                continue
            used.add(key)
            entries.append((title, original_index))
    return entries


def _fit_title(value: str, *, max_width: float, font_name: str, font_size: float) -> str:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    title = _text(value, 140)
    if stringWidth(title, font_name, font_size) <= max_width:
        return title
    while title and stringWidth(title + "...", font_name, font_size) > max_width:
        title = title[:-1]
    return title.rstrip() + "..."


def _toc_pdf(
    entries: list[tuple[str, int]],
    *,
    total_pages: int,
    toc_page_count: int,
    spanish: bool,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setTitle("NICO Table of Contents")
    pdf.setAuthor("NICO")

    chunks = [
        entries[index : index + _TOC_ROWS_PER_PAGE]
        for index in range(0, len(entries), _TOC_ROWS_PER_PAGE)
    ] or [[]]
    for chunk_index, chunk in enumerate(chunks, start=1):
        pdf.setFillColorRGB(0.06, 0.09, 0.16)
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(48, 744, "Tabla de contenido" if spanish else "Table of Contents")
        pdf.setFillColorRGB(0.57, 0.25, 0.04)
        pdf.setFont("Helvetica-Bold", 7)
        boundary = (
            "BORRADOR AUTOMATIZADO | APROBACIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA"
            if spanish
            else "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED"
        )
        pdf.drawString(48, 722, boundary)
        pdf.setStrokeColorRGB(0.80, 0.84, 0.89)
        pdf.line(48, 710, 564, 710)
        pdf.setFillColorRGB(0.20, 0.25, 0.33)
        y = 690
        for title, original_index in chunk:
            final_page_number = original_index + toc_page_count + 1
            fitted = _fit_title(
                title,
                max_width=445,
                font_name="Helvetica",
                font_size=7.7,
            )
            pdf.setFont("Helvetica", 7.7)
            pdf.drawString(54, y, fitted)
            pdf.setFont("Helvetica-Bold", 7.7)
            pdf.drawRightString(558, y, str(final_page_number))
            y -= 15.8
        pdf.setFont("Helvetica", 7)
        pdf.setFillColorRGB(0.39, 0.45, 0.55)
        pdf.drawString(
            48,
            36,
            "NICO | paquete de revisión técnica basado en evidencia"
            if spanish
            else "NICO | evidence-bound technical review package",
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


def semantic_renumber_and_outline(pdf_bytes: bytes) -> bytes:
    """Rebuild page labels, TOC and bookmarks from all semantic headings per page."""

    from pypdf import PdfReader, PdfWriter
    from nico import comprehensive_manifest_navigation_v1 as navigation

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("final Comprehensive PDF contains no pages")

    entries = semantic_entries(reader, navigation._outline_title)
    source_text = "\n".join(page.extract_text() or "" for page in reader.pages[:8])
    spanish = (
        "BORRADOR AUTOMATIZADO" in source_text.upper()
        or any(title in _ES_SEMANTIC_TITLES for title, _ in entries)
    )
    toc_page_count = max(1, math.ceil(len(entries) / _TOC_ROWS_PER_PAGE))
    total_pages = len(reader.pages) + toc_page_count
    toc_reader = PdfReader(
        io.BytesIO(
            _toc_pdf(
                entries,
                total_pages=total_pages,
                toc_page_count=toc_page_count,
                spanish=spanish,
            )
        )
    )
    if len(toc_reader.pages) != toc_page_count:
        raise ValueError("semantic TOC page-count contract failed")

    writer = PdfWriter()
    source_pages: list[tuple[Any, bool]] = [(reader.pages[0], True)]
    source_pages.extend((page, False) for page in toc_reader.pages)
    source_pages.extend((page, True) for page in reader.pages[1:])

    for index, (source, rewrite_labels) in enumerate(source_pages, start=1):
        writer.add_page(source)
        page = writer.pages[-1]
        if rewrite_labels:
            navigation._rewrite_local_page_labels(page, writer)
        overlay = PdfReader(
            io.BytesIO(navigation._page_overlay(index, total_pages))
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

    for title, original_index in entries:
        try:
            writer.add_outline_item(title, original_index + toc_page_count)
        except Exception:
            pass

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


__all__ = [
    "VERSION",
    "semantic_entries",
    "semantic_renumber_and_outline",
]
