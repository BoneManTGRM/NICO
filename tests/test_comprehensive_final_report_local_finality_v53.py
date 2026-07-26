from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_decision_grade_report_v5 as report_module
from nico.comprehensive_final_report_execution_v1 import wrap_final_report_provider


def _draft_pdf() -> str:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.setFont("Helvetica-Bold", 15)
    page.drawString(42, 720, "NICO Comprehensive Technical Assessment")
    page.setFont("Helvetica", 10)
    page.drawString(42, 690, "DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY NOT AUTHORIZED")
    page.drawString(42, 665, "DELIVERY Draft only")
    page.drawString(42, 640, "Not approved for client delivery")
    page.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _provider(_context):
    boundary = "DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY NOT AUTHORIZED"
    return {
        "status": "complete",
        "reason": "",
        "report_package": {
            "service_id": "comprehensive",
            "report_id": "comprehensive_report_local_finality",
            "markdown": (
                "# NICO Comprehensive Technical Assessment\n\n"
                f"{boundary}\n\nNot approved for client delivery\n"
            ),
            "html": (
                "<html><body><h1>NICO Comprehensive Technical Assessment</h1>"
                f"<p>{boundary}</p><p>Not approved for client delivery</p></body></html>"
            ),
            "json": {
                "service_id": "comprehensive",
                "identity": {"run_id": "comprun_local_finality"},
            },
            "pdf_base64": _draft_pdf(),
            "pdf_error": None,
            "pdf_page_count": 1,
            "canonical_truth_sha256": "a" * 64,
            "delivery_status": "Human Review Required",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_local_finality_rewrites_all_generated_surfaces_without_global_patch() -> None:
    original_builder = report_module.build_comprehensive_report_package

    result = wrap_final_report_provider(_provider)(
        {
            "run_id": "comprun_local_finality",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "evidence_ledger_id": "ledger_local_finality",
            "customer_id": "default_customer",
            "project_id": "default_project",
        }
    )

    package = result["report_package"]
    canonical = package["json"]
    pdf = base64.b64decode(package["pdf_base64"], validate=True)
    pdf_text = " ".join(
        " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages).split()
    )

    assert result["status"] == "complete"
    assert result["local_finality"]["status"] == "complete"
    assert result["report_finality"] == "final"
    assert result["approval_status"] == "pending_human_approval"
    assert result["delivery_status"] == "blocked_pending_human_approval"
    assert package["report_finality"] == "final"
    assert package["approval_status"] == "pending_human_approval"
    assert package["delivery_status"] == "blocked_pending_human_approval"
    assert canonical["report_finality"] == "final"
    assert canonical["approval_status"] == "pending_human_approval"
    assert canonical["delivery_status"] == "blocked_pending_human_approval"
    assert "FINAL REPORT" in package["markdown"].upper()
    assert "PENDING HUMAN APPROVAL" in package["markdown"].upper()
    assert "DRAFT" not in package["markdown"].upper()
    assert "DRAFT" not in package["html"].upper()
    assert "FINAL REPORT" in pdf_text.upper()
    assert "PENDING HUMAN APPROVAL" in pdf_text.upper()
    assert "DRAFT" not in pdf_text.upper()
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert package["human_review_required"] is True
    assert package["client_delivery_allowed"] is False
    assert report_module.build_comprehensive_report_package is original_builder
