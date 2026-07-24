from __future__ import annotations

import base64
import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_native_providers as providers
from nico.comprehensive_cross_format_finality_v49 import (
    VERSION,
    install_comprehensive_cross_format_finality_v49,
)


RUN_ID = "comprun_cross_format_v49"
REPOSITORY = "BoneManTGRM/NICO"
COMMIT_SHA = "a" * 40


def _pdf() -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.drawString(42, 720, "NICO Comprehensive Technical Assessment")
    page.drawString(42, 700, "FINAL REPORT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED")
    page.drawString(42, 680, f"Run ID: {RUN_ID}")
    page.drawString(42, 660, f"Repository: {REPOSITORY}")
    page.drawString(42, 640, f"Commit: {COMMIT_SHA}")
    page.save()
    return buffer.getvalue()


def _context(*, delivery_status: str = "blocked_pending_human_approval") -> dict:
    markdown = (
        "# NICO Comprehensive Technical Assessment\n\n"
        "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n\n"
        f"Run ID: {RUN_ID}\n"
        f"Repository: {REPOSITORY}\n"
        f"Immutable commit SHA: {COMMIT_SHA}\n"
    )
    package = {
        "service_id": "comprehensive",
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": delivery_status,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "markdown": markdown,
        "html": f"<html><body><pre>{markdown}</pre></body></html>",
        "pdf_base64": base64.b64encode(_pdf()).decode("ascii"),
        "canonical_truth_sha256": "b" * 64,
    }
    return {
        "run_id": RUN_ID,
        "repository": REPOSITORY,
        "commit_sha": COMMIT_SHA,
        "evidence_ledger_id": "ledger_cross_format_v49",
        "customer_id": "customer_cross_format_v49",
        "project_id": "project_cross_format_v49",
        "prior_stage_results": {
            "final_comprehensive_report_generation": {
                "status": "complete",
                "report_package": package,
            }
        },
    }


def test_current_final_report_boundary_passes_without_legacy_draft_phrase() -> None:
    install = install_comprehensive_cross_format_finality_v49()
    result = providers.cross_format_verification_provider(_context())

    assert install["bound"] is True
    assert result["status"] == "complete"
    assert result["cross_format_contract_schema"] == VERSION
    assert result["failed_checks"] == []
    assert result["checks"]["final_delivery_boundary_present_in_markdown"] is True
    assert "CLIENT DELIVERY NOT AUTHORIZED" not in _context()["prior_stage_results"]["final_comprehensive_report_generation"]["report_package"]["markdown"]
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_structured_delivery_drift_fails_closed_and_exposes_exact_check() -> None:
    install_comprehensive_cross_format_finality_v49()
    result = providers.cross_format_verification_provider(
        _context(delivery_status="delivery_allowed")
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "cross_format_final_report_verification_failed"
    assert "delivery_status_is_blocked" in result["failed_checks"]
    assert result["checks"]["delivery_status_is_blocked"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_installation_is_idempotent_and_replaces_obsolete_verifier() -> None:
    first = install_comprehensive_cross_format_finality_v49()
    second = install_comprehensive_cross_format_finality_v49()

    assert first["bound"] is True
    assert second["bound"] is True
    assert second["status"] == "already_installed"
    assert second["legacy_draft_phrase_required"] is False
