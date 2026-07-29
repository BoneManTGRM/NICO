from __future__ import annotations

import base64

import pytest

from nico.phase16_client_delivery_verification_v1 import (
    assert_client_delivery_package,
    verify_client_delivery_package,
)


def _package():
    finding = {"finding_id": "ARCH-1", "title": "Reduce complexity in page.tsx"}
    return {
        "json": {
            "canonical_findings": [finding],
            "executive_risk_register": [dict(finding)],
            "priority_findings": [dict(finding)],
        },
        "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL.pdf",
        "pdf_base64": base64.b64encode(b"%PDF-1.4 proof").decode("ascii"),
        "canonical_truth_sha256": "a" * 64,
        "phase9_release_gate": {"valid": True},
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
