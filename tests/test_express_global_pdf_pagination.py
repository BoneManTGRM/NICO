from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.express_backend_completion_transport import _paginate_express_pdf


def _pdf(page_count: int) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    for page_number in range(1, page_count + 1):
        pdf.drawString(72, 720, f"Body page {page_number}")
        pdf.drawRightString(540, 22, f"Page {page_number} of 15")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_global_pagination_uses_final_artifact_page_count() -> None:
    corrected = _paginate_express_pdf(_pdf(4), {"assessment_type": "express", "locale": "en"})
    reader = PdfReader(io.BytesIO(corrected))

    assert len(reader.pages) == 4
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        assert f"Page {page_number} of 4" in text
        assert f"Page {page_number} of 15" not in text


def test_global_pagination_supports_spanish_page_label() -> None:
    corrected = _paginate_express_pdf(_pdf(2), {"assessment_type": "express", "locale": "es-MX"})
    reader = PdfReader(io.BytesIO(corrected))

    assert len(reader.pages) == 2
    assert "Página 1 of 2" in (reader.pages[0].extract_text() or "")
    assert "Página 2 of 2" in (reader.pages[1].extract_text() or "")
    assert "Page 1 of 15" not in (reader.pages[0].extract_text() or "")
    assert "Page 2 of 15" not in (reader.pages[1].extract_text() or "")


def test_global_pagination_preserves_pdf_structure() -> None:
    corrected = _paginate_express_pdf(_pdf(3), {"run_id": "express_run_fixture"})

    assert corrected.startswith(b"%PDF-")
    assert b"%%EOF" in corrected[-2048:]
    assert len(PdfReader(io.BytesIO(corrected)).pages) == 3
