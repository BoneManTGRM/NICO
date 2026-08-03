from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_compose_v2 import compose_compact_client_pdf


def _pdf(*pages: list[str]) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    for lines in pages:
        y = 740
        for line in lines:
            document.drawString(45, y, line)
            y -= 16
        document.showPage()
    document.save()
    return output.getvalue()


def test_compose_uses_section_headings_not_incidental_appendix_mentions() -> None:
    base = _pdf(
        [
            "NICO COMPREHENSIVE",
            "The package includes a full evidence appendix in structured exports.",
        ],
        ["Executive Decision Brief", "Useful decision content."],
        [
            "P1 · Reduce complexity · NICO-FINDING-DUPLICATE",
            "Exact source",
            "Implementation sequence",
            "Disposition",
        ],
        ["Evidence Appendix", "raw internal material"],
        ["This page is after the appendix and must never be retained."],
    )
    register = _pdf(["Compact Finding and Remediation Register", "Complete Exact-Source Index"])
    gate = _pdf(["Human Review and Acceptance Gate", "CLIENT DELIVERY BLOCKED"])

    result = compose_compact_client_pdf(base, register, gate)
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 4
    assert "full evidence appendix in structured exports" in extracted
    assert "Useful decision content" in extracted
    assert "NICO-FINDING-DUPLICATE" not in extracted
    assert "raw internal material" not in extracted
    assert "after the appendix" not in extracted
    assert "Complete Exact-Source Index" in extracted
    assert "Human Review and Acceptance Gate" in extracted
