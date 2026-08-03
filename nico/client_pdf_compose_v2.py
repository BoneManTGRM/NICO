from __future__ import annotations

import io
import re
import unicodedata
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.comprehensive_client_ready_projection_v1 import MAX_CLIENT_PDF_PAGES

VERSION = "nico.client-pdf-compose.v2"


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


def compose_compact_client_pdf(base_pdf: bytes, register_pdf: bytes, gate_pdf: bytes) -> bytes:
    """Retain the decision body, then append one compact register and review gate.

    Heading-bound detection is deliberate. Cover and executive text may mention an
    evidence appendix or review gate without starting those sections; substring
    matching would incorrectly discard the entire decision body.
    """

    if not base_pdf.startswith(b"%PDF"):
        raise ValueError("compact client composition requires a valid base PDF")
    base = PdfReader(io.BytesIO(base_pdf))
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
            ),
        ):
            continue
        if _finding_detail(extracted):
            continue
        retained.append(page)

    writer = PdfWriter()
    for page in retained:
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


__all__ = ["VERSION", "compose_compact_client_pdf"]
