from __future__ import annotations

from nico.comprehensive_blocked_run_recovery_v1 import (
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)


SCANNER_TRUTH_CHECKS = [
    "canonical_scanner_payload_retention_truthful",
    "canonical_scanner_totals_recompute",
]


def _blocked_cross_format_record(*, failed_checks: list[str] | None = None) -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun_recovery_retry_bound",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-recovery-retry-bound",
        customer_id="customer-recovery-retry-bound",
        project_id="project-recovery-retry-bound",
        authorized=True,
    )
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id == "cross_format_truth_verification":
            checks = list(failed_checks or [])
            result = {
                "status": "blocked",
                "reason": "final_artifact_truth_verification_failed",
                "failed_checks": checks,
                "final_artifact_truth": {
                    "status": "blocked",
                    "failed_checks": checks,
                    "checks": {check: False for check in checks},
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        else:
            result = {
                "status": "complete",
                "evidence": {"stage": stage_id},
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
        )
        if stage_id == "cross_format_truth_verification":
            break
    return record


def _replay_to_original_block(
    recovered: dict,
    original_blocked: dict,
) -> dict:
    replayed = recovered
    start_index = len(replayed.get("completed_stages") or [])
    blocked_index = COMPREHENSIVE_STAGES.index("cross_format_truth_verification")
    for stage_id in COMPREHENSIVE_STAGES[start_index : blocked_index + 1]:
        replayed = apply_comprehensive_stage_result(
            replayed,
            stage_id=stage_id,
            result=original_blocked["stage_results"][stage_id],
        )
    return replayed


def test_matching_final_artifact_recovery_is_attempted_only_once() -> None:
    blocked = _blocked_cross_format_record()
    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)

    assert recovered["status"] == "running"
    assert len(recovered["recovery_history"]) == 1
    assert recovered["recovery_history"][0]["source_failed_stage"] == (
        "cross_format_truth_verification"
    )
    assert recovered["recovery_history"][0]["rerun_from_stage"] == (
        "final_comprehensive_report_generation"
    )

    reblocked = _replay_to_original_block(recovered, blocked)
    progress_at_real_failure = reblocked["progress_percent"]
    assert reblocked["status"] == "blocked"
    assert reblocked["terminal"] is True
    assert validate_comprehensive_run_record(reblocked)["status"] == "valid"

    exhausted = rewind_blocked_run_for_final_artifact_recovery(reblocked)

    assert exhausted == reblocked
    assert exhausted["progress_percent"] == progress_at_real_failure
    assert exhausted["current_stage"] == "cross_format_truth_verification"
    assert exhausted["stage_results"]["cross_format_truth_verification"]["status"] == (
        "blocked"
    )
    assert len(exhausted["recovery_history"]) == 1
    assert validate_comprehensive_run_record(exhausted)["status"] == "valid"


def test_scanner_register_recovery_has_an_independent_single_attempt_budget() -> None:
    blocked = _blocked_cross_format_record(failed_checks=SCANNER_TRUTH_CHECKS)
    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)

    assert recovered["status"] == "running"
    assert len(recovered["recovery_history"]) == 1
    assert recovered["recovery_history"][0]["source_failed_stage"] == (
        "cross_format_truth_verification"
    )
    assert recovered["recovery_history"][0]["rerun_from_stage"] == (
        "evidence_reconciliation_and_scoring"
    )
    assert recovered["recovery_history"][0]["canonical_scanner_register_rebuilt"] is True

    reblocked = _replay_to_original_block(recovered, blocked)
    assert reblocked["status"] == "blocked"
    assert reblocked["terminal"] is True
    assert validate_comprehensive_run_record(reblocked)["status"] == "valid"

    exhausted = rewind_blocked_run_for_final_artifact_recovery(reblocked)

    assert exhausted == reblocked
    assert exhausted["current_stage"] == "cross_format_truth_verification"
    assert exhausted["stage_results"]["cross_format_truth_verification"]["failed_checks"] == (
        SCANNER_TRUTH_CHECKS
    )
    assert len(exhausted["recovery_history"]) == 1
    assert validate_comprehensive_run_record(exhausted)["status"] == "valid"
