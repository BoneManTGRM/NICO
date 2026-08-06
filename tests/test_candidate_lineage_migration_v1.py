from __future__ import annotations

from nico.candidate_lineage_migration_v1 import (
    apply_candidate_lineage,
    lineage_keys,
    load_default_baseline,
)


def _baseline_record(record: dict, candidate: str, proposal: str = "source_review_required") -> list:
    keys = lineage_keys(record)
    return [keys["exact"], keys["semantic"], keys["group"], keys["line"], candidate, proposal, "cluster-1"]


def _baseline(records: list[list]) -> dict:
    return {
        "s": "nico.candidate-lineage-baseline.v2",
        "r": "BoneManTGRM/NICO",
        "c": "a" * 40,
        "n": len(records),
        "k": {"static": len(records)},
        "a": "none",
        "x": records,
    }


def _register(findings: list[dict]) -> dict:
    return {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "status": "complete",
        "exact_commit_sha": "b" * 40,
        "findings": findings,
        "totals": {"raw": sum(item.get("occurrence_count", 1) for item in findings)},
        "canonical_digest_sha256": "old",
    }


def test_default_baseline_is_decodable_and_complete() -> None:
    baseline = load_default_baseline()
    assert baseline["n"] == 662
    assert len(baseline["x"]) == 662
    assert baseline["k"] == {"dependency": 59, "secret": 17, "static": 586}
    assert baseline["a"] == "none"


def test_exact_candidate_carries_proposal_but_never_human_approval() -> None:
    current = {
        "finding_id": "NICO-SCAN-CURRENT",
        "scanner": "bandit",
        "category": "static",
        "rule_id": "B101",
        "source_path": "scripts/example.py",
        "line": 12,
        "evidence": "assert used",
        "disposition": "review_required",
        "occurrence_count": 1,
        "exact_commit_sha": "b" * 40,
    }
    result = apply_candidate_lineage(
        _register([current]),
        baseline=_baseline([_baseline_record(current, "NICO-OLD-1")]),
    )
    migrated = result["findings"][0]
    lineage = result["candidate_lineage"]
    assert migrated["lineage_status"] == "carried_forward_exact"
    assert migrated["prior_candidate_id"] == "NICO-OLD-1"
    assert migrated["proposed_disposition"] == "source_review_required"
    assert migrated["disposition"] == "review_required"
    assert migrated["human_approval_carried_forward"] is False
    assert migrated["human_approval_status"] == "pending"
    assert lineage["carried_forward_total"] == 1
    assert lineage["newly_observed"] == 0
    assert lineage["human_approval_carried_forward"] is False
    assert lineage["client_delivery_allowed"] is False


def test_line_shift_uses_semantic_lineage_and_new_candidate_stays_new() -> None:
    prior = {
        "scanner": "bandit",
        "category": "static",
        "rule_id": "B101",
        "source_path": "scripts/example.py",
        "line": 12,
        "evidence": "assert used",
    }
    shifted = {
        "finding_id": "NICO-SCAN-SHIFTED",
        "scanner": "bandit",
        "category": "static",
        "rule_id": "B101",
        "source_path": "/tmp/work/repo/scripts/example.py",
        "line": 19,
        "evidence": "assert used",
        "disposition": "review_required",
        "occurrence_count": 1,
        "exact_commit_sha": "b" * 40,
    }
    new = {
        "finding_id": "NICO-SCAN-NEW",
        "scanner": "bandit",
        "category": "static",
        "rule_id": "B608",
        "source_path": "scripts/new.py",
        "line": 4,
        "evidence": "hardcoded SQL",
        "disposition": "review_required",
        "occurrence_count": 1,
        "exact_commit_sha": "b" * 40,
    }
    result = apply_candidate_lineage(
        _register([shifted, new]),
        baseline=_baseline([_baseline_record(prior, "NICO-OLD-1")]),
    )
    assert result["findings"][0]["lineage_status"] == "carried_forward_location_changed"
    assert result["findings"][1]["lineage_status"] == "newly_observed"
    assert result["candidate_lineage"]["carried_forward_total"] == 1
    assert result["candidate_lineage"]["newly_observed"] == 1
    assert result["candidate_lineage"]["no_longer_observed"] == 0


def test_missing_prior_candidate_becomes_explicit_tombstone() -> None:
    prior = {
        "scanner": "bandit",
        "category": "static",
        "rule_id": "B101",
        "source_path": "scripts/removed.py",
        "line": 12,
        "evidence": "assert used",
    }
    result = apply_candidate_lineage(
        _register([]),
        baseline=_baseline([_baseline_record(prior, "NICO-OLD-REMOVED")]),
    )
    lineage = result["candidate_lineage"]
    assert lineage["no_longer_observed"] == 1
    assert lineage["tombstones"][0]["prior_candidate_id"] == "NICO-OLD-REMOVED"
    assert lineage["tombstones"][0]["human_approval_carried_forward"] is False
