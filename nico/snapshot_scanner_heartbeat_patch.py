from __future__ import annotations

import threading
import time
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import scanner_tool_runners, scanner_worker, snapshot_scanner_worker
from nico.storage import STORE

SNAPSHOT_SCANNER_HEARTBEAT_VERSION = "nico.snapshot_scanner_heartbeat.v1"
_WORKER_MARKER = "_nico_snapshot_scanner_heartbeat_worker_v1"
_TOOL_MARKER = "_nico_snapshot_scanner_heartbeat_tool_v1"
_CONTEXT = threading.local()


def _heartbeat_interval_seconds() -> int:
    return 15


def _write_heartbeat(scan_id: str, tool_name: str, started_monotonic: float) -> None:
    try:
        durable = STORE.get("scanner_runs", scan_id)
        current = deepcopy(durable if isinstance(durable, dict) else scanner_worker.SCAN_JOBS.get(scan_id) or {})
        if str(current.get("status") or "") not in {"queued", "running"}:
            return
        now_text = scanner_worker.now_iso()
        current.update(
            {
                "scan_id": scan_id,
                "status": "running",
                "current_stage": "scanner_suite",
                "active_tool": tool_name,
                "heartbeat_at": now_text,
                "updated_at": now_text,
                "tool_elapsed_seconds": round(max(0.0, time.monotonic() - started_monotonic), 1),
            }
        )
        scanner_worker.SCAN_JOBS[scan_id] = deepcopy(current)
        STORE.put("scanner_runs", scan_id, current)
    except Exception:
        return


def install_snapshot_scanner_heartbeat() -> dict[str, Any]:
    current_worker: Callable[..., Any] = snapshot_scanner_worker._run_snapshot_scan
    if not getattr(current_worker, _WORKER_MARKER, False):
        @wraps(current_worker)
        def worker_with_context(scan_id: str, payload: dict[str, Any]) -> Any:
            previous = getattr(_CONTEXT, "scan_id", None)
            _CONTEXT.scan_id = scan_id
            try:
                return current_worker(scan_id, payload)
            finally:
                if previous is None:
                    try:
                        delattr(_CONTEXT, "scan_id")
                    except AttributeError:
                        pass
                else:
                    _CONTEXT.scan_id = previous

        setattr(worker_with_context, _WORKER_MARKER, True)
        setattr(worker_with_context, "_nico_previous", current_worker)
        snapshot_scanner_worker._run_snapshot_scan = worker_with_context

    current_tool: Callable[..., Any] = scanner_tool_runners.run_scanner_tool
    if not getattr(current_tool, _TOOL_MARKER, False):
        @wraps(current_tool)
        def tool_with_heartbeat(spec: Any, workspace: Any, *args: Any, **kwargs: Any) -> Any:
            scan_id = str(getattr(_CONTEXT, "scan_id", "") or "")
            if not scan_id:
                return current_tool(spec, workspace, *args, **kwargs)

            tool_name = str(getattr(spec, "name", "unknown") or "unknown")
            started = time.monotonic()
            stop = threading.Event()

            def pulse() -> None:
                _write_heartbeat(scan_id, tool_name, started)
                while not stop.wait(_heartbeat_interval_seconds()):
                    _write_heartbeat(scan_id, tool_name, started)

            heartbeat = threading.Thread(target=pulse, daemon=True, name=f"nico-heartbeat-{scan_id[:24]}")
            heartbeat.start()
            try:
                return current_tool(spec, workspace, *args, **kwargs)
            finally:
                stop.set()
                heartbeat.join(timeout=2)
                _write_heartbeat(scan_id, tool_name, started)

        setattr(tool_with_heartbeat, _TOOL_MARKER, True)
        setattr(tool_with_heartbeat, "_nico_previous", current_tool)
        scanner_tool_runners.run_scanner_tool = tool_with_heartbeat

    return {
        "status": "installed",
        "version": SNAPSHOT_SCANNER_HEARTBEAT_VERSION,
        "heartbeat_interval_seconds": _heartbeat_interval_seconds(),
        "durable_heartbeat": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["SNAPSHOT_SCANNER_HEARTBEAT_VERSION", "install_snapshot_scanner_heartbeat"]
