from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status


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


def test_status_sanitizer_removes_internal_dump_pages_and_retains_client_pages() -> None:
    source = _pdf(
        [
            "NICO Comprehensive · comprun_test · FINAL",
            "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
            "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
            "Executive Decision Brief",
        ],
        [
            "Evidence Foundation",
            "Retained Evidence",
            "stage_execution.artifact_schema: internal.v1",
            "report_contract_reason: comprehensive_final_report_semantic_contract_failed",
            "human_evidence_summary.requires_human_review: True",
        ],
        [
            "Compact Finding and Remediation Register",
            "Complete Exact-Source Index",
            "nico/example.py:42",
        ],
        [
            "Human Review and Acceptance Gate",
            "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
        ],
    )

    sanitized = sanitize_client_pdf_status(source)
    reader = PdfReader(io.BytesIO(sanitized))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 3
    assert "report_contract_reason" not in extracted
    assert "comprehensive_final_report_semantic_contract_failed" not in extracted
    assert "stage_execution.artifact_schema" not in extracted
    assert " · FINAL" not in extracted
    assert "FINAL REPORT" not in extracted
    assert extracted.count("AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED") == 2
    assert "Complete Exact-Source Index" in extracted
    assert "Human Review and Acceptance Gate" in extracted
