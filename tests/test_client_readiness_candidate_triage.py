from __future__ import annotations

from copy import deepcopy

import pytest

from nico.client_readiness_candidate_triage import (
    build_candidate_triage_register,
    candidate_triage_gate,
    cluster_candidates,
)


def _candidate(candidate_id: str, *, category: str = "static", line: int = 10) -> dict:
    return {
        "candidate_id": candidate_id,
        "category": category,
        "analyzer": "semgrep" if category == "static" else "pip-audit",
        "rule_id": "python.lang.security.example",
        "path": "nico/example.py",
        "line": line,
        "message": "Example root cause",
        "metadata": {"retained": True},
    }


def _reviewer() -> dict:
    return {
        "identity": "authorized-reviewer",
        "role": "security reviewer",
        "authorized": True,
        "authorization_basis": "engagement-review-role",
    }


def _cluster_decision(cluster: dict, disposition: str = "false_positive") -> dict:
    return {
        "scope": "cluster",
        "cluster_id": cluster["cluster_id"],
        "cluster_digest": cluster["cluster_digest"],
        "disposition": disposition,
        "representative_evidence": ["Reviewed the exact source and retained scanner payload."],
        "reviewer": _reviewer(),
        "decided_at": "2026-08-05T18:00:00Z",
        "rationale": "The retained source proves the scanner pattern is not executable production risk.",
    }


def test_register_blocks_without_human_dispositions_and_preserves_evidence() -> None:
    candidates = [_candidate("candidate-1"), _candidate("candidate-2", line=11)]
    original = deepcopy(candidates)

    register = build_candidate_triage_register(candidates, repository="BoneManTGRM/NICO", commit_sha="a" * 40)

    assert register["status"] == "blocked"
    assert register["triage_complete"] is False
    assert register["pending_candidate_ids"] == ["candidate-1", "candidate-2"]
    assert register["records"][0]["original_evidence"] == original[0]
    assert candidates == original
    assert candidate_triage_gate(register)["status"] == "blocked"


def test_exact_cluster_decision_dispositions_every_member_once() -> None:
    candidates = [_candidate("candidate-1"), _candidate("candidate-2")]
    cluster = cluster_candidates(candidates)[0]

    register = build_candidate_triage_register(candidates, [_cluster_decision(cluster)])
    gate = candidate_triage_gate(register)

    assert register["status"] == "passed"
    assert register["disposition_counts"] == {"false_positive": 2}
    assert all(item["decision_status"] == "complete" for item in register["records"])
    assert gate["status"] == "passed"
    assert gate["client_delivery_allowed"] is False


def test_stale_cluster_digest_fails_closed() -> None:
    candidates = [_candidate("candidate-1"), _candidate("candidate-2")]
    cluster = cluster_candidates(candidates)[0]
    decision = _cluster_decision(cluster)
    decision["cluster_digest"] = "0" * 64

    register = build_candidate_triage_register(candidates, [decision])

    assert register["status"] == "blocked"
    assert "cluster_digest does not match" in " ".join(register["invalid_decisions"][0]["errors"])
    assert set(register["pending_candidate_ids"]) == {"candidate-1", "candidate-2"}


def test_bulk_decision_requires_representative_evidence_and_authority() -> None:
    candidates = [_candidate("candidate-1")]
    cluster = cluster_candidates(candidates)[0]
    decision = _cluster_decision(cluster)
    decision["representative_evidence"] = []
    decision["reviewer"]["authorized"] = False

    register = build_candidate_triage_register(candidates, [decision])
    errors = " ".join(register["invalid_decisions"][0]["errors"])

    assert "representative_evidence" in errors
    assert "authorized must be true" in errors
    assert register["status"] == "blocked"


def test_formal_more_evidence_disposition_requires_owner_date_and_risk_acceptance() -> None:
    candidate = _candidate("candidate-1", category="dependency")
    cluster = cluster_candidates([candidate])[0]
    decision = _cluster_decision(cluster, "requires_more_evidence")

    blocked = build_candidate_triage_register([candidate], [decision])
    errors = " ".join(blocked["invalid_decisions"][0]["errors"])
    assert "owner is required" in errors
    assert "review_by" in errors
    assert "risk_acceptance.accepted_by" in errors

    decision.update(
        {
            "owner": "dependency-review-owner",
            "review_by": "2026-08-19",
            "risk_acceptance": {
                "accepted_by": "authorized-risk-owner",
                "authorization_basis": "repository-owner",
                "accepted_at": "2026-08-05T18:00:00Z",
            },
        }
    )
    complete = build_candidate_triage_register([candidate], [decision])
    assert complete["status"] == "passed"
    assert complete["disposition_counts"] == {"requires_more_evidence": 1}


def test_duplicate_candidate_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate candidate identity"):
        cluster_candidates([_candidate("same"), _candidate("same")])


def test_overlapping_decisions_fail_closed_instead_of_last_write_wins() -> None:
    candidates = [_candidate("candidate-1")]
    cluster = cluster_candidates(candidates)[0]
    decision = _cluster_decision(cluster)
    candidate_decision = {
        "scope": "candidate",
        "candidate_id": "candidate-1",
        "disposition": "accepted_nonblocking",
        "reviewer": _reviewer(),
        "decided_at": "2026-08-05T18:00:00Z",
        "rationale": "Accepted by authorized reviewer.",
    }

    register = build_candidate_triage_register(candidates, [decision, candidate_decision])

    assert register["status"] == "blocked"
    assert "already dispositioned" in " ".join(register["invalid_decisions"][0]["errors"])


def test_automation_cannot_use_review_required_as_a_disposition() -> None:
    candidate = _candidate("candidate-1")
    cluster = cluster_candidates([candidate])[0]
    decision = _cluster_decision(cluster)
    decision["disposition"] = "review_required"

    register = build_candidate_triage_register([candidate], [decision])

    assert register["status"] == "blocked"
    assert "unsupported disposition" in " ".join(register["invalid_decisions"][0]["errors"])
