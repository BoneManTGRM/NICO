"""Primary-page references to findings must not be mistaken for finding cards."""
from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_compose_v2 import compose_compact_client_pdf
from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY


LOCALES = (
    ("Detailed Findings Register", "Six-Month Execution Roadmap", EN_BOUNDARY),
    ("Registro detallado de hallazgos", "Hoja de ruta de ejecución de seis meses", ES_BOUNDARY),
)
REFERENCES = (
    "NICO-CODE-001 Action: review the cyclomatic_complexity work package.",
    "NICO-FINDING-001 Exact source reference; disposition remains pending.",
)


def _pdf(pages: list[list[str]], boundary: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    for lines in pages:
        document.setFont("Helvetica", 8)
        document.drawString(40, 24, boundary)
        for index, line in enumerate(lines):
            document.drawString(40, 740 - index * 16, line)
        document.showPage()
    document.save()
    return buffer.getvalue()


@pytest.mark.parametrize("register,primary,boundary", LOCALES)
@pytest.mark.parametrize("reference", REFERENCES)
@pytest.mark.parametrize("known_heading", (True, False))
def test_primary_page_after_register_retains_finding_references(
    register: str, primary: str, boundary: str, reference: str, known_heading: bool,
) -> None:
    heading = primary if known_heading else "Project-specific primary work package"
    base = _pdf([
        ["Cover"], [register], ["P2 · Superseded legacy finding"],
        [heading, "PRIMARY-WORK-PACKAGE-REQUIRED", reference],
    ], boundary)
    result = compose_compact_client_pdf(
        base, _pdf([["Canonical register retained"]], boundary),
        _pdf([["Human review pending; delivery blocked"]], boundary),
    )
    pages = PdfReader(io.BytesIO(result)).pages
    text = "\n".join(page.extract_text() or "" for page in pages)
    assert "PRIMARY-WORK-PACKAGE-REQUIRED" in text
    assert reference in text
    assert heading in text
    assert "Superseded legacy finding" not in text
    assert "Canonical register retained" in text
    assert "Human review pending; delivery blocked" in text
    assert boundary in (pages[1].extract_text() or "")
    assert len(pages) == 4


def test_standalone_legacy_finding_card_is_still_replaced() -> None:
    result = compose_compact_client_pdf(
        _pdf([["Cover"], [REFERENCES[0], "Standalone legacy card"]], EN_BOUNDARY),
        _pdf([["Canonical register retained"]], EN_BOUNDARY),
        _pdf([["Human review pending; delivery blocked"]], EN_BOUNDARY),
    )
    reader = PdfReader(io.BytesIO(result))
    assert len(reader.pages) == 3
    assert "Standalone legacy card" not in "\n".join(page.extract_text() or "" for page in reader.pages)
