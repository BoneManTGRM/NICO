from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

import nico.express_async_api as express
from nico.api.production import app as production_app
from nico.assessment_block_messages import install_assessment_block_messages
from nico.durable_runtime_storage import install_durable_runtime_storage
from nico.express_backend_diagnostics import EXPRESS_BACKEND_DIAGNOSTICS_VERSION
from nico.express_runtime_heartbeat import install_express_runtime_heartbeat
from nico.lifecycle_status_hardening import install_lifecycle_status_hardening
from nico.mid_live_status_api import MID_LIVE_STATUS_ROUTE, register_mid_live_status_routes
from nico.mid_runtime_diagnostics import register_mid_runtime_diagnostics
from nico.postgres_timeout_patch import install_postgres_timeout_patch
from nico.scanner_redaction_safety import (
    SCANNER_REDACTION_SAFETY_VERSION,
    install_scanner_redaction_safety,
    scanner_redaction_safety_status,
)
from nico.snapshot_scanner_heartbeat_patch import install_snapshot_scanner_heartbeat

EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE = "/diagnostics/express-runtime"
EXPRESS_RUNTIME_REQUIRED_ROUTES = {
    ("POST", "/assessment/express-run"),
    ("POST", "/assessment/express-run/{run_id}/status"),
}


def _durable_required() -> bool:
    return (
        bool(os.getenv("DATABASE_URL", "").strip())
        or os.getenv("NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE", "false").strip().lower() == "true"
        or os.getenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "false").strip().lower() == "true"
    )


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def express_runtime_status(target: FastAPI) -> dict[str, Any]:
    worker = express._execute
    route_counts = {
        f"{method} {path}": _route_count(target, method, path)
        for method, path in sorted(EXPRESS_RUNTIME_REQUIRED_ROUTES)
    }
    diagnostics_installed = bool(getattr(worker, "_nico_express_backend_diagnostics_v1", False))
    heartbeat_installed = bool(getattr(worker, "_nico_express_runtime_heartbeat_v1", False))
    redaction = scanner_redaction_safety_status()
    storage = DURABLE_RUNTIME_STORAGE
    durable_required = _durable_required()
    durable_ready = bool(storage.get("persistence_available"))
    ready = (
        diagnostics_installed
        and heartbeat_installed
        and redaction["cycle_safe_redaction_installed"]
        and (durable_ready or not durable_required)
        and all(count == 1 for count in route_counts.values())
    )
    return {
        "status": "ok" if ready else "blocked",
        "version": EXPRESS_BACKEND_DIAGNOSTICS_VERSION,
        "bounded_backend_diagnostics_installed": diagnostics_installed,
        "durable_lifecycle_heartbeat_installed": heartbeat_installed,
        "worker_name": str(getattr(worker, "__name__", "unknown"))[:120],
        "route_counts": route_counts,
        "scanner_redaction_safety_version": SCANNER_REDACTION_SAFETY_VERSION,
        "cycle_safe_scanner_redaction_installed": redaction["cycle_safe_redaction_installed"],
        "scanner_redaction_maximum_depth": redaction["maximum_depth"],
        "storage_adapter": storage.get("adapter") or "unknown",
        "durable_storage_required": durable_required,
        "durable_storage_ready": durable_ready,
        "memory_storage_accepted": not durable_required,
        "request_validation_422_possible": False,
        "single_start_only": True,
        "replacement_run_allowed": False,
        "automatic_retry_allowed": False,
        "human_review_required": True,
        "client_ready": False,
    }


def _register_runtime_diagnostics(target: FastAPI) -> None:
    if _route_count(target, "GET", EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE):
        return

    def runtime_diagnostics() -> dict[str, Any]:
        return express_runtime_status(target)

    target.add_api_route(
        EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE,
        runtime_diagnostics,
        methods=["GET"],
        tags=["diagnostics"],
    )
    target.openapi_schema = None


DURABLE_RUNTIME_STORAGE = install_durable_runtime_storage()
POSTGRES_TIMEOUTS = install_postgres_timeout_patch()
SCANNER_REDACTION_SAFETY = install_scanner_redaction_safety()
SNAPSHOT_SCANNER_HEARTBEAT = install_snapshot_scanner_heartbeat()
EXPRESS_PRODUCTION_BOOTSTRAP = install_assessment_block_messages()
EXPRESS_RUNTIME_HEARTBEAT = install_express_runtime_heartbeat()
app = production_app
MID_LIVE_STATUS = register_mid_live_status_routes(app)
LIFECYCLE_STATUS_HARDENING = install_lifecycle_status_hardening(app)
MID_RUNTIME = register_mid_runtime_diagnostics(app)
_register_runtime_diagnostics(app)
EXPRESS_PRODUCTION_RUNTIME = express_runtime_status(app)

if _durable_required() and not DURABLE_RUNTIME_STORAGE.get("persistence_available"):
    raise RuntimeError(f"Durable assessment lifecycle storage is unavailable: {DURABLE_RUNTIME_STORAGE}")
if not SCANNER_REDACTION_SAFETY["cycle_safe_redaction_installed"]:
    raise RuntimeError("Express production bootstrap did not install cycle-safe scanner redaction")
if not EXPRESS_PRODUCTION_RUNTIME["bounded_backend_diagnostics_installed"]:
    raise RuntimeError("Express production bootstrap did not install bounded backend diagnostics")
if not EXPRESS_PRODUCTION_RUNTIME["durable_lifecycle_heartbeat_installed"]:
    raise RuntimeError("Express production bootstrap did not install durable lifecycle heartbeats")
if any(count != 1 for count in EXPRESS_PRODUCTION_RUNTIME["route_counts"].values()):
    raise RuntimeError(
        f"Express production routes are missing or duplicated: {EXPRESS_PRODUCTION_RUNTIME['route_counts']}"
    )
if _route_count(app, MID_LIVE_STATUS_ROUTE[0], MID_LIVE_STATUS_ROUTE[1]) != 1:
    raise RuntimeError("Mid live-status route must be registered exactly once")
if not SNAPSHOT_SCANNER_HEARTBEAT.get("source_runner_binding_installed"):
    raise RuntimeError("Scanner heartbeat wrapper is not bound to the source tool runner")
if not SNAPSHOT_SCANNER_HEARTBEAT.get("snapshot_worker_binding_installed"):
    raise RuntimeError("Scanner heartbeat wrapper is not bound to the snapshot worker's scanner-tool module alias")
if LIFECYCLE_STATUS_HARDENING.get("express_request_validation_422_possible"):
    raise RuntimeError("Express status route can still emit framework validation HTTP 422")
if LIFECYCLE_STATUS_HARDENING.get("mid_generic_http_500_possible"):
    raise RuntimeError("Mid live-status route can still emit an unbounded generic HTTP 500")
if MID_RUNTIME.get("status") != "ok":
    raise RuntimeError(f"Mid production runtime diagnostics are blocked: {MID_RUNTIME}")
if EXPRESS_PRODUCTION_RUNTIME.get("status") != "ok":
    raise RuntimeError(f"Express production runtime diagnostics are blocked: {EXPRESS_PRODUCTION_RUNTIME}")

app.state.nico_durable_runtime_storage = DURABLE_RUNTIME_STORAGE
app.state.nico_postgres_timeouts = POSTGRES_TIMEOUTS
app.state.nico_scanner_redaction_safety = SCANNER_REDACTION_SAFETY
app.state.nico_snapshot_scanner_heartbeat = SNAPSHOT_SCANNER_HEARTBEAT
app.state.nico_express_production_bootstrap = EXPRESS_PRODUCTION_BOOTSTRAP
app.state.nico_express_runtime_heartbeat = EXPRESS_RUNTIME_HEARTBEAT
app.state.nico_lifecycle_status_hardening = LIFECYCLE_STATUS_HARDENING
app.state.nico_express_production_runtime = EXPRESS_PRODUCTION_RUNTIME
app.state.nico_mid_live_status = MID_LIVE_STATUS
app.state.nico_mid_runtime = MID_RUNTIME

__all__ = [
    "app",
    "DURABLE_RUNTIME_STORAGE",
    "POSTGRES_TIMEOUTS",
    "SCANNER_REDACTION_SAFETY",
    "SNAPSHOT_SCANNER_HEARTBEAT",
    "EXPRESS_PRODUCTION_BOOTSTRAP",
    "EXPRESS_RUNTIME_HEARTBEAT",
    "LIFECYCLE_STATUS_HARDENING",
    "EXPRESS_PRODUCTION_RUNTIME",
    "MID_LIVE_STATUS",
    "MID_RUNTIME",
    "EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE",
    "EXPRESS_RUNTIME_REQUIRED_ROUTES",
    "express_runtime_status",
]
