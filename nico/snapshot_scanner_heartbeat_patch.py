from __future__ import annotations

import os
import threading
import time
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import scanner_tool_runners, scanner_worker, snapshot_scanner_worker
from nico.storage import STORE

SNAPSHOT_SCANNER_HEARTBEAT_VERSION = "nico.snapshot_scanner_heartbeat.v2"
_WORKER_MARKER = "_nico_snapshot_scanner_heartbeat_worker_v2"
_TOOL_MARKER = "_nico_snapshot_scanner_heartbeat_tool_v2"
_CONTEXT = threading.local()


def _heartbeat_interval_seconds() -> int:
    try:
        configured = int(os.getenv("NICO_SCANNER_HEARTBEAT_SECONDS", "15"))
    except (TypeError, ValueError):
        configured = 15
    return max(5, min(configured, 60))


def _write_heartbeat(scan_id: str, tool_name: str, started_monotonic: float) -> None:
    """Persist liveness while a scanner subprocess is executing.

    Snapshot scanner workers import ``run_scanner_tool`` into their own module
    namespace. The installer below therefore binds this wrapper both to the
    source module and to that already-imported worker symbol. Without that
    second binding, production scanners could run normally while never writing
    a heartbeat, leaving live status unable to distinguish a long tool from a
    dead worker.
    """

    try:
        durable = STORE.get("scanner_runs", scan_id)
        current = deepcopy(durable if isinstance(durable, dict) else scanner_worker.SCAN_JOBS.get(scan_id) or {})
        if str(current.get("status") or "") not in {"queued", "running"}:
            return
        now_text = scanner_worker.now_iso()
        sequence = int(current.get("heartbeat_sequence") or 0) + 1
        current.update(
            {
                "scan_id": scan_id,
                "status": "running",
                "current_stage": "scanner_suite",
                "active_tool": tool_name,
                "heartbeat_at": now_text,
                "updated_at": now_text,
                "heartbeat_sequence": sequence,
                "heartbeat_process_id": os.getpid(),
                "heartbeat_thread": threading.current_thread().name[:120],
                "tool_elapsed_seconds": round(max(0.0, time.monotonic() - started_monotonic), 1),
            }
        )
        scanner_worker.SCAN_JOBS[scan_id] = deepcopy(current)
        STORE.put("scanner_runs", scan_id, current)
    except Exception as exc:
        # Heartbeat persistence must never terminate the authorized scanner.
        # Retain bounded local diagnostics for the worker failure boundary and
        # Operations diagnostics without exposing exception text or secrets.
        local = deepcopy(scanner_worker.SCAN_JOBS.get(scan_id) or {})
        local["heartbeat_persistence_status"] = "failed"
        local["heartbeat_failure_type"] = type(exc).__name__[:80]
        scanner_worker.SCAN_JOBS[scan_id] = local


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

    source_tool: Callable[..., Any] = scanner_tool_runners.run_scanner_tool
    existing_bound = getattr(snapshot_scanner_worker, "run_scanner_tool", source_tool)
    if getattr(source_tool, _TOOL_MARKER, False):
        tool_with_heartbeat = source_tool
    elif getattr(existing_bound, _TOOL_MARKER, False):
        tool_with_heartbeat = existing_bound
    else:
        current_tool = source_tool

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

            heartbeat = threading.Thread(
                target=pulse,
                daemon=True,
                name=f"nico-heartbeat-{scan_id[:24]}",
            )
            heartbeat.start()
            try:
                return current_tool(spec, workspace, *args, **kwargs)
            finally:
                stop.set()
                heartbeat.join(timeout=2)
                _write_heartbeat(scan_id, tool_name, started)

        setattr(tool_with_heartbeat, _TOOL_MARKER, True)
        setattr(tool_with_heartbeat, "_nico_previous", current_tool)

    # Critical production binding: snapshot_scanner_worker imported the function
    # directly, so changing only scanner_tool_runners.run_scanner_tool does not
    # affect the name used inside _run_snapshot_scan.
    scanner_tool_runners.run_scanner_tool = tool_with_heartbeat
    snapshot_scanner_worker.run_scanner_tool = tool_with_heartbeat

    return {
        "status": "installed",
        "version": SNAPSHOT_SCANNER_HEARTBEAT_VERSION,
        "heartbeat_interval_seconds": _heartbeat_interval_seconds(),
        "durable_heartbeat": True,
        "source_runner_binding_installed": scanner_tool_runners.run_scanner_tool is tool_with_heartbeat,
        "snapshot_worker_binding_installed": snapshot_scanner_worker.run_scanner_tool is tool_with_heartbeat,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "SNAPSHOT_SCANNER_HEARTBEAT_VERSION",
    "install_snapshot_scanner_heartbeat",
]
