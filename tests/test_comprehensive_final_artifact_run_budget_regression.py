from __future__ import annotations

from nico.comprehensive_blocked_run_recovery_v1 import (
    final_artifact_recovery_stage,
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)


def _result(stage_id: str, *, blocked: bool = False, scanner_truth: bool = False) -> dict:
    if blocked:
        checks = ["canonical_scanner_totals_recompute"] if scanner_truth else []
        return {
            "status": "blocked",
            "reason": "final_artifact_truth_verification_failed",
            "failed_checks": checks,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    return {
        "status": "complete",
        "evidence": {"stage": stage_id},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _first_cross_format_block() -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun_run_wide_recovery_budget",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-run-wide-recovery-budget",
        customer_id="customer-run-wide-recovery-budget",
        project_id="project-run-wide-recovery-budget",
        authorized=True,
    )
    for stage_id in COMPREHENSIVE_STAGES:
        blocked = stage_id == "cross_format_truth_verification"
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=_result(stage_id, blocked=blocked),
        )
        if blocked:
            return record
    raise AssertionError("cross-format stage was not reached")


def test_one_exact_run_cannot_switch_recovery_targets_and_bounce_83_87() -> None:
    first_block = _first_cross_format_block()
    assert final_artifact_recovery_stage(first_block) == "final_comprehensive_report_generation"

    recovered = rewind_blocked_run_for_final_artifact_recovery(first_block)
    assert recovered["status"] == "running"
    assert len(recovered.get("recovery_history") or []) == 1

    second_block = recovered
    start = len(second_block.get("completed_stages") or [])
    for stage_id in COMPREHENSIVE_STAGES[start:]:
        blocked = stage_id == "cross_format_truth_verification"
        second_block = apply_comprehensive_stage_result(
            second_block,
            stage_id=stage_id,
            result=_result(stage_id, blocked=blocked, scanner_truth=blocked),
        )
        if blocked:
            break

    assert final_artifact_recovery_stage(second_block) == "evidence_reconciliation_and_scoring"
    unchanged = rewind_blocked_run_for_final_artifact_recovery(second_block)

    assert unchanged == second_block
    assert unchanged["status"] == "blocked"
    assert unchanged["terminal"] is True
    assert unchanged["current_stage"] == "cross_format_truth_verification"
    assert len(unchanged.get("recovery_history") or []) == 1
