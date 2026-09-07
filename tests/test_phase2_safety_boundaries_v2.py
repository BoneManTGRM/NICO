from __future__ import annotations

from copy import deepcopy

import pytest

from nico.comprehensive_review_work_safe_v1 import apply_review_work_action
from nico.comprehensive_review_work_v2 import ledger_for_record, review_work_projection


def _candidate(
    candidate_id: str,
    *,
    severity: str = "low",
    confidence: float = 0.98,
    evidence_change_state: str = "unchanged",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "cluster_id": "GROUP",
        "severity": severity,
        "scanner": "semgrep",
        "category": "security",
        "rule": "fixture-rule",
        "path": f"src/{candidate_id}.py",
        "technical_triage_verdict": "not_actionable",
        "technical_triage_confidence": confidence,
        "evidence_change_state": evidence_change_state,
        "grouped_review_eligible": True,
        "review_requires_individual_attention": False,
        "homogeneous_evidence": True,
        "homogeneous_verdict": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _record(candidate: dict) -> dict:
    identity = {
        "run_id": "comprun_scope_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger-scope-test",
        "project_id": "project-a",
        "client_id": "client-a",
        "assessment_depth": "comprehensive",
        "report_language": "en",
    }
    register = {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_record_count": 1,
        "findings": [candidate],
        "review_workload_clusters": [
            {
                "cluster_id": "GROUP",
                "candidate_ids": [candidate["candidate_id"]],
                "candidate_record_count": 1,
                "cluster_size": 1,
                "representative_candidate_id": candidate["candidate_id"],
                "grouped_review_eligible": True,
                "grouped_human_review_cluster": True,
                "homogeneous_evidence": True,
                "homogeneous_verdict": True,
                "underlying_candidate_disposition_required": True,
            }
        ],
        "technical_triage": {"total_candidates": 1, "triaged_candidates": 1},
    }
    canonical_identity = {
        key: identity[key]
        for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
    }
    return {
        "identity": identity,
        "status": "review_required",
        "terminal": True,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_results": {
            "final_comprehensive_report_generation": {
                "report_package": {
                    "json": {
                        "identity": canonical_identity,
                        "assessment": {"canonical_scanner_finding_register": register},
                        "human_review_required": True,
                        "client_delivery_allowed": False,
                    }
                }
            }
        },
    }


def _group_payload() -> dict:
    return {
        "action": "disposition_group",
        "cluster_id": "GROUP",
        "disposition": "false_positive",
        "rationale": "Exact homogeneous evidence supports this explicit group disposition.",
        "reviewer": "Alice",
        "reviewer_role": "Security specialist",
        "review_authorized": True,
        "authorization_confirmed": True,
    }


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate("material", severity="high"),
        _candidate("low-confidence", confidence=0.40),
        _candidate("changed", evidence_change_state="changed"),
    ],
)
def test_group_disposition_fails_closed_for_individual_attention_conditions(candidate: dict) -> None:
    with pytest.raises(
        ValueError,
        match="review_work_group_disposition_contains_non_bulk_reviewable_candidates",
    ):
        apply_review_work_action(_record(candidate), _group_payload())


def test_scope_binding_prevents_cross_run_project_or_client_review_state_leakage() -> None:
    record = _record(_candidate("stable"))
    record["review_work_ledger"] = ledger_for_record(record)

    other_run = deepcopy(record)
    other_run["identity"]["run_id"] = "comprun_other"
    with pytest.raises(ValueError, match="review_work_(identity|scope_binding|source_evidence)_"):
        review_work_projection(other_run)

    other_project = deepcopy(record)
    other_project["identity"]["project_id"] = "project-b"
    with pytest.raises(ValueError, match="review_work_(scope_binding|source_evidence)_changed"):
        review_work_projection(other_project)

    other_client = deepcopy(record)
    other_client["identity"]["client_id"] = "client-b"
    with pytest.raises(ValueError, match="review_work_(scope_binding|source_evidence)_changed"):
        review_work_projection(other_client)


def test_full_technical_triage_never_authorizes_human_assurance_or_delivery() -> None:
    record = _record(_candidate("triaged"))
    projection = review_work_projection(record)
    candidate = projection["candidates"][0]
    assert candidate["technical_triage_verdict"] == "not_actionable"
    assert candidate["human_disposition_state"] == "pending"
    assert projection["remaining_candidate_count"] == 1
    assert projection["ready_for_final_approval"] is False
    assert projection["client_delivery_allowed"] is False
    assert record["human_review_completed"] is False
    assert record["client_delivery_allowed"] is False


@pytest.mark.parametrize("label, expected, qc_population", [("high", 0.9, 1), ("medium", 0.72, 0), ("low", 0.45, 0), ("unknown", 0.0, 0)])
def test_canonical_confidence_labels_preserve_existing_scale_and_qc_eligibility(label, expected, qc_population):
    from nico.comprehensive_review_work_safe_v1 import review_work_projection as safe_projection

    candidate = _candidate("stable", confidence=label)
    candidate.update({"review_routing_class": "STABLE_CARRY_FORWARD", "lineage_status": "carried_forward_exact", "grouped_review_eligible": False})
    candidate.pop("evidence_change_state")
    record = _record(candidate)
    cluster = record["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"]["assessment"]["canonical_scanner_finding_register"]["review_workload_clusters"][0]
    cluster.update({"grouped_review_eligible": False, "grouped_human_review_cluster": False})
    before = deepcopy(record)
    projection = safe_projection(record)
    row = projection["candidates"][0]
    assert row["technical_triage_confidence"] == expected
    assert projection["quality_control_sampling"]["population_size"] == qc_population
    assert row["human_disposition_state"] == "automated_triage_complete"
    assert row["primary_review_queue"] == "stable_carry_forward"
    assert projection["queue_counts"]["stable_carry_forward"] == 1
    assert projection["queue_counts"]["human_technical_review"] == 0
    assert projection["required_human_disposition_count"] == 0
    assert projection["client_delivery_allowed"] is False
    assert record == before


def test_legacy_primary_queue_recognizes_canonical_exact_carry_forward_alias():
    candidate = _candidate("stable", confidence=0.98)
    candidate.pop("evidence_change_state")
    candidate["lineage_status"] = "carried_forward_exact"
    projection = review_work_projection(_record(candidate))
    assert projection["candidates"][0]["primary_review_queue"] == "stable_carry_forward"
    assert projection["queue_counts"]["stable_carry_forward"] == 1
