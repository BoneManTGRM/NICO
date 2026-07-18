from __future__ import annotations

from copy import deepcopy

from nico.cross_tier_verification_evidence_ledger_v1 import (
    build_cross_tier_verification_evidence_ledger,
)

SHA = "a" * 40
CHECKSUM = "b" * 64


def _tier() -> dict:
    return {
        "tests_passed": True,
        "security_passed": True,
        "build_passed": True,
        "render_qa_passed": True,
        "identity_invariants_passed": True,
        "deployment_sha_aligned": True,
        "client_delivery_allowed": True,
        "artifacts": {
            artifact_format: {
                "artifact_id": f"artifact-{artifact_format}",
                "sha256": CHECKSUM,
            }
            for artifact_format in ("pdf", "html", "markdown")
        },
    }


def _pass(completed_at: str) -> dict:
    return {
        "commit_sha": SHA,
        "completed_at": completed_at,
        "environments": {
            environment: {
                "deployment_id": f"{environment}-deployment",
                "commit_sha": SHA,
                "healthy": True,
            }
            for environment in ("staging", "production")
        },
        "tiers": {tier: _tier() for tier in ("express", "mid", "full")},
    }


def test_two_clean_passes_with_complete_evidence_allow_delivery() -> None:
    result = build_cross_tier_verification_evidence_ledger(
        [_pass("2026-07-18T00:00:00Z"), _pass("2026-07-18T00:15:00Z")],
        expected_commit_sha=SHA,
    )
    assert result["release_evidence_verified"] is True
    assert result["client_delivery_allowed"] is True
    assert result["issues"] == []


def test_missing_production_deployment_id_fails_closed() -> None:
    second = _pass("2026-07-18T00:15:00Z")
    second["environments"]["production"]["deployment_id"] = ""
    result = build_cross_tier_verification_evidence_ledger(
        [_pass("2026-07-18T00:00:00Z"), second],
        expected_commit_sha=SHA,
    )
    assert "evidence_pass_2:missing_production_deployment_id" in result["issues"]
    assert result["client_delivery_allowed"] is False


def test_deployment_sha_drift_fails_closed() -> None:
    second = _pass("2026-07-18T00:15:00Z")
    second["environments"]["staging"]["commit_sha"] = "c" * 40
    result = build_cross_tier_verification_evidence_ledger(
        [_pass("2026-07-18T00:00:00Z"), second],
        expected_commit_sha=SHA,
    )
    assert "evidence_pass_2:staging_deployment_sha_mismatch" in result["issues"]
    assert result["release_evidence_verified"] is False


def test_invalid_artifact_checksum_fails_closed() -> None:
    second = deepcopy(_pass("2026-07-18T00:15:00Z"))
    second["tiers"]["full"]["artifacts"]["pdf"]["sha256"] = "not-a-checksum"
    result = build_cross_tier_verification_evidence_ledger(
        [_pass("2026-07-18T00:00:00Z"), second],
        expected_commit_sha=SHA,
    )
    assert "evidence_pass_2:full_pdf_invalid_sha256" in result["issues"]
    assert result["client_delivery_allowed"] is False


def test_non_consecutive_timestamp_fails_closed() -> None:
    result = build_cross_tier_verification_evidence_ledger(
        [_pass("2026-07-18T00:15:00Z"), _pass("2026-07-18T00:15:00Z")],
        expected_commit_sha=SHA,
    )
    assert "evidence_pass_2:non_consecutive_timestamp" in result["issues"]
    assert result["release_evidence_verified"] is False


def test_naive_timestamp_is_rejected() -> None:
    result = build_cross_tier_verification_evidence_ledger(
        [_pass("2026-07-18T00:00:00"), _pass("2026-07-18T00:15:00Z")],
        expected_commit_sha=SHA,
    )
    assert "evidence_pass_1:missing_or_invalid_completed_at" in result["issues"]
    assert result["client_delivery_allowed"] is False
