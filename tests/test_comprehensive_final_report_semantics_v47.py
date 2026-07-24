from __future__ import annotations

import base64
import io
import json

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_final_report_semantics_v47 import (
    finalize_comprehensive_report_result,
    rewrite_comprehensive_pdf_semantics,
)


def _stale_pdf() -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.setFont("Helvetica-Bold", 18)
    page.drawString(42, 700, "NICO")
    page.drawString(42, 675, "Comprehensive Technical Assessment")
    page.setFont("Helvetica", 10)
    page.drawString(42, 640, "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED")
    page.drawString(42, 610, "Draft only")
    page.drawString(42, 580, "Not approved for client delivery")
    page.drawString(42, 550, "The automated assessment is complete only as a draft.")
    page.drawString(42, 30, "NICO Comprehensive · comprun_test · DRAFT")
    page.save()
    return buffer.getvalue()


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def _package(pdf: bytes) -> dict:
    return {
        "status": "complete",
        "reason": "",
        "report_id": "comprehensive_report_stale",
        "report_package": {
            "service_id": "comprehensive",
            "report_id": "comprehensive_report_stale",
            "markdown": (
                "# NICO Comprehensive Technical Assessment\n\n"
                "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n\n"
                "## Functional QA\n## Platform Parity\n## Six-Month Roadmap\n"
                "## Staffing, Sequencing, and Cost\n## Evidence Appendix\n"
                "## Human Review and Acceptance Gate\n"
            ),
            "html": (
                "<!doctype html><html><body><h1>NICO Comprehensive Technical Assessment</h1>"
                "<p>FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED</p>"
                "</body></html>"
            ),
            "json": {
                "service_id": "comprehensive",
                "identity": {"run_id": "comprun_test", "commit_sha": "a" * 40},
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_filename": "nico-comprehensive-assessment-test-DRAFT.pdf",
            "report_quality_contract": {"decision_grade_body": True},
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_pdf_rewrite_removes_stale_draft_language_and_adds_canonical_title() -> None:
    finalized, contract = rewrite_comprehensive_pdf_semantics(_stale_pdf())
    extracted = _text(finalized)

    assert contract["status"] == "passed"
    assert contract["stale_draft_language_absent"] is True
    assert contract["canonical_title_present"] is True
    assert contract["final_report_language_present"] is True
    assert contract["pending_approval_language_present"] is True
    assert "NICO Comprehensive Technical Assessment" in extracted
    assert "FINAL REPORT" in extracted
    assert "PENDING HUMAN APPROVAL" in extracted
    assert "DRAFT" not in extracted.upper()
    assert "Draft only" not in extracted
    assert "Not approved for client delivery" not in extracted
    assert "complete only as a draft" not in extracted.casefold()


def test_final_report_package_is_final_content_pending_approval_not_draft() -> None:
    result = finalize_comprehensive_report_result(_package(_stale_pdf()))
    package = result["report_package"]
    extracted = _text(base64.b64decode(package["pdf_base64"]))

    assert result["status"] == "complete"
    assert result["reason"] == ""
    assert result["report_finality"] == "final"
    assert result["approval_status"] == "pending_human_approval"
    assert result["delivery_status"] == "blocked_pending_human_approval"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert package["pdf_filename"].endswith("-FINAL-PENDING-APPROVAL.pdf")
    assert "DRAFT" not in package["pdf_filename"].upper()
    assert package["report_quality_contract"]["stale_draft_language_absent"] is True
    assert package["report_quality_contract"]["canonical_comprehensive_title_present"] is True
    assert package["report_quality_contract"]["report_finality"] == "final"
    assert "DRAFT" not in extracted.upper()
    assert len(package["pdf_sha256"]) == 64
    assert len(package["canonical_truth_sha256"]) == 64
    assert package["canonical_truth_sha256"] == result["canonical_truth_sha256"]
    json.dumps(package["json"], sort_keys=True)


def test_semantic_contract_fails_closed_when_required_markdown_title_is_missing() -> None:
    source = _package(_stale_pdf())
    source["report_package"]["markdown"] = "# Wrong report\n\nFINAL REPORT · PENDING HUMAN APPROVAL"

    result = finalize_comprehensive_report_result(source)

    assert result["status"] == "blocked"
    assert result["reason"] == "comprehensive_final_report_semantic_contract_failed"
    assert result["client_delivery_allowed"] is False
    assert result["human_review_required"] is True
