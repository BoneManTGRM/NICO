from __future__ import annotations

import pytest

from nico.comprehensive_blocked_run_recovery_v1 import (
    VERSION,
    blocked_run_recovery_reason,
    final_artifact_recovery_stage,
    is_recoverable_final_artifact_failure,
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    _record_hash,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)


RECOVERY_BUDGET_SCOPE = "source_failed_stage_recovery_generation"


def _detached_blocked_record(stage_id: str) -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun_3546b60fbb744bbea5fcf3c5c89b7ecd",
        repository="BoneManTGRM/NICO",
        commit_sha="5" * 40,
        evidence_ledger_id="ledger-stale-detached-recovery",
        customer_id="default_customer",
        project_id="default_project",
        authorized=True,
    )
    for current in COMPREHENSIVE_STAGES:
        if current == stage_id:
            result = {
                "status": "blocked",
                "reason": "stage_execution_failed",
                "technical_reason": "detached_stage_execution_failed",
                "http_status": 200,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        else:
            result = {
                "status": "complete",
                "evidence": {
                    "stage": current,
                    "exact_commit_sha": "5" * 40,
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        record = apply_comprehensive_stage_result(
            record,
            stage_id=current,
            result=result,
        )
        if current == stage_id:
            break
    return record


def _attach_recovery_history(
    blocked: dict,
    *,
    artifact_schema: str,
    budget_scope: str,
    recovery_generation: str | None = None,
) -> dict:
    updated = dict(blocked)
    event = {
        "artifact_schema": artifact_schema,
        "source_failed_stage": str(blocked["current_stage"]),
        "source_reason": "detached_stage_execution_failed",
        "rerun_from_stage": str(blocked["current_stage"]),
        "recovery_scope": "decision_report_and_downstream",
        "recovery_budget_scope": budget_scope,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "recovered_at": "2026-08-19T15:00:00+00:00",
    }
    if recovery_generation is not None:
        event["recovery_generation"] = recovery_generation
    updated["recovery_history"] = [event]
    updated["integrity_sha256"] = _record_hash(updated)
    assert validate_comprehensive_run_record(updated)["status"] == "valid"
    return updated


@pytest.mark.parametrize(
    ("failed_stage", "expected_scope"),
    [
        ("decision_report_generation", "decision_report_and_downstream"),
        ("final_comprehensive_report_generation", "final_report_only"),
    ],
)
def test_stale_detached_report_failure_rewinds_same_exact_run_once(
    failed_stage: str,
    expected_scope: str,
) -> None:
    blocked = _detached_blocked_record(failed_stage)
    identity = dict(blocked["identity"])
    target_index = COMPREHENSIVE_STAGES.index(failed_stage)
    preserved = {
        stage_id: blocked["stage_results"][stage_id]
        for stage_id in COMPREHENSIVE_STAGES[:target_index]
    }

    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert blocked_run_recovery_reason(blocked) == "detached_stage_execution_failed"
    assert is_recoverable_final_artifact_failure(blocked) is True
    assert final_artifact_recovery_stage(blocked) == failed_stage

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)

    assert recovered["identity"] == identity
    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["completed_stages"] == list(COMPREHENSIVE_STAGES[:target_index])
    assert failed_stage not in recovered["stage_results"]
    for stage_id, result in preserved.items():
        assert recovered["stage_results"][stage_id] == result

    history = recovered["recovery_history"][-1]
    assert history["artifact_schema"] == VERSION
    assert history["source_failed_stage"] == failed_stage
    assert history["source_reason"] == "detached_stage_execution_failed"
    assert history["rerun_from_stage"] == failed_stage
    assert history["recovery_scope"] == expected_scope
    assert history["recovery_budget_scope"] == RECOVERY_BUDGET_SCOPE
    assert history["recovery_generation"] == VERSION
    assert history["exact_run_identity_preserved"] is True
    assert history["raw_scanner_evidence_preserved"] is True
    assert history["human_review_required"] is True
    assert history["client_delivery_allowed"] is False
    assert recovered["human_review_required"] is True
    assert recovered["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"

    # The recovered record is active, so merely re-entering the helper cannot spend
    # another recovery attempt or create a second history event.
    assert rewind_blocked_run_for_final_artifact_recovery(recovered) == recovered


def test_previous_recovery_generation_does_not_permanently_lock_durable_run() -> None:
    blocked = _detached_blocked_record("decision_report_generation")
    blocked_with_v7_attempt = _attach_recovery_history(
        blocked,
        artifact_schema="nico.comprehensive_blocked_run_recovery.v7",
        budget_scope="source_failed_stage",
    )

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked_with_v7_attempt)

    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["identity"] == blocked["identity"]
    assert len(recovered["recovery_history"]) == 2
    latest = recovered["recovery_history"][-1]
    assert latest["artifact_schema"] == VERSION
    assert latest["recovery_generation"] == VERSION
    assert latest["recovery_budget_scope"] == RECOVERY_BUDGET_SCOPE
    assert latest["source_failed_stage"] == "decision_report_generation"
    assert latest["source_reason"] == "detached_stage_execution_failed"
    assert latest["human_review_required"] is True
    assert latest["client_delivery_allowed"] is False


def test_current_recovery_generation_still_allows_only_one_attempt_per_source_stage() -> None:
    blocked = _detached_blocked_record("decision_report_generation")
    already_attempted = _attach_recovery_history(
        blocked,
        artifact_schema=VERSION,
        budget_scope=RECOVERY_BUDGET_SCOPE,
        recovery_generation=VERSION,
    )

    assert is_recoverable_final_artifact_failure(already_attempted) is True
    assert rewind_blocked_run_for_final_artifact_recovery(already_attempted) == already_attempted


def test_detached_failure_outside_report_stages_stays_blocked() -> None:
    blocked = _detached_blocked_record("deep_scanner_triage")

    assert blocked_run_recovery_reason(blocked) == "stage_execution_failed"
    assert is_recoverable_final_artifact_failure(blocked) is False
    assert rewind_blocked_run_for_final_artifact_recovery(blocked) == blocked
