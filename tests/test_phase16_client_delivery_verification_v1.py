from __future__ import annotations

import base64

import pytest

from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_STATUS,
    APPROVAL_SUFFIX,
    DELIVERY_STATUS,
    REPORT_FINALITY,
)
from nico.phase16_client_delivery_verification_v1 import (
    assert_client_delivery_package,
    repair_client_delivery_package,
    verify_client_delivery_package,
)


def _finding(fid: str, location: str = "apps/web/app/operations/page.tsx:177"):
    return {
        "finding_id": fid,
        "title": "High-complexity code hotspot",
        "decision_title": "High-complexity code hotspot",
        "interpretation": "High-complexity code hotspot",
        "category": "architecture",
        "location": location,
        "acceptance_criteria": [
            "Target functions fall below the approved complexity threshold. [method: automated_test; target commit: "
            + "a" * 40
            + "]",
        ],
    }


def _package():
    finding = _finding("ARCH-1")
    finding["title"] = "Reduce complexity in page.tsx"
    finding["decision_title"] = finding["title"]
    return {
        "json": {
            "canonical_findings": [finding],
            "executive_risk_register": [dict(finding)],
            "priority_findings": [dict(finding)],
            "report_finality": REPORT_FINALITY,
            "approval_status": APPROVAL_STATUS,
            "delivery_status": DELIVERY_STATUS,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "pdf_filename": f"nico-report-{APPROVAL_SUFFIX}.pdf",
        "pdf_base64": base64.b64encode(b"%PDF-1.4 proof").decode("ascii"),
        "canonical_truth_sha256": "a" * 64,
        "phase9_release_gate": {"valid": True},
        "report_finality": REPORT_FINALITY,
        "approval_status": APPROVAL_STATUS,
        "delivery_status": DELIVERY_STATUS,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "analyzer_evidence_report": {
            "analyzers": [
                {"scanner": "bandit", "status": "completed"},
                {"scanner": "eslint", "status": "completed"},
            ]
        },
    }


def test_phase16_accepts_consistent_client_delivery_package():
    result = assert_client_delivery_package(_package())
    assert result["valid"] is True
    assert result["pdf_signature_checked"] is True
    assert result["release_gate_verified"] is True
    assert result["automated_draft_verified"] is True
    assert len(result["verification_fingerprint_sha256"]) == 64


def test_phase16_rejects_visible_title_drift_and_duplicate_scanners():
    package = _package()
    package["json"]["priority_findings"][0]["title"] = "Old generic title"
    package["analyzer_evidence_report"]["analyzers"].append(
        {"scanner": "bandit", "status": "completed"}
    )
    result = verify_client_delivery_package(package)
    assert result["valid"] is False
    assert any("title-consistent" in error for error in result["errors"])
    assert any("duplicate scanner" in error for error in result["errors"])
    with pytest.raises(ValueError, match="Phase 16 client-delivery verification failed"):
        assert_client_delivery_package(package)


def test_phase16_rejects_non_pdf_payload():
    package = _package()
    package["pdf_base64"] = base64.b64encode(b"not a pdf").decode("ascii")
    result = verify_client_delivery_package(package)
    assert result["valid"] is False
    assert "client PDF payload does not have a PDF signature" in result["errors"]


def test_phase16_rejects_legacy_final_pending_approval_identity():
    package = _package()
    package["pdf_filename"] = "nico-report-FINAL-PENDING-APPROVAL.pdf"
    package["report_finality"] = "final"
    result = verify_client_delivery_package(package)
    assert result["valid"] is False
    assert any("automated-draft approval state" in error for error in result["errors"])
    assert any("automated draft" in error for error in result["errors"])


def test_phase16_repairs_paired_legacy_and_p1_findings_and_repeated_criteria():
    package = _package()
    legacy = _finding("RISK-54DC2C8248A9")
    enriched = _finding("RISK-P1-0A2FA160AB")
    enriched["cost_of_inaction"] = "Material"
    enriched["acceptance_criteria"].append(
        "Target functions fall below the approved complexity threshold. [method: workflow_verification; target commit: "
        + "a" * 40
        + "]"
    )
    package["json"]["canonical_findings"] = [legacy, enriched]
    package["json"]["findings_register"] = [legacy, enriched]
    package["json"]["executive_risk_register"] = [legacy, enriched]
    package["pdf_filename"] = (
        "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf"
    )
    package["report_finality"] = "final"

    repaired = repair_client_delivery_package(package)
    assert len(repaired["json"]["canonical_findings"]) == 1
    finding = repaired["json"]["canonical_findings"][0]
    assert set(finding["finding_aliases"]) == {
        "RISK-54DC2C8248A9",
        "RISK-P1-0A2FA160AB",
    }
    assert len(finding["acceptance_criteria"]) == 1
    assert repaired["pdf_filename"] == f"nico-report-{APPROVAL_SUFFIX}.pdf"
    assert repaired["pdf_filename"].count(APPROVAL_SUFFIX) == 1
    assert "FINAL-PENDING-APPROVAL" not in repaired["pdf_filename"]
    assert repaired["report_finality"] == REPORT_FINALITY
    assert repaired["approval_status"] == APPROVAL_STATUS
    assert repaired["delivery_status"] == DELIVERY_STATUS
    assert repaired["client_delivery_allowed"] is False
    assert assert_client_delivery_package(repaired)["valid"] is True


def test_phase16_repair_is_idempotent():
    first = repair_client_delivery_package(_package())
    second = repair_client_delivery_package(first)
    assert first["pdf_filename"] == second["pdf_filename"]
    assert first["json"]["canonical_findings"] == second["json"]["canonical_findings"]
    assert first["canonical_truth_sha256"] == second["canonical_truth_sha256"]
    assert second["pdf_filename"].count(APPROVAL_SUFFIX) == 1
