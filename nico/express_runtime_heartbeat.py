from __future__ import annotations

import os
import threading
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import express_async_api
from nico.storage import STORE, utc_now

EXPRESS_RUNTIME_HEARTBEAT_VERSION = "nico.express_runtime_heartbeat.v2"
_PATCH_MARKER = "_nico_express_runtime_heartbeat_v1"
_ACTIVE_STATUSES = {"queued", "running", "starting", "pending"}


def _interval_seconds() -> int:
    try:
        value = int(os.getenv("NICO_EXPRESS_HEARTBEAT_SECONDS", "15"))
    except (TypeError, ValueError):
        value = 15
    return max(5, min(value, 60))


def _legacy_pulse(run_id: str) -> None:
    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict):
        return
    response = deepcopy(record.get("response") if isinstance(record.get("response"), dict) else {})
    status = str(response.get("status") or record.get("status") or "").lower()
    if status not in _ACTIVE_STATUSES:
        return
    now = utc_now()
    sequence = int(response.get("heartbeat_sequence") or record.get("heartbeat_sequence") or 0) + 1
    response.update(
        {
            "heartbeat_at": now,
            "heartbeat_sequence": sequence,
            "heartbeat_process_id": os.getpid(),
            "updated_at": now,
            "human_review_required": True,
            "client_ready": False,
        }
    )
    record.update(
        {
            "status": status,
            "response": response,
            "payload": deepcopy(response),
            "heartbeat_at": now,
            "heartbeat_sequence": sequence,
            "updated_at": now,
        }
    )
    STORE.put("assessment_runs", run_id, record)


def _pulse(run_id: str) -> None:
    try:
        patcher = getattr(STORE, "patch_heartbeat", None)
        if callable(patcher):
            patcher(
                "assessment_runs",
                run_id,
                patch={
                    "heartbeat_at": utc_now(),
                    "heartbeat_process_id": os.getpid(),
                    "heartbeat_thread": threading.current_thread().name[:120],
                    "human_review_required": True,
                    "client_ready": False,
                },
                active_statuses=_ACTIVE_STATUSES,
                nested_key="response",
            )
            return
        _legacy_pulse(run_id)
    except Exception:
        # A heartbeat failure must not terminate the authorized assessment.
        return


def install_express_runtime_heartbeat() -> dict[str, Any]:
    current: Callable[[str, dict[str, Any]], None] = express_async_api._execute
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": EXPRESS_RUNTIME_HEARTBEAT_VERSION,
            "interval_seconds": _interval_seconds(),
        }

    @wraps(current)
    def execute_with_heartbeat(run_id: str, request_payload: dict[str, Any]) -> None:
        stop = threading.Event()

        def heartbeat_loop() -> None:
            _pulse(run_id)
            while not stop.wait(_interval_seconds()):
                _pulse(run_id)

        thread = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name=f"nico-express-heartbeat-{run_id[-16:]}",
        )
        thread.start()
        try:
            return current(run_id, request_payload)
        finally:
            stop.set()
            thread.join(timeout=2)
            _pulse(run_id)

    setattr(execute_with_heartbeat, _PATCH_MARKER, True)
    setattr(execute_with_heartbeat, "_nico_previous", current)
    express_async_api._execute = execute_with_heartbeat
    return {
        "status": "installed",
        "version": EXPRESS_RUNTIME_HEARTBEAT_VERSION,
        "interval_seconds": _interval_seconds(),
        "durable_heartbeat": True,
        "atomic_status_guard": callable(getattr(STORE, "patch_heartbeat", None)),
        "terminal_state_can_be_reopened": False,
        "cross_worker_status_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["EXPRESS_RUNTIME_HEARTBEAT_VERSION", "install_express_runtime_heartbeat"]
