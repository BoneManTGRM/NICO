from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from nico.comprehensive_stage_watchdog_v1 import STALL_REASON
from nico.storage import STORE

VERSION = "nico.comprehensive_background_stage_execution.v1"
DEFAULT_INLINE_GRACE_SECONDS = 0.75
DEFAULT_MAX_RUNTIME_SECONDS = 900
DEFAULT_HEARTBEAT_SECONDS = 10
DEFAULT_ORPHAN_SECONDS = 60

BACKGROUND_STAGE_IDS = frozenset(
    {
        "dependency_security_static_analysis",
        "deep_scanner_triage",
        "risk_reduction_and_executive_briefing",
        "final_comprehensive_report_generation",
    }
)

StageExecutor = Callable[[dict[str, Any]], dict[str, Any]]
_TASKS: dict[str, dict[str, Any]] = {}
_TASK_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _bounded_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _inline_grace_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_BACKGROUND_INLINE_GRACE_SECONDS",
        DEFAULT_INLINE_GRACE_SECONDS,
        0.0,
        10.0,
    )


def _max_runtime_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_BACKGROUND_MAX_RUNTIME_SECONDS",
        DEFAULT_MAX_RUNTIME_SECONDS,
        30.0,
        3_600.0,
    )


def _heartbeat_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_BACKGROUND_HEARTBEAT_SECONDS",
        DEFAULT_HEARTBEAT_SECONDS,
        1.0,
        60.0,
    )


def _orphan_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_BACKGROUND_ORPHAN_SECONDS",
        DEFAULT_ORPHAN_SECONDS,
        15.0,
        600.0,
    )


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _previous_stage(context: Mapping[str, Any], stage_id: str) -> dict[str, Any]:
    stages = context.get("prior_stage_results")
    if not isinstance(stages, Mapping):
        return {}
    value = stages.get(stage_id)
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _poll_iteration(context: Mapping[str, Any], stage_id: str) -> int:
    previous = _previous_stage(context, stage_id)
    execution = previous.get("stage_execution")
    if not isinstance(execution, Mapping):
        return 0
    try:
        return max(0, int(execution.get("background_poll_iteration") or 0))
    except (TypeError, ValueError):
        return 0


def _recovery_attempt(context: Mapping[str, Any], stage_id: str) -> int:
    return sum(
        1
        for item in context.get("recovery_history") or []
        if isinstance(item, Mapping) and _text(item.get("stage_id")) == stage_id
    )


def _task_identity(
    context: Mapping[str, Any],
    stage_id: str,
) -> tuple[str, int, int]:
    iteration = _poll_iteration(context, stage_id)
    recovery_attempt = _recovery_attempt(context, stage_id)
    identity = {
        "run_id": _text(context.get("run_id")),
        "stage_id": stage_id,
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "poll_iteration": iteration,
        "recovery_attempt": recovery_attempt,
    }
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        if not identity[field]:
            raise ValueError(f"background_stage_{field}_required")
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"comprehensive_stage_{digest[:28]}", iteration, recovery_attempt


def _job_age_seconds(job: Mapping[str, Any]) -> float:
    try:
        return max(0.0, time.time() - float(job.get("heartbeat_epoch") or job.get("created_epoch") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _durable_job(task_id: str) -> dict[str, Any]:
    try:
        value = STORE.get("client_jobs", task_id)
    except Exception:
        return {}
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _put_job(task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    job = deepcopy(dict(payload))
    job.setdefault("job_id", task_id)
    job.setdefault("workflow", "comprehensive_background_stage")
    job.setdefault("human_review_required", True)
    job["client_delivery_allowed"] = False
    try:
        return STORE.put("client_jobs", task_id, job)
    except Exception:
        # The canonical assessment run remains the authority. A local task may still
        # finish and be consumed by the request process when durable task telemetry is
        # temporarily unavailable.
        return job


def _execution_metadata(
    *,
    task_id: str,
    iteration: int,
    recovery_attempt: int,
    elapsed_seconds: float,
    max_runtime_seconds: float,
    completed: bool,
) -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "mode": "durable_background_stage_poll",
        "task_id": task_id,
        "background_poll_iteration": iteration + (1 if completed else 0),
        "recovery_attempt": recovery_attempt,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "max_runtime_seconds": max_runtime_seconds,
        "completed_within_boundary": completed,
        "duplicate_execution_prevented": True,
        "canonical_run_written_only_by_request_thread": True,
    }


def _in_progress_result(
    context: Mapping[str, Any],
    *,
    stage_id: str,
    task_id: str,
    iteration: int,
    recovery_attempt: int,
    started_epoch: float,
    max_runtime_seconds: float,
) -> dict[str, Any]:
    previous = _previous_stage(context, stage_id)
    scanner = previous.get("scanner") if isinstance(previous.get("scanner"), Mapping) else {}
    progress = (
        previous.get("stage_progress_percent")
        or previous.get("progress_percent")
        or scanner.get("progress_percent")
    )
    result = {
        "status": "running",
        "reason": "background_stage_execution_in_progress",
        "summary": _text(previous.get("summary"))
        or "This assessment stage is continuing in the background without holding the browser request open.",
        "retryable": False,
        "cancelable": True,
        "artifacts_available": bool(previous.get("artifacts_available") or previous.get("evidence")),
        "run_id": _text(context.get("run_id")),
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": _execution_metadata(
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            elapsed_seconds=max(0.0, time.time() - started_epoch),
            max_runtime_seconds=max_runtime_seconds,
            completed=False,
        ),
    }
    if progress is not None:
        result["stage_progress_percent"] = progress
    for key in ("scan_id", "scanner", "evidence", "unavailable_data_notes"):
        if key in previous:
            result[key] = deepcopy(previous[key])
    return result


def _timeout_result(
    context: Mapping[str, Any],
    *,
    stage_id: str,
    task_id: str,
    iteration: int,
    recovery_attempt: int,
    elapsed_seconds: float,
    max_runtime_seconds: float,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": STALL_REASON,
        "error_code": "background_stage_execution_timeout",
        "error_message": (
            f"Stage {stage_id} exceeded the {int(max_runtime_seconds)}-second background execution boundary."
        ),
        "technical_reason": (
            f"background_stage_execution_timeout:stage={stage_id}:"
            f"task_id={task_id}:elapsed_seconds={round(elapsed_seconds, 3)}"
        ),
        "retryable": True,
        "cancelable": True,
        "artifacts_available": False,
        "run_id": _text(context.get("run_id")),
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": _execution_metadata(
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            elapsed_seconds=elapsed_seconds,
            max_runtime_seconds=max_runtime_seconds,
            completed=False,
        ),
        "watchdog": {
            "artifact_schema": VERSION,
            "stage_id": stage_id,
            "stalled": True,
            "stalled_seconds": int(elapsed_seconds),
            "progress_changed": False,
            "revision_only_changes_count_as_progress": False,
            "scanner_evidence_preserved": True,
            "background_task_result_ignored_after_timeout": True,
        },
    }


def _failed_result(
    context: Mapping[str, Any],
    *,
    stage_id: str,
    task_id: str,
    iteration: int,
    recovery_attempt: int,
    message: str,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": "background_stage_execution_failed",
        "error_code": "background_stage_execution_failed",
        "error_message": message,
        "technical_reason": f"background_stage_execution_failed:stage={stage_id}:task_id={task_id}",
        "retryable": True,
        "cancelable": True,
        "artifacts_available": False,
        "run_id": _text(context.get("run_id")),
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": _execution_metadata(
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            elapsed_seconds=0.0,
            max_runtime_seconds=_max_runtime_seconds(),
            completed=False,
        ),
    }


def _completed_result(
    value: Mapping[str, Any],
    *,
    task_id: str,
    iteration: int,
    recovery_attempt: int,
    elapsed_seconds: float,
    max_runtime_seconds: float,
) -> dict[str, Any]:
    output = deepcopy(dict(value))
    execution = output.get("stage_execution")
    execution_payload = deepcopy(dict(execution)) if isinstance(execution, Mapping) else {}
    execution_payload.update(
        _execution_metadata(
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            elapsed_seconds=elapsed_seconds,
            max_runtime_seconds=max_runtime_seconds,
            completed=True,
        )
    )
    output["stage_execution"] = execution_payload
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


def _start_task(
    executor: StageExecutor,
    context: Mapping[str, Any],
    *,
    stage_id: str,
    task_id: str,
    iteration: int,
    recovery_attempt: int,
    max_runtime_seconds: float,
    restart_count: int,
) -> dict[str, Any]:
    started_epoch = time.time()
    event = threading.Event()
    state: dict[str, Any] = {
        "task_id": task_id,
        "stage_id": stage_id,
        "started_epoch": started_epoch,
        "event": event,
        "result": None,
        "error": "",
        "expired": False,
    }
    with _TASK_LOCK:
        _TASKS[task_id] = state

    base_job = {
        "job_id": task_id,
        "workflow": "comprehensive_background_stage",
        "status": "running",
        "run_id": _text(context.get("run_id")),
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "customer_id": _text(context.get("customer_id")) or "default_customer",
        "project_id": _text(context.get("project_id")) or "default_project",
        "stage_id": stage_id,
        "poll_iteration": iteration,
        "recovery_attempt": recovery_attempt,
        "restart_count": restart_count,
        "created_epoch": started_epoch,
        "heartbeat_epoch": started_epoch,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "max_runtime_seconds": max_runtime_seconds,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    _put_job(task_id, base_job)

    def heartbeat() -> None:
        interval = _heartbeat_seconds()
        while not event.wait(interval):
            with _TASK_LOCK:
                if state.get("expired"):
                    return
            heartbeat_job = {
                **base_job,
                "status": "running",
                "heartbeat_epoch": time.time(),
                "updated_at": _now_iso(),
                "elapsed_seconds": round(time.time() - started_epoch, 3),
            }
            _put_job(task_id, heartbeat_job)

    def invoke() -> None:
        try:
            value = executor(deepcopy(dict(context)))
            if not isinstance(value, Mapping):
                raise TypeError(f"stage_executor_must_return_dict:{stage_id}")
            elapsed = time.time() - started_epoch
            with _TASK_LOCK:
                expired = bool(state.get("expired")) or elapsed >= max_runtime_seconds
            if expired:
                timeout = _timeout_result(
                    context,
                    stage_id=stage_id,
                    task_id=task_id,
                    iteration=iteration,
                    recovery_attempt=recovery_attempt,
                    elapsed_seconds=elapsed,
                    max_runtime_seconds=max_runtime_seconds,
                )
                with _TASK_LOCK:
                    state["result"] = timeout
                    state["expired"] = True
                _put_job(
                    task_id,
                    {
                        **base_job,
                        "status": "timed_out",
                        "updated_at": _now_iso(),
                        "heartbeat_epoch": time.time(),
                        "elapsed_seconds": round(elapsed, 3),
                        "result": timeout,
                        "late_provider_result_discarded": True,
                    },
                )
                return
            completed = _completed_result(
                value,
                task_id=task_id,
                iteration=iteration,
                recovery_attempt=recovery_attempt,
                elapsed_seconds=elapsed,
                max_runtime_seconds=max_runtime_seconds,
            )
            with _TASK_LOCK:
                state["result"] = completed
            _put_job(
                task_id,
                {
                    **base_job,
                    "status": "complete",
                    "updated_at": _now_iso(),
                    "heartbeat_epoch": time.time(),
                    "elapsed_seconds": round(elapsed, 3),
                    "result": completed,
                },
            )
        except BaseException as exc:  # defensive provider boundary
            message = f"{type(exc).__name__}: {_text(exc)[:700]}"
            with _TASK_LOCK:
                state["error"] = message
            _put_job(
                task_id,
                {
                    **base_job,
                    "status": "failed",
                    "updated_at": _now_iso(),
                    "heartbeat_epoch": time.time(),
                    "error_message": message,
                },
            )
        finally:
            event.set()

    threading.Thread(
        target=heartbeat,
        name=f"nico-stage-heartbeat-{stage_id}",
        daemon=True,
    ).start()
    threading.Thread(
        target=invoke,
        name=f"nico-stage-background-{stage_id}",
        daemon=True,
    ).start()
    return state


def _local_outcome(
    state: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    stage_id: str,
    task_id: str,
    iteration: int,
    recovery_attempt: int,
    max_runtime_seconds: float,
) -> dict[str, Any] | None:
    result = state.get("result")
    if isinstance(result, Mapping):
        return deepcopy(dict(result))
    error = _text(state.get("error"))
    if error:
        return _failed_result(
            context,
            stage_id=stage_id,
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            message=error,
        )
    started = float(state.get("started_epoch") or time.time())
    elapsed = max(0.0, time.time() - started)
    if elapsed >= max_runtime_seconds:
        with _TASK_LOCK:
            if isinstance(state, dict):
                state["expired"] = True
        timeout = _timeout_result(
            context,
            stage_id=stage_id,
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            elapsed_seconds=elapsed,
            max_runtime_seconds=max_runtime_seconds,
        )
        _put_job(
            task_id,
            {
                "job_id": task_id,
                "workflow": "comprehensive_background_stage",
                "status": "timed_out",
                "run_id": _text(context.get("run_id")),
                "customer_id": _text(context.get("customer_id")) or "default_customer",
                "project_id": _text(context.get("project_id")) or "default_project",
                "stage_id": stage_id,
                "result": timeout,
                "updated_at": _now_iso(),
                "heartbeat_epoch": time.time(),
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
        return timeout
    return None


def execute_background_stage(
    executor: StageExecutor,
    context: Mapping[str, Any],
    *,
    stage_id: str,
    inline_grace_seconds: float | None = None,
    max_runtime_seconds: float | None = None,
) -> dict[str, Any]:
    """Advance one long-running stage without holding the continuation request open.

    A provider invocation is identified by immutable run identity, stage, poll
    iteration, and recovery attempt. The same invocation is never launched twice in
    one process. Durable task state lets another process observe completion or wait on
    a live heartbeat. The provider result is only written into the canonical run by the
    normal request thread.
    """

    if stage_id not in BACKGROUND_STAGE_IDS:
        raise ValueError(f"background_stage_not_configured:{stage_id}")

    task_id, iteration, recovery_attempt = _task_identity(context, stage_id)
    grace = _inline_grace_seconds() if inline_grace_seconds is None else max(0.0, float(inline_grace_seconds))
    max_runtime = _max_runtime_seconds() if max_runtime_seconds is None else max(0.05, float(max_runtime_seconds))

    with _TASK_LOCK:
        local = _TASKS.get(task_id)
    if local:
        event = local.get("event")
        if isinstance(event, threading.Event):
            event.wait(grace)
        outcome = _local_outcome(
            local,
            context,
            stage_id=stage_id,
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            max_runtime_seconds=max_runtime,
        )
        if outcome is not None:
            return outcome
        return _in_progress_result(
            context,
            stage_id=stage_id,
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            started_epoch=float(local.get("started_epoch") or time.time()),
            max_runtime_seconds=max_runtime,
        )

    durable = _durable_job(task_id)
    durable_status = _text(durable.get("status")).casefold()
    if durable_status in {"complete", "timed_out"} and isinstance(durable.get("result"), Mapping):
        return deepcopy(dict(durable["result"]))
    if durable_status == "failed":
        return _failed_result(
            context,
            stage_id=stage_id,
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            message=_text(durable.get("error_message")) or "The background stage provider failed without retained detail.",
        )

    restart_count = int(durable.get("restart_count") or 0) if durable else 0
    if durable_status == "running" and _job_age_seconds(durable) < _orphan_seconds():
        started_epoch = float(durable.get("created_epoch") or time.time())
        elapsed = max(0.0, time.time() - started_epoch)
        if elapsed >= max_runtime:
            return _timeout_result(
                context,
                stage_id=stage_id,
                task_id=task_id,
                iteration=iteration,
                recovery_attempt=recovery_attempt,
                elapsed_seconds=elapsed,
                max_runtime_seconds=max_runtime,
            )
        return _in_progress_result(
            context,
            stage_id=stage_id,
            task_id=task_id,
            iteration=iteration,
            recovery_attempt=recovery_attempt,
            started_epoch=started_epoch,
            max_runtime_seconds=max_runtime,
        )
    if durable_status == "running":
        restart_count += 1

    state = _start_task(
        executor,
        context,
        stage_id=stage_id,
        task_id=task_id,
        iteration=iteration,
        recovery_attempt=recovery_attempt,
        max_runtime_seconds=max_runtime,
        restart_count=restart_count,
    )
    event = state.get("event")
    if isinstance(event, threading.Event):
        event.wait(grace)
    outcome = _local_outcome(
        state,
        context,
        stage_id=stage_id,
        task_id=task_id,
        iteration=iteration,
        recovery_attempt=recovery_attempt,
        max_runtime_seconds=max_runtime,
    )
    if outcome is not None:
        return outcome
    return _in_progress_result(
        context,
        stage_id=stage_id,
        task_id=task_id,
        iteration=iteration,
        recovery_attempt=recovery_attempt,
        started_epoch=float(state.get("started_epoch") or time.time()),
        max_runtime_seconds=max_runtime,
    )


def is_background_stage_in_progress(result: Mapping[str, Any]) -> bool:
    return bool(
        _text(result.get("status")).casefold() == "running"
        and _text(result.get("reason")) == "background_stage_execution_in_progress"
        and isinstance(result.get("stage_execution"), Mapping)
    )


def reset_background_stage_tasks_for_tests() -> None:
    with _TASK_LOCK:
        for state in _TASKS.values():
            if isinstance(state, dict):
                state["expired"] = True
                event = state.get("event")
                if isinstance(event, threading.Event):
                    event.set()
        _TASKS.clear()


__all__ = [
    "BACKGROUND_STAGE_IDS",
    "DEFAULT_MAX_RUNTIME_SECONDS",
    "VERSION",
    "execute_background_stage",
    "is_background_stage_in_progress",
    "reset_background_stage_tasks_for_tests",
]
