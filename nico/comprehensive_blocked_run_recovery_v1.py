from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record

VERSION = "nico.comprehensive_blocked_run_recovery.v3"
_FINAL_REPORT_STAGE = "final_comprehensive_report_generation"
_CROSS_FORMAT_STAGE = "cross_format_truth_verification"
_SCANNER_REGISTER_RECOVERY_STAGE = "evidence_reconciliation_and_scoring"
_RECOVERABLE_REASONS_BY_STAGE = {
    _FINAL_REPORT_STAGE: {
        "final_report_execution_timeout",
    },
    _CROSS_FORMAT_STAGE: {
        "final_artifact_truth_verification_failed",
        "cross_format_final_report_verification_failed",
        "cross_format_truth_verification_failed",
    },
}
_SCANNER_REGISTER_SOURCE_CHECKS = {
    "canonical_scanner_payload_retention_truthful",
    "canonical_scanner_totals_recompute",
}
_STAGE_ALIASES = {
    "final comprehensive report generation": _FINAL_REPORT_STAGE,
    "cross format truth verification": _CROSS_FORMAT_STAGE,
    "cross-format truth verification": _CROSS_FORMAT_STAGE,
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _stage_id(value: Any) -> str:
    raw = _text(value)
    if raw in COMPREHENSIVE_STAGES:
        return raw
    normalized = raw.casefold().replace("_", " ")
    return _STAGE_ALIASES.get(normalized, raw)


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


def _current_failed_stage(record: Mapping[str, Any]) -> str:
    return _stage_id(record.get("current_stage"))


def _failed_stage_result(record: Mapping[str, Any]) -> Mapping[str, Any]:
    stage_results = record.get("stage_results")
    if not isinstance(stage_results, Mapping):
        return {}
    failed_stage = _current_failed_stage(record)
    result = stage_results.get(failed_stage)
    return result if isinstance(result, Mapping) else {}


def blocked_run_recovery_reason(record: Mapping[str, Any]) -> str:
    result = _failed_stage_result(record)
    reason = _text(result.get("reason"))
    if not reason:
        reason = _text(result.get("technical_reason"))
    return reason.split(":", 1)[0]


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

    A final-report execution timeout resumes only final report generation using the
    already-persisted exact-run evidence. Cross-format scanner-register total or
    payload-retention failures originate in evidence reconciliation and therefore
    rewind to that boundary. Other recognized final-artifact failures regenerate only
    the final report package.
    """

    if _current_failed_stage(record) == _FINAL_REPORT_STAGE:
        return _FINAL_REPORT_STAGE
    failed_checks = final_artifact_failed_checks(record)
    if failed_checks.intersection(_SCANNER_REGISTER_SOURCE_CHECKS):
        return _SCANNER_REGISTER_RECOVERY_STAGE
    return _FINAL_REPORT_STAGE


def is_recoverable_final_artifact_failure(record: Mapping[str, Any]) -> bool:
    failed_stage = _current_failed_stage(record)
    recoverable_reasons = _RECOVERABLE_REASONS_BY_STAGE.get(failed_stage, set())
    return bool(
        _text(record.get("status")).casefold() == "blocked"
        and record.get("terminal") is True
        and blocked_run_recovery_reason(record) in recoverable_reasons
    )


def rewind_blocked_run_for_final_artifact_recovery(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rewind only as far as the authoritative source of the failed report result.

    Repository capture, exact run identity, raw scanner output, authorization, and the
    evidence ledger remain unchanged. A final-report timeout reruns only final report
    generation. Scanner-register truth failures rerun evidence reconciliation and all
    downstream stages from the same exact-commit evidence. Human approval and client
    delivery remain blocked.
    """

    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if not is_recoverable_final_artifact_failure(record):
        return record

    source_failed_stage = _current_failed_stage(record)
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
    recovery_scope = (
        "evidence_reconciliation_and_downstream"
        if scanner_register_rebuild
        else "final_report_only"
    )
    history.append(
        {
            "artifact_schema": VERSION,
            "source_failed_stage": source_failed_stage,
            "source_reason": blocked_run_recovery_reason(record),
            "source_failed_checks": failed_checks,
            "rerun_from_stage": recovery_stage,
            "recovery_scope": recovery_scope,
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
