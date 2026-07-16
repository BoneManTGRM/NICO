from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from nico import scanner_tool_runners, snapshot_scanner_worker
from nico.mid_live_status_api import MID_LIVE_STATUS_PATH, MID_LIVE_STATUS_VERSION
from nico.report_quality_gate import REPORT_QUALITY_GATE_VERSION
from nico.snapshot_scanner_heartbeat_patch import SNAPSHOT_SCANNER_HEARTBEAT_VERSION
from nico.storage import STORE

MID_RUNTIME_DIAGNOSTICS_PATH = "/diagnostics/mid-runtime"
MID_RUNTIME_DIAGNOSTICS_VERSION = "nico.mid_runtime_diagnostics.v1"
_HEARTBEAT_MARKER = "_nico_snapshot_scanner_heartbeat_tool_v2"


def _route_count(app: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def mid_runtime_status(app: FastAPI) -> dict[str, Any]:
    source_binding = bool(getattr(scanner_tool_runners.run_scanner_tool, _HEARTBEAT_MARKER, False))
    worker_binding = bool(getattr(snapshot_scanner_worker.run_scanner_tool, _HEARTBEAT_MARKER, False))
    same_binding = scanner_tool_runners.run_scanner_tool is snapshot_scanner_worker.run_scanner_tool
    live_routes = _route_count(app, "GET", MID_LIVE_STATUS_PATH)
    storage = STORE.status()
    database_required = bool(os.getenv("DATABASE_URL", "").strip())
    durable_ready = bool(storage.get("persistence_available")) if database_required else True
    status = "ok" if source_binding and worker_binding and same_binding and live_routes == 1 and durable_ready else "blocked"
    return {
        "status": status,
        "version": MID_RUNTIME_DIAGNOSTICS_VERSION,
        "mid_live_status_version": MID_LIVE_STATUS_VERSION,
        "mid_live_status_route_count": live_routes,
        "scanner_heartbeat_version": SNAPSHOT_SCANNER_HEARTBEAT_VERSION,
        "source_runner_heartbeat_binding": source_binding,
        "snapshot_worker_heartbeat_binding": worker_binding,
        "heartbeat_bindings_identical": same_binding,
        "report_quality_gate_version": REPORT_QUALITY_GATE_VERSION,
        "storage_adapter": storage.get("adapter") or storage.get("mode") or "unknown",
        "durable_storage_required": database_required,
        "durable_storage_ready": durable_ready,
        "same_run_duplicate_prevention": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def register_mid_runtime_diagnostics(app: FastAPI) -> dict[str, Any]:
    if not _route_count(app, "GET", MID_RUNTIME_DIAGNOSTICS_PATH):
        def diagnostics() -> dict[str, Any]:
            return mid_runtime_status(app)

        app.add_api_route(
            MID_RUNTIME_DIAGNOSTICS_PATH,
            diagnostics,
            methods=["GET"],
            tags=["diagnostics", "mid"],
        )
        app.openapi_schema = None
    return mid_runtime_status(app)


__all__ = [
    "MID_RUNTIME_DIAGNOSTICS_PATH",
    "MID_RUNTIME_DIAGNOSTICS_VERSION",
    "mid_runtime_status",
    "register_mid_runtime_diagnostics",
]
