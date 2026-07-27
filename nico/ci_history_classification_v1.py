from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

VERSION = "nico.ci_history_classification.v1"

_SUCCESS = {"success"}
_NEUTRAL = {"neutral", "skipped"}
_CANCELLED = {"cancelled", "canceled"}
_FAILURE = {"failure", "timed_out", "startup_failure", "action_required"}
_INFRA = {"stale"}
_ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def classify_workflow_run(run: dict[str, Any]) -> dict[str, Any]:
    status = _text(run.get("status")).lower()
    conclusion = _text(run.get("conclusion")).lower()
    event = _text(run.get("event")).lower()
    reason_hint = " ".join(
        _text(run.get(key)).lower()
        for key in ("reason", "message", "display_title", "name")
    )

    blockers: list[str] = []
    if not run.get("id"):
        blockers.append("run_id_missing")
    if not _text(run.get("name")):
        blockers.append("workflow_name_missing")
    if status == "completed" and not conclusion:
        blockers.append("completed_without_conclusion")
    if status != "completed" and conclusion:
        blockers.append("nonterminal_with_conclusion")

    category = "unknown_review_required"
    reason = "unrecognized_workflow_state"
    affects_historical_failure_rate = False

    if blockers:
        reason = blockers[0]
    elif status in _ACTIVE or (status and status != "completed"):
        category = "active_not_historical"
        reason = f"status:{status or 'unknown'}"
    elif conclusion in _SUCCESS:
        category = "success"
        reason = "completed_successfully"
    elif conclusion in _NEUTRAL:
        category = "neutral_or_skipped"
        reason = f"conclusion:{conclusion}"
    elif conclusion in _CANCELLED:
        if any(token in reason_hint for token in ("superseded", "newer run", "concurrency")):
            category = "superseded_cancellation"
            reason = "cancelled_by_newer_or_concurrent_run"
        elif any(token in reason_hint for token in ("manual", "user cancelled", "canceled by")):
            category = "manual_cancellation"
            reason = "explicit_manual_cancellation"
        else:
            category = "expected_or_unclassified_cancellation"
            reason = "cancelled_without_failure_evidence"
    elif conclusion in _INFRA or any(
        token in reason_hint
        for token in ("runner lost", "hosted runner", "service unavailable", "infrastructure", "billing")
    ):
        category = "infrastructure_fault"
        reason = "runner_or_platform_fault"
    elif conclusion in _FAILURE:
        category = "genuine_failure"
        reason = f"conclusion:{conclusion}"
        affects_historical_failure_rate = True
    elif event == "workflow_dispatch" and conclusion == "":
        category = "unknown_review_required"
        reason = "manual_run_without_terminal_conclusion"

    return {
        "schema": VERSION,
        "run_id": run.get("id"),
        "workflow_name": _text(run.get("name")),
        "status": status,
        "conclusion": conclusion,
        "event": event,
        "head_sha": _text(run.get("head_sha"), 64),
        "actor": _text((run.get("actor") or {}).get("login") if isinstance(run.get("actor"), dict) else run.get("actor")),
        "created_at": _text(run.get("created_at"), 64),
        "updated_at": _text(run.get("updated_at"), 64),
        "category": category,
        "reason": reason,
        "metadata_blockers": blockers,
        "review_required": category == "unknown_review_required",
        "affects_historical_failure_rate": affects_historical_failure_rate,
    }


def classify_workflow_history(
    runs: Iterable[dict[str, Any]],
    *,
    current_required_checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    classified = [classify_workflow_run(dict(run)) for run in runs]
    counts = Counter(item["category"] for item in classified)
    denominator = counts["success"] + counts["genuine_failure"]
    historical_failure_rate = (
        counts["genuine_failure"] / denominator if denominator else None
    )
    review_ids = [item["run_id"] for item in classified if item["review_required"]]
    current = dict(current_required_checks or {})
    current_green = bool(current) and all(
        str(value).lower() in {"success", "neutral", "skipped"}
        for value in current.values()
    )
    return {
        "schema": "nico.ci_history_summary.v1",
        "historical_reliability": {
            "total_runs": len(classified),
            "classified_counts": dict(sorted(counts.items())),
            "genuine_failure_denominator": denominator,
            "genuine_failure_rate": historical_failure_rate,
            "review_required_run_ids": review_ids,
        },
        "current_branch_health": {
            "required_checks": current,
            "green": current_green,
            "independent_from_historical_reliability": True,
        },
        "runs": classified,
        "cancellations_counted_as_failures": False,
        "unknown_metadata_fails_closed": True,
    }


def install_ci_history_classification_v1() -> dict[str, Any]:
    return {
        "status": "installed",
        "version": VERSION,
        "deterministic_classification": True,
        "historical_and_current_health_separated": True,
        "unknown_metadata_fails_closed": True,
        "cancellations_excluded_from_failure_rate": True,
        "provenance_retained": True,
    }


__all__ = [
    "VERSION",
    "classify_workflow_run",
    "classify_workflow_history",
    "install_ci_history_classification_v1",
]
