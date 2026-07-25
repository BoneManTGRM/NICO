from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_final_pdf_front_matter_v1 import _replace_first_two_pages


def _pdf(pages: list[str]) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    for text in pages:
        page.drawString(36, 740, text)
        page.showPage()
    page.save()
    return buffer.getvalue()


def test_front_matter_replacement_removes_stale_underlying_text() -> None:
    original = _pdf([
        "OLD FRONT MATTER Final PDF pages: 25 Page 1 of 25",
        "OLD PRODUCT NAME NICO Unified Strategic Assessment Page 2 of 25",
        "Evidence appendix remains unchanged",
    ])
    replacement = _pdf([
        "NICO COMPREHENSIVE Page 1 of 37",
        "Final PDF pages: 37 Page 2 of 37",
    ])

    repaired = _replace_first_two_pages(original, replacement)
    reader = PdfReader(io.BytesIO(repaired))
    first_two = " ".join((reader.pages[index].extract_text() or "") for index in range(2))

    assert len(reader.pages) == 3
    assert "OLD FRONT MATTER" not in first_two
    assert "NICO Unified Strategic Assessment" not in first_two
    assert "Final PDF pages: 25" not in first_two
    assert first_two.count("Final PDF pages:") == 1
    assert "Page 1 of 37" in first_two
    assert "Page 2 of 37" in first_two
    assert "Evidence appendix remains unchanged" in (reader.pages[2].extract_text() or "")


def test_final_pdf_front_matter_installer_is_bound_after_appendices() -> None:
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "nico"
        / "comprehensive_decision_grade_v5.py"
    ).read_text(encoding="utf-8")

    assert "install_comprehensive_code_remediation_appendix_v1()" in source
    assert "install_comprehensive_code_remediation_outline_v1()" in source
    assert "install_comprehensive_final_pdf_front_matter_v1()" in source
    assert source.index("install_comprehensive_final_pdf_front_matter_v1()") > source.index(
        "install_comprehensive_code_remediation_outline_v1()"
    )
