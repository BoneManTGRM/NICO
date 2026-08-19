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
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)


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
    assert history["recovery_budget_scope"] == "source_failed_stage"
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


def test_detached_failure_outside_report_stages_stays_blocked() -> None:
    blocked = _detached_blocked_record("deep_scanner_triage")

    assert blocked_run_recovery_reason(blocked) == "stage_execution_failed"
    assert is_recoverable_final_artifact_failure(blocked) is False
    assert rewind_blocked_run_for_final_artifact_recovery(blocked) == blocked
