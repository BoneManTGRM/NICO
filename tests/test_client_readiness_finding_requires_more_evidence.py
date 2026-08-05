from __future__ import annotations

from nico.client_readiness_finding_disposition import (
    build_finding_disposition_register,
    canonical_finding,
    finding_disposition_gate,
)


def _finding(*, release_blocking: bool = True) -> dict:
    return {
        "finding_id": "NICO-FINDING-FIXTURE",
        "title": "Reduce complexity in fixture",
        "priority": "P1",
        "path": "nico/fixture.py",
        "line": 40,
        "evidence": "cyclomatic_complexity=50",
        "release_blocking": release_blocking,
        "control_plane": True,
    }


def _decision(finding_digest: str) -> dict:
    return {
        "finding_id": "NICO-FINDING-FIXTURE",
        "finding_digest": finding_digest,
        "decision": "requires_more_evidence",
        "evidence_request": "Provide the exact-SHA characterization-test result and measured post-change complexity.",
        "risk": "A complex control-plane function may regress during modification.",
        "probable_impact": "Report publication or delivery controls could fail.",
        "owner": "Technical reviewer",
        "target_date": "2026-09-01",
        "verification_method": "Exact-SHA complexity rerun and targeted characterization tests.",
        "rationale": "The retained evidence is insufficient to accept, reject, defer, or verify remediation.",
        "decided_at": "2026-08-05T21:45:00Z",
        "reviewer": {
            "identity": "reviewer@example.com",
            "role": "Principal Engineering Reviewer",
            "authorization_basis": "Repository-owner delegated review authority",
            "authorized": True,
        },
    }


def test_authorized_request_more_evidence_is_valid_but_remains_blocked() -> None:
    finding = _finding()
    normalized = canonical_finding(finding)
    register = build_finding_disposition_register(
        [finding],
        [_decision(normalized["finding_digest"])],
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        run_id="comprun_fixture",
    )

    assert register["invalid_decisions"] == []
    assert register["status"] == "blocked"
    assert register["disposition_complete"] is False
    assert register["decision_counts"] == {"requires_more_evidence": 1}
    assert register["pending_finding_ids"] == ["NICO-FINDING-FIXTURE"]
    assert register["records"][0]["decision_status"] == "requires_more_evidence"
    assert register["release_blockers"] == [
        "NICO-FINDING-FIXTURE requires more evidence before disposition"
    ]
    assert finding_disposition_gate(register)["status"] == "blocked"


def test_request_more_evidence_requires_a_precise_evidence_request() -> None:
    finding = _finding(release_blocking=False)
    normalized = canonical_finding(finding)
    decision = _decision(normalized["finding_digest"])
    decision.pop("evidence_request")

    register = build_finding_disposition_register([finding], [decision])

    assert register["status"] == "blocked"
    assert len(register["invalid_decisions"]) == 1
    assert "evidence_request is required when requesting more evidence" in register[
        "invalid_decisions"
    ][0]["errors"]
    assert register["records"][0]["decision_status"] == "pending_human_decision"


def test_request_more_evidence_does_not_fabricate_residual_risk_acceptance() -> None:
    finding = _finding()
    normalized = canonical_finding(finding)
    decision = _decision(normalized["finding_digest"])

    register = build_finding_disposition_register([finding], [decision])

    assert register["invalid_decisions"] == []
    assert "residual_risk_acceptance" not in register["records"][0]["decision"]
    assert register["client_delivery_allowed"] is False
    assert register["automation_may_decide"] is False
