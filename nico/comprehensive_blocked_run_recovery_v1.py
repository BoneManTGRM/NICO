from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record

VERSION = "nico.comprehensive_blocked_run_recovery.v10"
_DECISION_REPORT_STAGE = "decision_report_generation"
_FINAL_REPORT_STAGE = "final_comprehensive_report_generation"
_CROSS_FORMAT_STAGE = "cross_format_truth_verification"
_EXECUTIVE_BRIEFING_RECOVERY_STAGE = "risk_reduction_and_executive_briefing"
_SCANNER_REGISTER_RECOVERY_STAGE = "evidence_reconciliation_and_scoring"
_MAX_AUTOMATIC_RECOVERY_ATTEMPTS_PER_SOURCE_STAGE = 1
_RECOVERY_BUDGET_SCOPE = "source_failed_stage_recovery_generation"
_RECOVERABLE_REASONS_BY_STAGE = {
    _DECISION_REPORT_STAGE: {
        "detached_stage_execution_failed",
        "v2_production_publication_failed",
    },
    _FINAL_REPORT_STAGE: {
        "detached_stage_execution_failed",
        "final_report_execution_timeout",
        "final_report_publication_deadline_exceeded",
        "v2_production_publication_failed",
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
_EXECUTIVE_BRIEFING_SOURCE_CHECKS = {
    "stage_score_evidence_matches_canonical",
}
_STAGE_ALIASES = {
    "decision report generation": _DECISION_REPORT_STAGE,
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


def _automatic_recovery_attempt_count(
    record: Mapping[str, Any],
    *,
    source_failed_stage: str,
) -> int:
    """Count bounded attempts for this source stage in the current repair generation.

    A recovery attempt must remain bounded so a persistent provider defect cannot loop
    indefinitely. It must also not permanently brick a durable run after the underlying
    production defect is repaired in a later recovery generation. Older recovery-history
    entries therefore remain immutable evidence but do not consume the one-attempt budget
    of this version. The current generation still permits at most one automatic rewind
    per failed source stage.
    """

    history = record.get("recovery_history")
    if not isinstance(history, list):
        return 0
    return sum(
        1
        for item in history
        if isinstance(item, Mapping)
        and _stage_id(item.get("source_failed_stage")) == source_failed_stage
        and _text(item.get("recovery_budget_scope")) == _RECOVERY_BUDGET_SCOPE
        and _text(item.get("recovery_generation")) == VERSION
    )


def _recovery_reason_candidates(record: Mapping[str, Any]) -> list[str]:
    """Return bounded persisted failure reasons without hiding technical detail.

    Some historical detached-stage records retained a generic public ``reason`` while
    keeping the actionable runtime cause in ``technical_reason``. Recovery eligibility
    must therefore inspect both persisted fields while remaining stage allow-listed.
    """

    result = _failed_stage_result(record)
    candidates: list[str] = []
    for key in ("reason", "technical_reason"):
        value = _text(result.get(key)).split(":", 1)[0]
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def blocked_run_recovery_reason(record: Mapping[str, Any]) -> str:
    candidates = _recovery_reason_candidates(record)
    recoverable = _RECOVERABLE_REASONS_BY_STAGE.get(
        _current_failed_stage(record),
        set(),
    )
    for candidate in candidates:
        if candidate in recoverable:
            return candidate
    return candidates[0] if candidates else ""


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

    A detached decision-report execution failure reruns the decision-report stage and
    its downstream Comprehensive stages from the already-persisted exact-run evidence.
    A final-report execution/publication failure resumes only final report generation.
    Cross-format scanner-register total or payload-retention failures originate in
    evidence reconciliation and therefore rewind to that boundary. A stage-score
    evidence mismatch caused by the Phase 3 executive briefing is repaired by
    regenerating that briefing and downstream report artifacts from preserved canonical
    scoring. Other recognized final-artifact failures regenerate only the final package.
    """

    failed_stage = _current_failed_stage(record)
    if failed_stage in {_DECISION_REPORT_STAGE, _FINAL_REPORT_STAGE}:
        return failed_stage
    failed_checks = final_artifact_failed_checks(record)
    if failed_checks.intersection(_SCANNER_REGISTER_SOURCE_CHECKS):
        return _SCANNER_REGISTER_RECOVERY_STAGE
    if failed_checks.intersection(_EXECUTIVE_BRIEFING_SOURCE_CHECKS):
        return _EXECUTIVE_BRIEFING_RECOVERY_STAGE
    return _FINAL_REPORT_STAGE


def is_recoverable_final_artifact_failure(record: Mapping[str, Any]) -> bool:
    failed_stage = _current_failed_stage(record)
    recoverable_reasons = _RECOVERABLE_REASONS_BY_STAGE.get(failed_stage, set())
    reasons = _recovery_reason_candidates(record)
    return bool(
        _text(record.get("status")).casefold() == "blocked"
        and record.get("terminal") is True
        and any(reason in recoverable_reasons for reason in reasons)
    )


def rewind_blocked_run_for_final_artifact_recovery(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rewind once per repair generation to the authoritative failed source stage.

    Repository capture, exact run identity, raw scanner output, authorization, and the
    evidence ledger remain unchanged. A stale detached decision-report failure reruns
    the decision report and downstream stages; a final-report failure reruns only final
    report generation. Scanner-register truth failures rerun evidence reconciliation
    and downstream stages from the same exact-commit evidence. Phase 3 stage-score
    evidence mismatches regenerate the executive briefing and downstream artifacts from
    preserved canonical scoring. Each failed source stage receives one automatic repair
    attempt in this recovery generation. Older generations stay in immutable history but
    cannot permanently prevent a repaired deployment from recovering the same durable
    run. A repeated failure under this generation stays terminal and visible. Human
    approval and client delivery remain blocked.
    """

    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if not is_recoverable_final_artifact_failure(record):
        return record

    source_failed_stage = _current_failed_stage(record)
    recovery_stage = final_artifact_recovery_stage(record)
    if (
        _automatic_recovery_attempt_count(
            record,
            source_failed_stage=source_failed_stage,
        )
        >= _MAX_AUTOMATIC_RECOVERY_ATTEMPTS_PER_SOURCE_STAGE
    ):
        return record

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
    if scanner_register_rebuild:
        recovery_scope = "evidence_reconciliation_and_downstream"
    elif recovery_stage == _EXECUTIVE_BRIEFING_RECOVERY_STAGE:
        recovery_scope = "executive_briefing_and_downstream"
    elif recovery_stage == _DECISION_REPORT_STAGE:
        recovery_scope = "decision_report_and_downstream"
    else:
        recovery_scope = "final_report_only"
    history.append(
        {
            "artifact_schema": VERSION,
            "source_failed_stage": source_failed_stage,
            "source_reason": blocked_run_recovery_reason(record),
            "source_failed_checks": failed_checks,
            "rerun_from_stage": recovery_stage,
            "recovery_scope": recovery_scope,
            "recovery_budget_scope": _RECOVERY_BUDGET_SCOPE,
            "recovery_generation": VERSION,
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
