from __future__ import annotations

from nico.comprehensive_blocked_run_recovery_v1 import (
    is_recoverable_final_artifact_failure,
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)


def _blocked_record(reason: str = "final_artifact_truth_verification_failed") -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun_recovery_v1",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-recovery-v1",
        customer_id="customer-recovery-v1",
        project_id="project-recovery-v1",
        authorized=True,
    )
    for stage_id in COMPREHENSIVE_STAGES:
        result = (
            {"status": "blocked", "reason": reason}
            if stage_id == "cross_format_truth_verification"
            else {"status": "complete", "evidence": {"stage": stage_id}}
        )
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
        )
        if stage_id == "cross_format_truth_verification":
            break
    return record


def test_final_artifact_failure_rewinds_only_the_publication_boundary() -> None:
    blocked = _blocked_record()
    identity = dict(blocked["identity"])
    preserved_snapshot = blocked["stage_results"]["immutable_repository_snapshot"]

    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert is_recoverable_final_artifact_failure(blocked) is True

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)
    target_index = COMPREHENSIVE_STAGES.index(
        "final_comprehensive_report_generation"
    )

    assert recovered["identity"] == identity
    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["completed_stages"] == list(COMPREHENSIVE_STAGES[:target_index])
    assert "final_comprehensive_report_generation" not in recovered["stage_results"]
    assert "cross_format_truth_verification" not in recovered["stage_results"]
    assert recovered["stage_results"]["immutable_repository_snapshot"] == preserved_snapshot
    assert recovered["recovery_history"][-1]["exact_run_identity_preserved"] is True
    assert recovered["recovery_history"][-1]["rerun_from_stage"] == (
        "final_comprehensive_report_generation"
    )
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"


def test_unrelated_terminal_failure_is_not_rewound() -> None:
    blocked = _blocked_record("unrelated_failure")

    assert is_recoverable_final_artifact_failure(blocked) is False
    assert rewind_blocked_run_for_final_artifact_recovery(blocked) == blocked
