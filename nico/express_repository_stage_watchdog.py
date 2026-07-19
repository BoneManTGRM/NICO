from __future__ import annotations

from copy import deepcopy
from threading import Event, Thread, local
from time import monotonic
from typing import Any, Callable

PATCH_VERSION = "nico.express_repository_stage_watchdog.v2"
_PATCH_MARKER = "_nico_express_repository_stage_watchdog_v2"
_HEARTBEAT_SECONDS = 15
_EXPECTED_STAGE_SECONDS = 900
_CONTEXT = local()


def _context() -> tuple[str, dict[str, Any]] | None:
    run_id = getattr(_CONTEXT, "run_id", "")
    payload = getattr(_CONTEXT, "request_payload", None)
    if not run_id or not isinstance(payload, dict):
        return None
    return str(run_id), payload


def _heartbeat(api: Any, run_id: str, payload: dict[str, Any], count: int, elapsed: int) -> None:
    api._record_stage(
        run_id,
        payload,
        "repository_evidence",
        "Repository evidence collection is active. NICO is waiting on the same bounded backend task; no duplicate assessment has been started.",
        progress_percent=53,
        evidence={
            "watchdog_version": PATCH_VERSION,
            "heartbeat_count": count,
            "stage_elapsed_seconds": elapsed,
            "expected_stage_seconds": _EXPECTED_STAGE_SECONDS,
            "stage_overdue": elapsed >= _EXPECTED_STAGE_SECONDS,
            "same_run_continuation": True,
            "backend_task_active": True,
            "background_assessment_task": False,
        },
    )


def _heartbeat_loop(
    api: Any,
    run_id: str,
    request_payload: dict[str, Any],
    stop: Event,
    *,
    heartbeat_seconds: float = _HEARTBEAT_SECONDS,
) -> None:
    started = monotonic()
    count = 0
    while not stop.wait(heartbeat_seconds):
        count += 1
        try:
            _heartbeat(api, run_id, request_payload, count, int(monotonic() - started))
        except Exception:
            # Heartbeat publication is observability only. The authoritative
            # assessment must continue even if one progress write is unavailable.
            continue


def _run_with_watchdog(
    api: Any,
    function: Callable[[dict[str, Any]], dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    context = _context()
    if context is None:
        return function(payload)

    run_id, request_payload = context
    stop = Event()
    heartbeat_thread = Thread(
        target=_heartbeat_loop,
        args=(api, run_id, deepcopy(request_payload), stop),
        daemon=True,
        name=f"nico-express-evidence-heartbeat-{run_id[-8:]}",
    )
    heartbeat_thread.start()
    try:
        # Run the authoritative assessment in the exact worker thread. The old
        # implementation moved it into a shared executor and attempted to cancel
        # an already-running Future after 15 minutes. Python cannot cancel a
        # running thread, so the worker recorded failure and released capacity
        # while a zombie assessment continued mutating process state. Keeping the
        # task inline preserves one exact lifecycle and prevents queued/zombie work.
        return function(payload)
    finally:
        stop.set()
        heartbeat_thread.join(timeout=2)


def install_express_repository_stage_watchdog() -> dict[str, Any]:
    from nico import express_async_api as api
    from nico.api import main as api_main

    current_execute = api._execute
    if not getattr(current_execute, _PATCH_MARKER, False):
        def execute_with_context(run_id: str, request_payload: dict[str, Any]) -> None:
            _CONTEXT.run_id = run_id
            _CONTEXT.request_payload = deepcopy(request_payload)
            try:
                current_execute(run_id, request_payload)
            finally:
                _CONTEXT.run_id = ""
                _CONTEXT.request_payload = None

        setattr(execute_with_context, _PATCH_MARKER, True)
        setattr(execute_with_context, "_nico_previous", current_execute)
        api._execute = execute_with_context

    wrapped_names: list[str] = []
    for name in ("run_github_assessment", "run_github_assessment_with_scanner_artifacts"):
        current = getattr(api_main, name, None)
        if not callable(current) or getattr(current, _PATCH_MARKER, False):
            continue

        def watched(
            payload: dict[str, Any],
            _current: Callable[[dict[str, Any]], dict[str, Any]] = current,
        ) -> dict[str, Any]:
            return _run_with_watchdog(api, _current, payload)

        setattr(watched, _PATCH_MARKER, True)
        setattr(watched, "_nico_previous", current)
        setattr(api_main, name, watched)
        wrapped_names.append(name)

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "heartbeat_seconds": _HEARTBEAT_SECONDS,
        "expected_stage_seconds": _EXPECTED_STAGE_SECONDS,
        "wrapped_functions": wrapped_names,
        "authoritative_task_runs_inline": True,
        "running_future_cancellation_used": False,
        "zombie_assessment_possible": False,
        "duplicate_start_allowed": False,
        "synthetic_progress_allowed": False,
    }


__all__ = [
    "PATCH_VERSION",
    "_heartbeat_loop",
    "_run_with_watchdog",
    "install_express_repository_stage_watchdog",
]
