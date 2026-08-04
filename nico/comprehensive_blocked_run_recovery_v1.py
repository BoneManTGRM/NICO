from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record

VERSION = "nico.comprehensive_blocked_run_recovery.v2"
_FINAL_REPORT_STAGE = "final_comprehensive_report_generation"
_SCANNER_REGISTER_RECOVERY_STAGE = "evidence_reconciliation_and_scoring"
_FAILED_STAGE = "cross_format_truth_verification"
_RECOVERABLE_REASONS = {
    "final_artifact_truth_verification_failed",
    "cross_format_final_report_verification_failed",
    "cross_format_truth_verification_failed",
}
_SCANNER_REGISTER_SOURCE_CHECKS = {
    "canonical_scanner_payload_retention_truthful",
    "canonical_scanner_totals_recompute",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _string_values(value: Any) -> set[str]:
    if isinstance(value, str):
        normalized = _text(value)
        return {normalized} if normalized else set()
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {
        normalized
        for item in value
        if (normalized := _text(item))
    }


def _failed_stage_result(record: Mapping[str, Any]) -> Mapping[str, Any]:
    stage_results = record.get("stage_results")
    if not isinstance(stage_results, Mapping):
        return {}
    failed_stage = _text(record.get("current_stage"))
    result = stage_results.get(failed_stage)
    return result if isinstance(result, Mapping) else {}


def blocked_run_recovery_reason(record: dict[str, Any]) -> str:
    result = _failed_stage_result(record)
    return _text(result.get("reason") or result.get("technical_reason"))


def final_artifact_failed_checks(record: Mapping[str, Any]) -> set[str]:
    """Return exact failed final-artifact checks retained on the blocked stage."""

    result = _failed_stage_result(record)
    checks = _string_values(result.get("failed_checks"))
    truth = result.get("final_artifact_truth")
    if isinstance(truth, Mapping):
        checks.update(_string_values(truth.get("failed_checks")))
    evidence = result.get("evidence")
    if isinstance(evidence, Mapping):
        checks.update(_string_values(evidence.get("failed_checks")))
    return checks


def final_artifact_recovery_stage(record: Mapping[str, Any]) -> str:
    """Choose the earliest authoritative stage required to apply the repair.

    Most final-artifact failures concern rendering or validation and need only the
    final report stage regenerated. Scanner-register total or payload-retention
    failures originate in the canonical register built during evidence
    reconciliation. Re-rendering an already malformed register cannot apply a
    corrected candidate-normalization contract, so those exact checks rewind to the
    scoring boundary while preserving the immutable snapshot and raw scanner output.
    """

    failed_checks = final_artifact_failed_checks(record)
    if failed_checks.intersection(_SCANNER_REGISTER_SOURCE_CHECKS):
        return _SCANNER_REGISTER_RECOVERY_STAGE
    return _FINAL_REPORT_STAGE


def is_recoverable_final_artifact_failure(record: dict[str, Any]) -> bool:
    return bool(
        _text(record.get("status")).casefold() == "blocked"
        and record.get("terminal") is True
        and _text(record.get("current_stage")) == _FAILED_STAGE
        and blocked_run_recovery_reason(record) in _RECOVERABLE_REASONS
    )


def rewind_blocked_run_for_final_artifact_recovery(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rewind only as far as the authoritative source of the failed truth check.

    Repository capture, immutable identity, raw scanner output, authorization, and
    the evidence ledger remain unchanged. Ordinary renderer or final-validation
    incidents rerun only final report generation. Scanner-register totals or payload
    retention incidents rerun evidence reconciliation and all downstream stages so
    the corrected register is rebuilt from the same exact-commit scanner evidence.
    """

    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if not is_recoverable_final_artifact_failure(record):
        return record

    recovery_stage = final_artifact_recovery_stage(record)
    failed_checks = sorted(final_artifact_failed_checks(record))
    updated = deepcopy(record)
    target_index = COMPREHENSIVE_STAGES.index(recovery_stage)
    retained_stages = list(COMPREHENSIVE_STAGES[:target_index])
    existing_results = (
        updated.get("stage_results")
        if isinstance(updated.get("stage_results"), dict)
        else {}
    )
    updated["stage_results"] = {
        stage_id: deepcopy(existing_results[stage_id])
        for stage_id in retained_stages
        if stage_id in existing_results
    }
    updated["completed_stages"] = retained_stages
    updated["current_stage"] = retained_stages[-1] if retained_stages else None
    updated["status"] = "running"
    updated["terminal"] = False
    updated["progress_percent"] = round(
        (len(retained_stages) / len(COMPREHENSIVE_STAGES)) * 100,
        2,
    )
    recovered_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    previous_revision = int(updated.get("revision") or 0)
    history = [
        deepcopy(item)
        for item in updated.get("recovery_history") or []
        if isinstance(item, dict)
    ]
    scanner_register_rebuild = recovery_stage == _SCANNER_REGISTER_RECOVERY_STAGE
    history.append(
        {
            "artifact_schema": VERSION,
            "source_failed_stage": _FAILED_STAGE,
            "source_reason": blocked_run_recovery_reason(record),
            "source_failed_checks": failed_checks,
            "rerun_from_stage": recovery_stage,
            "preserved_stage_count": len(retained_stages),
            "exact_run_identity_preserved": True,
            "immutable_repository_snapshot_preserved": True,
            "raw_scanner_evidence_preserved": True,
            "canonical_scanner_register_rebuilt": scanner_register_rebuild,
            "score_recalculation_from_preserved_evidence": scanner_register_rebuild,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "recovered_at": recovered_at,
        }
    )
    updated["recovery_history"] = history
    updated["updated_at"] = recovered_at
    updated["revision"] = previous_revision + 1
    updated["human_review_required"] = True
    updated["human_review_completed"] = False
    updated["client_delivery_allowed"] = False
    for key in (
        "accepted_edition",
        "approved_delivery_package",
        "review_context",
        "review_decision",
    ):
        updated.pop(key, None)
    updated["integrity_sha256"] = _record_hash(updated)

    final_validation = validate_comprehensive_run_record(updated)
    if final_validation["status"] != "valid":
        raise ValueError(
            "invalid_recovered_run_record:"
            + ",".join(final_validation["violations"])
        )
    return updated


__all__ = [
    "VERSION",
    "blocked_run_recovery_reason",
    "final_artifact_failed_checks",
    "final_artifact_recovery_stage",
    "is_recoverable_final_artifact_failure",
    "rewind_blocked_run_for_final_artifact_recovery",
]
