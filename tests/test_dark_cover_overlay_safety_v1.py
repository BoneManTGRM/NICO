from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_incomplete_analyzer_summary_v1 import _overlay_pdf_summary
from nico.comprehensive_report_coverage_synchronization_v63 import _ensure_pdf_coverage_alias
from nico.v2_dark_branded_cover import _cover


def _body_page() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(42, 740, "Executive Decision Brief")
    pdf.save()
    return buffer.getvalue()


def _two_page_report(canonical: dict) -> bytes:
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(_cover(canonical, spanish=False))).pages[0])
    writer.add_page(PdfReader(io.BytesIO(_body_page())).pages[0])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_machine_readable_overlays_preserve_dark_cover_footer() -> None:
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/SARA",
            "commit_sha": "a" * 40,
            "run_id": "comprun_overlay_safety",
        },
        "assessment": {
            "technical_score": 87,
            "evidence_adjusted_score": 75,
            "incomplete_applicable_analyzers": ["eslint"],
        },
        "scanner_execution_records": [
            {"scanner_name": "eslint", "applicable": True, "completed": False},
        ],
    }
    report = _two_page_report(canonical)
    report, inserted = _ensure_pdf_coverage_alias(report, 89, required=True)
    assert inserted == 1
    report = _overlay_pdf_summary(report, canonical, spanish=False)

    reader = PdfReader(io.BytesIO(report))
    cover_text = reader.pages[0].extract_text() or ""
    body_text = reader.pages[1].extract_text() or ""

    assert "analyzer_execution_coverage" not in cover_text
    assert "Incomplete applicable analyzers" not in cover_text
    assert "analyzer_execution_coverage: 89" in body_text
    assert "Incomplete applicable analyzers: 1" in body_text
    assert cover_text.count("AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED") == 1
