from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record

VERSION = "nico.comprehensive_blocked_run_recovery.v1"
_RECOVERY_STAGE = "final_comprehensive_report_generation"
_FAILED_STAGE = "cross_format_truth_verification"
_RECOVERABLE_REASONS = {
    "final_artifact_truth_verification_failed",
    "cross_format_final_report_verification_failed",
    "cross_format_truth_verification_failed",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def blocked_run_recovery_reason(record: dict[str, Any]) -> str:
    stage_results = record.get("stage_results")
    if not isinstance(stage_results, dict):
        return ""
    failed_stage = _text(record.get("current_stage"))
    result = stage_results.get(failed_stage)
    if not isinstance(result, dict):
        return ""
    return _text(result.get("reason") or result.get("technical_reason"))


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
    """Rewind only the report publication boundary while preserving exact-run evidence.

    Repository capture, scanner output, scoring inputs, strategic modules, identity, and
    the evidence ledger remain unchanged. The final report is regenerated and then
    rechecked by cross-format truth verification under the corrected runtime.
    """

    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if not is_recoverable_final_artifact_failure(record):
        return record

    updated = deepcopy(record)
    target_index = COMPREHENSIVE_STAGES.index(_RECOVERY_STAGE)
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
    history.append(
        {
            "artifact_schema": VERSION,
            "source_failed_stage": _FAILED_STAGE,
            "source_reason": blocked_run_recovery_reason(record),
            "rerun_from_stage": _RECOVERY_STAGE,
            "preserved_stage_count": len(retained_stages),
            "exact_run_identity_preserved": True,
            "repository_and_scanner_evidence_preserved": True,
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
    "is_recoverable_final_artifact_failure",
    "rewind_blocked_run_for_final_artifact_recovery",
]
