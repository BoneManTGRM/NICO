from __future__ import annotations

from nico.comprehensive_blocked_run_recovery_v1 import (
    VERSION,
    blocked_run_recovery_reason,
    final_artifact_failed_checks,
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


SCANNER_TRUTH_CHECKS = [
    "canonical_scanner_payload_retention_truthful",
    "canonical_scanner_totals_recompute",
]


def _new_record(run_id: str = "comprun_recovery_v1") -> dict:
    return create_comprehensive_run_record(
        run_id=run_id,
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-recovery-v1",
        customer_id="customer-recovery-v1",
        project_id="project-recovery-v1",
        authorized=True,
    )


def _blocked_record(
    reason: str = "final_artifact_truth_verification_failed",
    *,
    failed_checks: list[str] | None = None,
) -> dict:
    record = _new_record()
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id == "cross_format_truth_verification":
            result = {
                "status": "blocked",
                "reason": reason,
                "failed_checks": list(failed_checks or []),
                "final_artifact_truth": {
                    "status": "blocked",
                    "failed_checks": list(failed_checks or []),
                    "checks": {
                        check: False for check in failed_checks or []
                    },
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


def _final_report_timeout_record() -> dict:
    record = _new_record("comprun_c29de84e0bfe475d89bf4734028edf97")
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id == "final_comprehensive_report_generation":
            result = {
                "status": "blocked",
                "technical_reason": (
                    "final_report_execution_timeout:"
                    "stage=final_comprehensive_report_generation"
                ),
                "stage_execution": {
                    "execution_timeout_seconds": 240,
                    "elapsed_seconds": 240.001,
                    "recovery_supported": True,
                    "recovery_scope": "final_report_only",
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        else:
            result = {
                "status": "complete",
                "evidence": {
                    "stage": stage_id,
                    "exact_commit_sha": "a" * 40,
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
        )
        if stage_id == "final_comprehensive_report_generation":
            break
    return record


def test_final_report_timeout_rewinds_only_final_report_and_preserves_evidence() -> None:
    blocked = _final_report_timeout_record()
    identity = dict(blocked["identity"])
    scanner_evidence = blocked["stage_results"][
        "dependency_security_static_analysis"
    ]
    traceability = blocked["stage_results"]["requirements_traceability"]

    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert blocked_run_recovery_reason(blocked) == "final_report_execution_timeout"
    assert is_recoverable_final_artifact_failure(blocked) is True
    assert final_artifact_recovery_stage(blocked) == (
        "final_comprehensive_report_generation"
    )

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)
    target_index = COMPREHENSIVE_STAGES.index(
        "final_comprehensive_report_generation"
    )

    assert recovered["identity"] == identity
    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["completed_stages"] == list(COMPREHENSIVE_STAGES[:target_index])
    assert recovered["stage_results"][
        "dependency_security_static_analysis"
    ] == scanner_evidence
    assert recovered["stage_results"]["requirements_traceability"] == traceability
    assert "final_comprehensive_report_generation" not in recovered["stage_results"]
    assert "cross_format_truth_verification" not in recovered["stage_results"]

    history = recovered["recovery_history"][-1]
    assert history["artifact_schema"] == VERSION
    assert history["source_failed_stage"] == "final_comprehensive_report_generation"
    assert history["source_reason"] == "final_report_execution_timeout"
    assert history["rerun_from_stage"] == "final_comprehensive_report_generation"
    assert history["recovery_scope"] == "final_report_only"
    assert history["exact_run_identity_preserved"] is True
    assert history["raw_scanner_evidence_preserved"] is True
    assert history["canonical_scanner_register_rebuilt"] is False
    assert history["score_recalculation_from_preserved_evidence"] is False
    assert history["human_review_required"] is True
    assert history["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"

    assert rewind_blocked_run_for_final_artifact_recovery(recovered) == recovered


def test_final_artifact_failure_rewinds_only_the_publication_boundary() -> None:
    blocked = _blocked_record()
    identity = dict(blocked["identity"])
    preserved_snapshot = blocked["stage_results"]["immutable_repository_snapshot"]

    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert is_recoverable_final_artifact_failure(blocked) is True
    assert final_artifact_failed_checks(blocked) == set()
    assert final_artifact_recovery_stage(blocked) == (
        "final_comprehensive_report_generation"
    )

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
    history = recovered["recovery_history"][-1]
    assert history["artifact_schema"] == VERSION
    assert history["source_failed_stage"] == "cross_format_truth_verification"
    assert history["exact_run_identity_preserved"] is True
    assert history["rerun_from_stage"] == "final_comprehensive_report_generation"
    assert history["recovery_scope"] == "final_report_only"
    assert history["canonical_scanner_register_rebuilt"] is False
    assert history["score_recalculation_from_preserved_evidence"] is False
    assert history["human_review_required"] is True
    assert history["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"


def test_scanner_register_truth_failure_rewinds_to_reconciliation() -> None:
    blocked = _blocked_record(failed_checks=SCANNER_TRUTH_CHECKS)
    identity = dict(blocked["identity"])
    snapshot = blocked["stage_results"]["immutable_repository_snapshot"]
    scanner = blocked["stage_results"]["dependency_security_static_analysis"]

    assert final_artifact_failed_checks(blocked) == set(SCANNER_TRUTH_CHECKS)
    assert final_artifact_recovery_stage(blocked) == (
        "evidence_reconciliation_and_scoring"
    )

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)
    target_index = COMPREHENSIVE_STAGES.index(
        "evidence_reconciliation_and_scoring"
    )

    assert recovered["identity"] == identity
    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["completed_stages"] == list(COMPREHENSIVE_STAGES[:target_index])
    assert recovered["stage_results"]["immutable_repository_snapshot"] == snapshot
    assert recovered["stage_results"]["dependency_security_static_analysis"] == scanner
    assert "evidence_reconciliation_and_scoring" not in recovered["stage_results"]
    assert "decision_report_generation" not in recovered["stage_results"]
    assert "deep_scanner_triage" not in recovered["stage_results"]
    assert "final_comprehensive_report_generation" not in recovered["stage_results"]
    assert "cross_format_truth_verification" not in recovered["stage_results"]

    history = recovered["recovery_history"][-1]
    assert history["artifact_schema"] == VERSION
    assert history["source_failed_checks"] == sorted(SCANNER_TRUTH_CHECKS)
    assert history["rerun_from_stage"] == "evidence_reconciliation_and_scoring"
    assert history["recovery_scope"] == "evidence_reconciliation_and_downstream"
    assert history["immutable_repository_snapshot_preserved"] is True
    assert history["raw_scanner_evidence_preserved"] is True
    assert history["canonical_scanner_register_rebuilt"] is True
    assert history["score_recalculation_from_preserved_evidence"] is True
    assert history["human_review_required"] is True
    assert history["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"


def test_scanner_failed_checks_are_read_from_nested_truth_when_top_level_is_absent() -> None:
    blocked = _blocked_record(failed_checks=SCANNER_TRUTH_CHECKS)
    blocked["stage_results"]["cross_format_truth_verification"].pop(
        "failed_checks",
        None,
    )

    assert final_artifact_failed_checks(blocked) == set(SCANNER_TRUTH_CHECKS)
    assert final_artifact_recovery_stage(blocked) == (
        "evidence_reconciliation_and_scoring"
    )


def test_unrecognized_final_check_keeps_narrow_publication_recovery() -> None:
    blocked = _blocked_record(failed_checks=["pdf_identifier_integrity"])

    assert final_artifact_recovery_stage(blocked) == (
        "final_comprehensive_report_generation"
    )
    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)
    assert recovered["recovery_history"][-1]["rerun_from_stage"] == (
        "final_comprehensive_report_generation"
    )
    assert recovered["recovery_history"][-1][
        "canonical_scanner_register_rebuilt"
    ] is False


def test_unrelated_terminal_failure_is_not_rewound() -> None:
    blocked = _blocked_record("unrelated_failure")

    assert is_recoverable_final_artifact_failure(blocked) is False
    assert rewind_blocked_run_for_final_artifact_recovery(blocked) == blocked
