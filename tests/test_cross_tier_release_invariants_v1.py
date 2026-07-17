from __future__ import annotations

import pytest

from nico.cross_tier_release_invariants_v1 import (
    attach_cross_tier_release_invariants,
    validate_cross_tier_release,
)


def _release(tier: str = "full") -> dict:
    assessment_id = f"assessment-{tier}"
    repository_id = "repo-1"
    snapshot_sha = "a" * 40
    evidence_packet_id = "packet-1"
    locale = "en"
    artifacts = {}
    for index, report_format in enumerate(("pdf", "html", "markdown"), start=1):
        artifacts[report_format] = {
            "artifact_id": f"artifact-{tier}-{report_format}",
            "sha256": str(index) * 64,
            "assessment_id": assessment_id,
            "repository_id": repository_id,
            "snapshot_sha": snapshot_sha,
            "evidence_packet_id": evidence_packet_id,
            "tier": tier,
            "locale": locale,
        }
    return {
        "tier": tier,
        "assessment_id": assessment_id,
        "repository_id": repository_id,
        "snapshot_sha": snapshot_sha,
        "evidence_packet_id": evidence_packet_id,
        "locale": locale,
        "canonical_score": 84,
        "displayed_score": 84,
        "automated_complete": True,
        "human_approved": True,
        "revoked": False,
        "approval": {"reviewer_id": "reviewer-1", "approved_at": "2026-07-17T23:30:00Z"},
        "artifacts": artifacts,
        "client_delivery_allowed": True,
    }


def _expected(tier: str) -> dict:
    return {
        "expected_tier": tier,
        "expected_assessment_id": f"assessment-{tier}",
        "expected_repository_id": "repo-1",
        "expected_snapshot_sha": "a" * 40,
        "expected_evidence_packet_id": "packet-1",
        "expected_locale": "en",
    }


@pytest.mark.parametrize("tier", ["express", "mid", "full"])
def test_each_tier_passes_only_with_reconciled_identity_and_approval(tier: str) -> None:
    decision = validate_cross_tier_release(_release(tier), **_expected(tier))
    assert decision["issues"] == []
    assert decision["all_invariants_passed"] is True
    assert decision["client_delivery_allowed"] is True


def test_score_mismatch_fails_closed() -> None:
    release = _release("mid")
    release["displayed_score"] = 91
    decision = validate_cross_tier_release(release, **_expected("mid"))
    assert "score_reconciliation_failure" in decision["issues"]
    assert decision["client_delivery_allowed"] is False


def test_revocation_overrides_previous_approval() -> None:
    release = _release("full")
    release["revoked"] = True
    decision = validate_cross_tier_release(release, **_expected("full"))
    assert "approval_revoked" in decision["issues"]
    assert decision["client_delivery_allowed"] is False


def test_cross_tier_artifact_contamination_is_blocked() -> None:
    release = _release("express")
    release["artifacts"]["pdf"]["tier"] = "full"
    decision = validate_cross_tier_release(release, **_expected("express"))
    assert "pdf_tier_mismatch" in decision["issues"]
    assert decision["client_delivery_allowed"] is False


def test_stale_snapshot_artifact_is_blocked() -> None:
    release = _release("full")
    release["artifacts"]["html"]["snapshot_sha"] = "b" * 40
    decision = validate_cross_tier_release(release, **_expected("full"))
    assert "html_snapshot_mismatch" in decision["issues"]
    assert decision["client_delivery_allowed"] is False


def test_missing_format_and_invalid_checksum_are_blocked() -> None:
    release = _release("mid")
    del release["artifacts"]["markdown"]
    release["artifacts"]["pdf"]["sha256"] = "not-a-sha"
    decision = validate_cross_tier_release(release, **_expected("mid"))
    assert "missing_markdown_artifact" in decision["issues"]
    assert "invalid_pdf_sha256" in decision["issues"]


def test_attach_preserves_existing_delivery_block() -> None:
    release = _release("express")
    release["client_delivery_allowed"] = False
    result = attach_cross_tier_release_invariants(release, **_expected("express"))
    assert result["cross_tier_release_invariants"]["client_delivery_allowed"] is True
    assert result["client_delivery_allowed"] is False
