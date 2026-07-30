from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.v2_report_quality_runtime_compat import repair_rendered_report


def _package(title: str) -> dict:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(72, 740, "NICO Comprehensive Technical Assessment")
    pdf.drawString(72, 720, "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED")
    pdf.drawString(72, 700, "comprun_runtime_compat")
    pdf.drawString(72, 680, "a" * 40)
    pdf.showPage()
    pdf.drawString(72, 740, title)
    pdf.drawString(72, 720, "Code Audit 78/100")
    pdf.showPage()
    pdf.save()
    return {
        "json": {
            "identity": {"run_id": "comprun_runtime_compat", "commit_sha": "a" * 40},
            "assessment": {
                "sections": [
                    {
                        "id": "code_audit",
                        "label": "Code Audit",
                        "presented_status": "MODERATE",
                        "presented_score": 78,
                        "summary": "Canonical code evidence was assessed.",
                    }
                ]
            },
        },
        "pdf_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "markdown": "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
        "html": "<html><body>FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED</body></html>",
    }


def test_repairs_restored_premium_scorecard_title() -> None:
    repaired = repair_rendered_report(_package("Technical Scorecard and Weighting"))
    output = base64.b64decode(repaired["pdf_base64"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output)).pages)
    assert "Canonical Technical Scorecard" in text
    assert "Code Audit" in text
    assert "78/100" in text
    assert repaired["premium_report_renderer"]["scorecard_rows_verified"] is True


def test_repairs_canonical_scorecard_title() -> None:
    repaired = repair_rendered_report(_package("Canonical Technical Scorecard"))
    output = base64.b64decode(repaired["pdf_base64"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output)).pages)
    assert text.count("Canonical Technical Scorecard") == 1
    assert "Code Audit" in text
