from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    _record_hash,
    validate_comprehensive_run_record,
)

VERSION = "nico.comprehensive_stage_watchdog.v1"
ACTIVE_STATUSES = {"queued", "running", "pending", "planned", "in_progress"}
STALL_REASON = "stage_progress_stalled"
DEFAULT_MAX_NO_PROGRESS_ATTEMPTS = 120
DEFAULT_STALL_TIMEOUT_SECONDS = 600
MAX_RECOVERY_ATTEMPTS = 1

_TRANSIENT_SIGNAL_KEYS = {
    "checked_at",
    "created_at",
    "heartbeat_at",
    "last_checked_at",
    "last_poll_at",
    "polled_at",
    "request_id",
    "revision",
    "timestamp",
    "updated_at",
    "watchdog",
}


def _now(value: datetime | None = None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _max_no_progress_attempts() -> int:
    return _bounded_int(
        "NICO_COMPREHENSIVE_STAGE_MAX_NO_PROGRESS_ATTEMPTS",
        DEFAULT_MAX_NO_PROGRESS_ATTEMPTS,
        5,
        2_000,
    )


def _stall_timeout_seconds() -> int:
    return _bounded_int(
        "NICO_COMPREHENSIVE_STAGE_STALL_TIMEOUT_SECONDS",
        DEFAULT_STALL_TIMEOUT_SECONDS,
        60,
        7_200,
    )


def _percent(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return round(max(0.0, min(100.0, parsed)), 2)


def _progress(result: Mapping[str, Any]) -> float | None:
    for container in (
        result,
        result.get("scanner") if isinstance(result.get("scanner"), Mapping) else {},
        result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {},
        result.get("metrics") if isinstance(result.get("metrics"), Mapping) else {},
    ):
        for key in ("progress_percent", "stage_progress_percent", "completion_percent"):
            parsed = _percent(container.get(key))
            if parsed is not None:
                return parsed
    return None


def _stable_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return str(type(value).__name__)
    if isinstance(value, Mapping):
        return {
            str(key): _stable_value(item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _TRANSIENT_SIGNAL_KEYS
            and str(key) not in {"raw_evidence", "raw_output", "logs", "report_package"}
        }
    if isinstance(value, list):
        return [_stable_value(item, depth=depth + 1) for item in value[:80]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _signal(result: Mapping[str, Any]) -> str:
    payload = _stable_value(result)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_stage_watchdog(
    record: Mapping[str, Any],
    *,
    stage_id: str,
    result: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Convert an indefinitely unchanged active stage into a truthful terminal failure.

    Revision-only writes, polling timestamps, and heartbeats do not count as progress.
    Scanner evidence remains intact in the stage result. A bounded diagnostic is added
    so the public status projection can explain the failure and offer one safe retry.
    """

    output = deepcopy(dict(result))
    status = str(output.get("status") or "complete").strip().casefold()
    if status not in ACTIVE_STATUSES:
        return output

    instant = _now(now)
    instant_text = _iso(instant)
    prior_results = record.get("stage_results")
    prior = (
        prior_results.get(stage_id)
        if isinstance(prior_results, Mapping)
        and isinstance(prior_results.get(stage_id), Mapping)
        else {}
    )
    prior_watchdog = (
        prior.get("watchdog")
        if isinstance(prior, Mapping) and isinstance(prior.get("watchdog"), Mapping)
        else {}
    )

    signal = _signal(output)
    prior_signal = str(prior_watchdog.get("progress_signal_sha256") or "")
    changed = not prior_signal or signal != prior_signal
    no_progress_attempts = 0 if changed else int(prior_watchdog.get("no_progress_attempts") or 0) + 1
    first_observed_at = str(prior_watchdog.get("first_observed_at") or instant_text)
    last_progress_at = instant_text if changed else str(prior_watchdog.get("last_progress_at") or first_observed_at)
    last_progress = _parse_iso(last_progress_at) or instant
    stalled_seconds = max(0, int((instant - last_progress).total_seconds()))
    max_attempts = _max_no_progress_attempts()
    timeout_seconds = _stall_timeout_seconds()
    stalled = no_progress_attempts >= max_attempts or stalled_seconds >= timeout_seconds

    watchdog = {
        "artifact_schema": VERSION,
        "stage_id": stage_id,
        "first_observed_at": first_observed_at,
        "last_progress_at": last_progress_at,
        "observed_at": instant_text,
        "progress_percent": _progress(output),
        "progress_signal_sha256": signal,
        "progress_changed": changed,
        "no_progress_attempts": no_progress_attempts,
        "stalled_seconds": stalled_seconds,
        "max_no_progress_attempts": max_attempts,
        "stall_timeout_seconds": timeout_seconds,
        "revision_only_changes_count_as_progress": False,
        "scanner_evidence_preserved": True,
        "stalled": stalled,
    }
    output["watchdog"] = watchdog
    if not stalled:
        return output

    output.update(
        {
            "status": "blocked",
            "reason": STALL_REASON,
            "error_code": STALL_REASON,
            "error_message": (
                f"Stage {stage_id} produced no meaningful progress for "
                f"{no_progress_attempts} continuation attempt(s) and "
                f"{stalled_seconds} second(s)."
            ),
            "technical_reason": (
                f"{STALL_REASON}:stage={stage_id}:attempts={no_progress_attempts}:"
                f"stalled_seconds={stalled_seconds}"
            ),
            "retryable": True,
            "cancelable": True,
            "artifacts_available": bool(
                output.get("artifacts_available")
                or output.get("artifact_hash")
                or output.get("evidence")
                or output.get("scanner")
            ),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return output


def _stall_result(record: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    stage_id = str(record.get("current_stage") or "")
    results = record.get("stage_results")
    result = (
        results.get(stage_id)
        if stage_id and isinstance(results, Mapping) and isinstance(results.get(stage_id), Mapping)
        else {}
    )
    return stage_id, result


def is_recoverable_stage_stall(record: Mapping[str, Any]) -> bool:
    stage_id, result = _stall_result(record)
    if not stage_id:
        return False
    recoveries = [
        item
        for item in record.get("recovery_history") or []
        if isinstance(item, Mapping)
        and item.get("recovery_type") == STALL_REASON
        and item.get("stage_id") == stage_id
    ]
    return bool(
        record.get("terminal") is True
        and str(record.get("status") or "").casefold() == "blocked"
        and str(result.get("reason") or result.get("error_code") or "") == STALL_REASON
        and len(recoveries) < MAX_RECOVERY_ATTEMPTS
    )


def rewind_stalled_stage_for_retry(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Allow one explicit continuation retry without changing prior completed evidence."""

    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if not is_recoverable_stage_stall(record):
        return record

    stage_id, result = _stall_result(record)
    updated = deepcopy(record)
    history = [
        deepcopy(dict(item))
        for item in updated.get("recovery_history") or []
        if isinstance(item, Mapping)
    ]
    instant = _now(now)
    history.append(
        {
            "artifact_schema": VERSION,
            "recovery_type": STALL_REASON,
            "stage_id": stage_id,
            "source_revision": int(record.get("revision") or 0),
            "source_watchdog": deepcopy(dict(result.get("watchdog") or {})),
            "source_error_code": str(result.get("error_code") or STALL_REASON),
            "completed_stage_evidence_preserved": True,
            "stalled_stage_evidence_preserved_in_history": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "recovered_at": _iso(instant),
        }
    )
    updated["recovery_history"] = history
    updated["stage_results"].pop(stage_id, None)
    completed = list(updated.get("completed_stages") or [])
    updated["current_stage"] = completed[-1] if completed else None
    updated["status"] = "running"
    updated["terminal"] = False
    updated["progress_percent"] = round(
        (len(completed) / len(COMPREHENSIVE_STAGES)) * 100,
        2,
    )
    updated["updated_at"] = _iso(instant)
    updated["revision"] = int(updated.get("revision") or 0) + 1
    updated["human_review_required"] = True
    updated["human_review_completed"] = False
    updated["client_delivery_allowed"] = False
    updated["integrity_sha256"] = _record_hash(updated)

    final_validation = validate_comprehensive_run_record(updated)
    if final_validation["status"] != "valid":
        raise ValueError(
            "invalid_recovered_run_record:" + ",".join(final_validation["violations"])
        )
    return updated


__all__ = [
    "ACTIVE_STATUSES",
    "STALL_REASON",
    "VERSION",
    "apply_stage_watchdog",
    "is_recoverable_stage_stall",
    "rewind_stalled_stage_for_retry",
]
