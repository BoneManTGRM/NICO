from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from nico.comprehensive_pdf_reflow_v1 import (
    _content_lines,
    _preserves_text,
    _render_group,
    compact_sparse_stage_pages,
)


def _source_page(title: str, bullets: list[str], page_number: int, total: int) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=letter, invariant=1)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(40, 760, "NICO Comprehensive · comprun_shipproof · AUTOMATED DRAFT")
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(40, 720, title)
    canvas.setFont("Helvetica", 9)
    y = 690
    for bullet in bullets:
        canvas.drawString(40, y, f"- {bullet}")
        y -= 18
    canvas.drawString(250, 30, f"Document page {page_number} of {total}")
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _join(pdfs: list[bytes]) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for payload in pdfs:
        for page in PdfReader(io.BytesIO(payload)).pages:
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_reflow_preserves_literal_hyphen_bullets_for_truth_gate() -> None:
    source = _source_page(
        "Code audit",
        ["Executable code-risk findings: 0.", "Test paths in tree: 1099."],
        1,
        2,
    )
    second = _source_page(
        "Static Analysis",
        ["Raw candidates: 698.", "Confirmed material findings: 0."],
        2,
        2,
    )
    texts = [page.extract_text() or "" for page in PdfReader(io.BytesIO(_join([source, second]))).pages]
    replacement = _render_group(texts)

    assert _preserves_text(texts, replacement) is True
    replacement_text = " ".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(replacement)).pages
    )
    assert "- Executable code-risk findings: 0." in replacement_text
    assert "- Raw candidates: 698." in replacement_text
    assert _content_lines(texts[0])[1].startswith("-")


def test_sparse_stage_pages_compact_without_truth_loss() -> None:
    payload = _join(
        [
            _source_page("Code audit", ["Executable code-risk findings: 0."], 1, 3),
            _source_page("Static Analysis", ["Raw candidates: 698."], 2, 3),
            _source_page("Velocity / Complexity", ["Architecture score: 78/100."], 3, 3),
        ]
    )

    compacted, proof = compact_sparse_stage_pages(payload)

    assert proof["status"] == "compacted"
    assert proof["truth_preserved"] is True
    assert proof["canonical_truth_mutated"] is False
    assert proof["original_pages"] == 3
    assert proof["final_pages"] < 3
    text = " ".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(compacted)).pages
    )
    assert "- Executable code-risk findings: 0." in text
    assert "- Raw candidates: 698." in text
    assert "- Architecture score: 78/100." in text
