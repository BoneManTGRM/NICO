from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.express_not_scored_pdf_append_v35 import VERSION, append_not_scored_page


def _base_pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(72, 720, "NICO Express base report")
    document.save()
    return buffer.getvalue()


def _text(pdf_bytes: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_append_adds_exact_not_scored_controls_without_numeric_placeholders() -> None:
    result = {
        "sections": [
            {
                "id": "scanner_worker",
                "label": "Scanner Worker Evidence",
                "score": 9,
                "status": "supplemental",
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "status": "gray",
            },
        ]
    }

    output = append_not_scored_page(_base_pdf(), result)
    extracted = _text(output)

    assert len(PdfReader(io.BytesIO(output)).pages) == 2
    assert "Scanner Worker Evidence" in extracted
    assert "Client / Human Acceptance" in extracted
    assert extracted.count("NOT SCORED") >= 2
    assert "SUPPLEMENTAL" in extracted
    assert "GRAY" in extracted
    assert "None/100" not in extracted
    assert "0/100" not in extracted
    assert result["express_not_scored_pdf_append"]["status"] == "complete"
    assert result["express_not_scored_pdf_append"]["control_count"] == 2
    assert VERSION == "nico.express_not_scored_pdf_append.v35"


def test_append_is_noop_without_non_scored_controls() -> None:
    source = _base_pdf()
    result = {
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 90,
                "presented_score": 90,
                "status": "green",
                "directly_scored": True,
            }
        ]
    }

    assert append_not_scored_page(source, result) == source
    assert "express_not_scored_pdf_append" not in result
