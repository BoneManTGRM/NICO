from __future__ import annotations

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


_PRODUCTION_REASON = (
    "v2_production_publication_failed:ValueError:missing Spanish presentation translation "
    "for acceptance_criteria: The exact-SHA rerun no longer reports cyclomatic complexity "
    "above 30 at nico/comprehensive_review_work_v1.py:323"
)


def _blocked_at(stage_to_block: str, run_id: str) -> dict:
    record = create_comprehensive_run_record(
        run_id=run_id,
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id=f"ledger-{run_id}",
        customer_id="customer-production-recovery",
        project_id="project-production-recovery",
        authorized=True,
        report_language="es-MX",
    )
    for stage_id in COMPREHENSIVE_STAGES:
        result = {
            "status": "complete",
            "evidence": {"stage": stage_id, "exact_commit_sha": "a" * 40},
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        if stage_id == stage_to_block:
            result = {
                "status": "blocked",
                "reason": _PRODUCTION_REASON,
                "technical_reason": _PRODUCTION_REASON,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
        )
        if stage_id == stage_to_block:
            break
    return record


def test_current_spanish_final_publication_failure_is_recoverable_on_new_generation() -> None:
    blocked = _blocked_at(
        "final_comprehensive_report_generation",
        "comprun_9984093ce1b34acb98dc444447f13242",
    )

    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert blocked_run_recovery_reason(blocked) == "v2_production_publication_failed"
    assert is_recoverable_final_artifact_failure(blocked) is True
    assert final_artifact_recovery_stage(blocked) == "final_comprehensive_report_generation"

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)
    target_index = COMPREHENSIVE_STAGES.index("final_comprehensive_report_generation")

    assert recovered["identity"]["run_id"] == blocked["identity"]["run_id"]
    assert recovered["identity"]["commit_sha"] == blocked["identity"]["commit_sha"]
    assert recovered["identity"]["report_language"] == "es-MX"
    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["completed_stages"] == list(COMPREHENSIVE_STAGES[:target_index])
    assert "final_comprehensive_report_generation" not in recovered["stage_results"]
    history = recovered["recovery_history"][-1]
    assert history["artifact_schema"] == VERSION
    assert history["source_reason"] == "v2_production_publication_failed"
    assert history["rerun_from_stage"] == "final_comprehensive_report_generation"
    assert history["recovery_scope"] == "final_report_only"
    assert history["exact_run_identity_preserved"] is True
    assert history["raw_scanner_evidence_preserved"] is True
    assert history["human_review_required"] is True
    assert history["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"


def test_decision_report_publication_failure_rewinds_decision_report_and_downstream() -> None:
    blocked = _blocked_at(
        "decision_report_generation",
        "comprun_decision_publication_recovery",
    )

    assert blocked_run_recovery_reason(blocked) == "v2_production_publication_failed"
    assert is_recoverable_final_artifact_failure(blocked) is True
    assert final_artifact_recovery_stage(blocked) == "decision_report_generation"

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)
    target_index = COMPREHENSIVE_STAGES.index("decision_report_generation")
    assert recovered["completed_stages"] == list(COMPREHENSIVE_STAGES[:target_index])
    assert "decision_report_generation" not in recovered["stage_results"]
    assert recovered["recovery_history"][-1]["recovery_scope"] == "decision_report_and_downstream"


def test_publication_recovery_remains_bounded_per_generation() -> None:
    blocked = _blocked_at(
        "final_comprehensive_report_generation",
        "comprun_publication_recovery_bound",
    )
    first = rewind_blocked_run_for_final_artifact_recovery(blocked)

    # Recreate the same final-stage failure after the one allowed v9 recovery attempt.
    retry = first
    retry = apply_comprehensive_stage_result(
        retry,
        stage_id="final_comprehensive_report_generation",
        result={
            "status": "blocked",
            "reason": _PRODUCTION_REASON,
            "technical_reason": _PRODUCTION_REASON,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )

    assert retry["terminal"] is True
    assert rewind_blocked_run_for_final_artifact_recovery(retry) == retry
