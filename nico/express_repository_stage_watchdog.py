from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
from threading import local
from time import monotonic
from typing import Any, Callable

PATCH_VERSION = "nico.express_repository_stage_watchdog.v1"
_PATCH_MARKER = "_nico_express_repository_stage_watchdog_v1"
_HEARTBEAT_SECONDS = 15
_MAX_STAGE_SECONDS = 900
_CONTEXT = local()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="nico-express-evidence")


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
            "stage_timeout_seconds": _MAX_STAGE_SECONDS,
            "same_run_continuation": True,
            "backend_task_active": True,
        },
    )


def _run_with_watchdog(
    api: Any,
    function: Callable[[dict[str, Any]], dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    context = _context()
    if context is None:
        return function(payload)

    run_id, request_payload = context
    future: Future[dict[str, Any]] = _EXECUTOR.submit(function, payload)
    started = monotonic()
    heartbeat = 0
    while True:
        try:
            return future.result(timeout=_HEARTBEAT_SECONDS)
        except FutureTimeout:
            heartbeat += 1
            elapsed = int(monotonic() - started)
            _heartbeat(api, run_id, request_payload, heartbeat, elapsed)
            if elapsed >= _MAX_STAGE_SECONDS:
                future.cancel()
                raise TimeoutError(
                    f"Express repository evidence exceeded {_MAX_STAGE_SECONDS} seconds for exact run {run_id}."
                )


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
        "maximum_stage_seconds": _MAX_STAGE_SECONDS,
        "wrapped_functions": wrapped_names,
        "duplicate_start_allowed": False,
        "synthetic_progress_allowed": False,
    }


__all__ = [
    "PATCH_VERSION",
    "install_express_repository_stage_watchdog",
]
