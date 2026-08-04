from __future__ import annotations

import io
import re
import unicodedata
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.comprehensive_client_ready_projection_v1 import MAX_CLIENT_PDF_PAGES

VERSION = "nico.client-pdf-compose.v3.3"
CORE_REVIEW_COMPANION_PAGES = 8

_REVIEW_SECTION_HEADINGS = (
    "functional qa",
    "qa funcional",
    "platform parity",
    "paridad de plataformas",
    "historical trends and change failure",
    "tendencias historicas y fallos de cambio",
    "requirements traceability",
    "trazabilidad de requisitos",
    "stakeholder and business alignment",
    "alineacion comercial y de partes interesadas",
    "risk reduction and executive briefing",
    "reduccion de riesgo y resumen ejecutivo",
    "six-month roadmap",
    "hoja de ruta de seis meses",
    "staffing, sequencing, and cost",
    "personal, secuencia y costo",
)


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.casefold().split())


def _meaningful_lines(value: str) -> list[str]:
    output: list[str] = []
    for raw in str(value or "").splitlines():
        line = _normalized(raw)
        if not line:
            continue
        if line.startswith("nico comprehensive ·"):
            continue
        if re.fullmatch(r"(?:page|pagina) \d+", line):
            continue
        output.append(line)
    return output


def _page_heading(value: str, headings: tuple[str, ...]) -> bool:
    lines = _meaningful_lines(value)
    if not lines:
        return False
    first = lines[0]
    return any(first == heading or first.startswith(f"{heading} ") for heading in headings)


def _finding_detail(value: str) -> bool:
    text = _normalized(value)
    if "nico-finding-" in text and "exact source" in text and (
        "implementation sequence" in text or "disposition" in text
    ):
        return True
    return "nico-code-" in text and "action:" in text and "cyclomatic_complexity" in text


def compose_compact_client_pdf(
    base_pdf: bytes,
    register_pdf: bytes,
    gate_pdf: bytes,
    *,
    review_pdf: bytes | None = None,
) -> bytes:
    """Retain the decision body and every generated client-review page.

    The review companion is compacted at its authoritative renderer. Composition
    must not discard overflow pages that contain retained evidence or a human
    decision worksheet. If the complete decision body, review companion, compact
    register, and approval gate cannot fit within the client boundary, publication
    fails closed instead of silently truncating the package.
    """

    if not base_pdf.startswith(b"%PDF"):
        raise ValueError("compact client composition requires a valid base PDF")
    base = PdfReader(io.BytesIO(base_pdf))
    review = (
        PdfReader(io.BytesIO(review_pdf))
        if review_pdf is not None and review_pdf.startswith(b"%PDF")
        else None
    )
    register = PdfReader(io.BytesIO(register_pdf))
    gate = PdfReader(io.BytesIO(gate_pdf))

    retained: list[Any] = []
    for page in base.pages:
        extracted = page.extract_text() or ""
        if _page_heading(
            extracted,
            (
                "evidence appendix",
                "apendice de evidencia",
            ),
        ):
            break
        if _page_heading(
            extracted,
            (
                "finding and remediation register",
                "registro de hallazgos y remediacion",
                "analyzer applicability and provenance",
                "procedencia y aplicabilidad de analizadores",
                "human review and acceptance gate",
                "puerta de revision humana y aceptacion",
                *_REVIEW_SECTION_HEADINGS,
            ),
        ):
            continue
        if _finding_detail(extracted):
            continue
        retained.append(page)

    register_and_gate_count = len(register.pages) + len(gate.pages)
    review_count = len(review.pages) if review is not None else 0
    required_review_count = review_count

    if review is not None:
        max_retained = max(
            0,
            MAX_CLIENT_PDF_PAGES - register_and_gate_count - required_review_count,
        )
        retained = retained[:max_retained]

    available_review_pages = max(
        0,
        MAX_CLIENT_PDF_PAGES - len(retained) - register_and_gate_count,
    )
    selected_review_pages = (
        list(review.pages[: min(review_count, available_review_pages)])
        if review is not None
        else []
    )
    if review is not None and len(selected_review_pages) != required_review_count:
        raise ValueError(
            "client-ready PDF cannot preserve the complete Comprehensive review companion "
            f"within the {MAX_CLIENT_PDF_PAGES}-page boundary"
        )

    writer = PdfWriter()
    for page in retained:
        writer.add_page(page)
    for page in selected_review_pages:
        writer.add_page(page)
    for page in register.pages:
        writer.add_page(page)
    for page in gate.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if page_count > MAX_CLIENT_PDF_PAGES:
        raise ValueError(
            f"client-ready PDF exceeds the {MAX_CLIENT_PDF_PAGES}-page boundary: {page_count}"
        )
    return pdf


__all__ = [
    "CORE_REVIEW_COMPANION_PAGES",
    "VERSION",
    "compose_compact_client_pdf",
]
