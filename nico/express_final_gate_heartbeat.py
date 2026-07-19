from __future__ import annotations

import threading
from copy import deepcopy
from functools import wraps
from time import monotonic
from typing import Any, Callable

PATCH_VERSION = "nico.express_final_gate_heartbeat.v1"
_PATCH_MARKER = "_nico_express_final_gate_heartbeat_v1"
_CONTEXT = threading.local()
_HEARTBEAT_SECONDS = 20.0


def _context() -> tuple[str, dict[str, Any]] | None:
    run_id = str(getattr(_CONTEXT, "run_id", "") or "").strip()
    request_payload = getattr(_CONTEXT, "request_payload", None)
    if not run_id.startswith("express_run_") or not isinstance(request_payload, dict):
        return None
    return run_id, request_payload


def _publish_heartbeat(
    api: Any,
    run_id: str,
    request_payload: dict[str, Any],
    *,
    operation: str,
    sequence: int,
    elapsed_seconds: int,
) -> None:
    api._record_stage(
        run_id,
        request_payload,
        "truth_and_review_gates",
        "Report artifacts are complete. NICO is applying the same-run truth, evidence, and human-review gates.",
        progress_percent=96,
        evidence={
            "final_gate_heartbeat_version": PATCH_VERSION,
            "final_gate_operation": operation,
            "heartbeat_sequence": sequence,
            "stage_elapsed_seconds": elapsed_seconds,
            "same_run_continuation": True,
            "backend_task_active": True,
        },
    )


def _run_with_heartbeat(
    api: Any,
    function: Callable[[dict[str, Any]], dict[str, Any]],
    payload: dict[str, Any],
    *,
    operation: str,
    heartbeat_seconds: float = _HEARTBEAT_SECONDS,
) -> dict[str, Any]:
    context = _context()
    if context is None:
        return function(payload)

    run_id, request_payload = context
    stopped = threading.Event()
    started = monotonic()

    def heartbeat_loop() -> None:
        sequence = 0
        while not stopped.wait(max(0.01, float(heartbeat_seconds))):
            sequence += 1
            try:
                _publish_heartbeat(
                    api,
                    run_id,
                    request_payload,
                    operation=operation,
                    sequence=sequence,
                    elapsed_seconds=int(monotonic() - started),
                )
            except Exception:
                # Heartbeat publication must never replace the authoritative gate
                # result. The gate continues and its terminal write remains final.
                continue

    thread: threading.Thread | None = None
    try:
        thread = threading.Thread(
            target=heartbeat_loop,
            name=f"nico-express-final-gate-{operation}",
            daemon=True,
        )
        thread.start()
    except RuntimeError:
        thread = None

    try:
        return function(payload)
    finally:
        stopped.set()
        if thread is not None:
            thread.join(timeout=1.0)


def install_express_final_gate_heartbeat() -> dict[str, Any]:
    from nico import express_async_api as api
    from nico.api import main as api_main

    current_execute = api._execute
    if not getattr(current_execute, _PATCH_MARKER, False):
        @wraps(current_execute)
        def execute_with_final_gate_context(run_id: str, request_payload: dict[str, Any]) -> None:
            _CONTEXT.run_id = run_id
            _CONTEXT.request_payload = deepcopy(request_payload)
            try:
                current_execute(run_id, request_payload)
            finally:
                _CONTEXT.run_id = ""
                _CONTEXT.request_payload = None

        setattr(execute_with_final_gate_context, _PATCH_MARKER, True)
        setattr(execute_with_final_gate_context, "_nico_previous", current_execute)
        api._execute = execute_with_final_gate_context

    wrapped: list[str] = []
    for name, operation in (
        ("attach_evidence_artifact_bundle", "evidence_bundle"),
        ("attach_client_acceptance_gate", "acceptance_gate"),
    ):
        current = getattr(api_main, name, None)
        if not callable(current) or getattr(current, _PATCH_MARKER, False):
            continue

        @wraps(current)
        def watched(
            payload: dict[str, Any],
            _current: Callable[[dict[str, Any]], dict[str, Any]] = current,
            _operation: str = operation,
        ) -> dict[str, Any]:
            return _run_with_heartbeat(api, _current, payload, operation=_operation)

        setattr(watched, _PATCH_MARKER, True)
        setattr(watched, "_nico_previous", current)
        setattr(api_main, name, watched)
        wrapped.append(name)

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "heartbeat_seconds": _HEARTBEAT_SECONDS,
        "wrapped_functions": wrapped,
        "final_gate_liveness_persisted": True,
        "same_run_continuation": True,
        "terminal_result_authoritative": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "PATCH_VERSION",
    "_run_with_heartbeat",
    "install_express_final_gate_heartbeat",
]
