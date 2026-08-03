from __future__ import annotations

import io
import re
import unicodedata
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.comprehensive_client_ready_projection_v1 import MAX_CLIENT_PDF_PAGES

VERSION = "nico.client-pdf-compose.v3.2"
CORE_REVIEW_COMPANION_PAGES = 24

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
    """Retain the decision body and append bounded client-review artifacts.

    The first 24 review-companion pages contain the evidence posture,
    limitations, and human-decision worksheet for every restored Comprehensive
    section. Later companion pages are action-planning worksheets and may be
    omitted only when a larger legacy/premium base would otherwise exceed the
    45-page client boundary. This keeps all eight review sections while avoiding
    a false failure caused by a harmless difference in base-renderer pagination.
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
    core_review_count = min(CORE_REVIEW_COMPANION_PAGES, review_count)

    # If an unusually long legacy base competes with the decision-review core,
    # keep the cover/decision body only up to the space that preserves all core
    # review pages and the compact register/gate.
    if review is not None:
        max_retained = max(
            0,
            MAX_CLIENT_PDF_PAGES - register_and_gate_count - core_review_count,
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
    if review is not None and len(selected_review_pages) < core_review_count:
        raise ValueError(
            "client-ready PDF cannot preserve the complete Comprehensive review core "
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
