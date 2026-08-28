from __future__ import annotations

import io
import re
import unicodedata
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.comprehensive_client_ready_projection_v1 import MAX_CLIENT_PDF_PAGES

VERSION = "nico.client-pdf-compose.v3.5"
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

_CI_BOUNDARY_HEADINGS = (
    "ci/cd operational readiness and historical health",
    "preparacion operativa y salud historica de ci/cd",
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


def _optional_pdf_reader(pdf: bytes | None, *, label: str) -> PdfReader | None:
    if pdf is None:
        return None
    if not pdf.startswith(b"%PDF"):
        raise ValueError(f"compact client composition requires a valid {label} PDF")
    return PdfReader(io.BytesIO(pdf))


def compose_compact_client_pdf(
    base_pdf: bytes,
    register_pdf: bytes,
    gate_pdf: bytes,
    *,
    review_pdf: bytes | None = None,
    ci_boundary_pdf: bytes | None = None,
) -> bytes:
    """Retain one cover, the decision body, and every required client page.

    The legacy premium body can contain its own title page after the branded cover
    is applied. That second cover is not evidence and can introduce a second
    generated timestamp, so it is removed here. Review and CI/CD boundary pages
    are reserved before the body budget is calculated and are never silently
    truncated.
    """

    if not base_pdf.startswith(b"%PDF"):
        raise ValueError("compact client composition requires a valid base PDF")
    if not register_pdf.startswith(b"%PDF"):
        raise ValueError("compact client composition requires a valid register PDF")
    if not gate_pdf.startswith(b"%PDF"):
        raise ValueError("compact client composition requires a valid gate PDF")

    base = PdfReader(io.BytesIO(base_pdf))
    review = _optional_pdf_reader(review_pdf, label="review companion")
    ci_boundary = _optional_pdf_reader(ci_boundary_pdf, label="CI/CD boundary")
    register = PdfReader(io.BytesIO(register_pdf))
    gate = PdfReader(io.BytesIO(gate_pdf))

    retained: list[Any] = []
    for page_index, page in enumerate(base.pages):
        extracted = page.extract_text() or ""
        if ci_boundary is not None and _page_heading(
            extracted,
            _CI_BOUNDARY_HEADINGS,
        ):
            # The separately rendered boundary is the authoritative physical
            # edition. Retaining the base copy as well creates two body pages
            # for one semantic section and shifts every later TOC target.
            continue
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
                "puerta de revision y aceptacion humana",
                *_REVIEW_SECTION_HEADINGS,
            ),
        ):
            continue
        if page_index > 0 and _page_heading(
            extracted,
            (
                "comprehensive technical assessment",
                "evaluacion tecnica integral",
            ),
        ):
            # The branded cover is retained as page zero. A second legacy title
            # page has no independent evidence and would create duplicate title,
            # pagination, and generated-at facts.
            continue
        if _finding_detail(extracted):
            continue
        retained.append(page)

    if not retained:
        raise ValueError("client-ready PDF composition removed every primary report page")

    register_and_gate_count = len(register.pages) + len(gate.pages)
    review_count = len(review.pages) if review is not None else 0
    ci_boundary_count = len(ci_boundary.pages) if ci_boundary is not None else 0
    required_review_count = review_count
    required_ci_boundary_count = ci_boundary_count
    reserved_count = (
        register_and_gate_count
        + required_review_count
        + required_ci_boundary_count
    )
    if reserved_count > MAX_CLIENT_PDF_PAGES:
        raise ValueError(
            "client-ready PDF required pages exceed the "
            f"{MAX_CLIENT_PDF_PAGES}-page boundary"
        )

    total_page_count = len(retained) + reserved_count
    if total_page_count > MAX_CLIENT_PDF_PAGES:
        raise ValueError(
            "client-ready PDF cannot preserve every primary and required page within "
            f"the {MAX_CLIENT_PDF_PAGES}-page boundary: {total_page_count}"
        )

    selected_review_pages = list(review.pages) if review is not None else []
    if review is not None and len(selected_review_pages) != required_review_count:
        raise ValueError(
            "client-ready PDF cannot preserve the complete Comprehensive review companion "
            f"within the {MAX_CLIENT_PDF_PAGES}-page boundary"
        )

    selected_ci_boundary_pages = (
        list(ci_boundary.pages) if ci_boundary is not None else []
    )
    if len(selected_ci_boundary_pages) != required_ci_boundary_count:
        raise ValueError(
            "client-ready PDF cannot preserve the complete CI/CD boundary "
            f"within the {MAX_CLIENT_PDF_PAGES}-page boundary"
        )

    writer = PdfWriter()
    for page in retained:
        writer.add_page(page)
    for page in selected_ci_boundary_pages:
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
