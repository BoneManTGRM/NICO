from __future__ import annotations

from copy import deepcopy

import pytest

from nico.client_readiness_finding_disposition import (
    build_finding_disposition_register,
    canonical_finding,
    finding_disposition_gate,
)


DIGEST = "d" * 64


def _finding(finding_id: str, *, release_blocking: bool = False) -> dict:
    return {
        "finding_id": finding_id,
        "title": "Reduce complexity in control path",
        "priority": "P1" if release_blocking else "P2",
        "path": "nico/control.py",
        "line": 42,
        "evidence": "cyclomatic_complexity=50",
        "release_blocking": release_blocking,
        "control_plane": True,
    }


def _reviewer() -> dict:
    return {
        "identity": "authorized-reviewer",
        "role": "technical acceptance owner",
        "authorized": True,
        "authorization_basis": "engagement-approval-matrix",
    }


def _risk_acceptance() -> dict:
    return {
        "accepted_by": "authorized-risk-owner",
        "role": "residual risk owner",
        "authorization_basis": "client-risk-authority",
        "accepted_at": "2026-08-05T18:00:00Z",
        "scope": "Exact finding on exact release commit",
    }


def _decision(finding: dict, state: str = "remediate") -> dict:
    canonical = canonical_finding(finding)
    return {
        "finding_id": canonical["finding_id"],
        "finding_digest": canonical["finding_digest"],
        "decision": state,
        "risk": "Regression risk in a release-control path.",
        "probable_impact": "A change can be harder to review and recover safely.",
        "owner": "engineering-owner",
        "target_date": "2026-08-20",
        "verification_method": "Characterization tests plus exact-SHA complexity rerun.",
        "verification": {"status": "passed", "artifact_sha256": DIGEST},
        "reviewer": _reviewer(),
        "decided_at": "2026-08-05T18:00:00Z",
        "rationale": "Decision applies to the exact retained source and verification artifact.",
    }


def test_missing_human_decisions_block_and_original_findings_are_preserved() -> None:
    findings = [_finding("F-1"), _finding("F-2")]
    original = deepcopy(findings)

    register = build_finding_disposition_register(findings)

    assert register["status"] == "blocked"
    assert register["pending_finding_ids"] == ["F-1", "F-2"]
    assert register["records"][0]["original_finding"] == original[0]
    assert findings == original
    assert finding_disposition_gate(register)["status"] == "blocked"


def test_all_exact_findings_with_authorized_decisions_pass_without_authorizing_delivery() -> None:
    findings = [_finding("F-1"), _finding("F-2")]
    decisions = [_decision(item) for item in findings]

    register = build_finding_disposition_register(findings, decisions)
    gate = finding_disposition_gate(register)

    assert register["status"] == "passed"
    assert register["decision_counts"] == {"remediate": 2}
    assert gate["status"] == "passed"
    assert gate["client_delivery_allowed"] is False


def test_stale_finding_digest_fails_closed() -> None:
    finding = _finding("F-1")
    decision = _decision(finding)
    decision["finding_digest"] = "0" * 64

    register = build_finding_disposition_register([finding], [decision])

    assert register["status"] == "blocked"
    assert "finding_digest does not match" in " ".join(register["invalid_decisions"][0]["errors"])


def test_release_blocking_remediation_must_be_verified_as_passed() -> None:
    finding = _finding("F-1", release_blocking=True)
    decision = _decision(finding)
    decision["verification"] = {"status": "pending"}
    decision["residual_risk_acceptance"] = _risk_acceptance()

    register = build_finding_disposition_register([finding], [decision])
    errors = " ".join(register["invalid_decisions"][0]["errors"])

    assert register["status"] == "blocked"
    assert "release-blocking remediation must be verified" in errors


def test_accept_or_defer_requires_authorized_residual_risk_acceptance() -> None:
    for state in ("accept", "defer"):
        finding = _finding(f"F-{state}")
        decision = _decision(finding, state)
        register = build_finding_disposition_register([finding], [decision])
        assert register["status"] == "blocked"
        assert "residual_risk_acceptance.accepted_by" in " ".join(register["invalid_decisions"][0]["errors"])

        decision["residual_risk_acceptance"] = _risk_acceptance()
        complete = build_finding_disposition_register([finding], [decision])
        assert complete["status"] == "passed"


def test_release_blocking_acceptance_is_possible_only_with_explicit_risk_authority() -> None:
    finding = _finding("F-1", release_blocking=True)
    decision = _decision(finding, "accept")
    decision["residual_risk_acceptance"] = _risk_acceptance()

    register = build_finding_disposition_register([finding], [decision])

    assert register["status"] == "passed"
    assert register["release_blockers"] == []


def test_rejecting_a_finding_requires_rejection_evidence() -> None:
    finding = _finding("F-1")
    decision = _decision(finding, "reject")

    blocked = build_finding_disposition_register([finding], [decision])
    assert "rejection_evidence is required" in " ".join(blocked["invalid_decisions"][0]["errors"])

    decision["rejection_evidence"] = "Exact source and scanner payload prove the location is no longer present."
    complete = build_finding_disposition_register([finding], [decision])
    assert complete["status"] == "passed"


def test_duplicate_finding_identity_and_duplicate_decisions_are_rejected() -> None:
    finding = _finding("F-1")
    with pytest.raises(ValueError, match="duplicate finding identity"):
        build_finding_disposition_register([finding, finding])

    decision = _decision(finding)
    register = build_finding_disposition_register([finding], [decision, decision])
    assert register["status"] == "blocked"
    assert "already has a decision" in " ".join(register["invalid_decisions"][0]["errors"])


def test_automation_cannot_use_unapproved_decision_state() -> None:
    finding = _finding("F-1")
    decision = _decision(finding)
    decision["decision"] = "auto_approved"

    register = build_finding_disposition_register([finding], [decision])

    assert register["status"] == "blocked"
    assert "unsupported finding decision" in " ".join(register["invalid_decisions"][0]["errors"])
