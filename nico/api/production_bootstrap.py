from __future__ import annotations

from typing import Any

from fastapi import FastAPI

import nico.express_async_api as express
from nico.api.production import app as production_app
from nico.assessment_block_messages import install_assessment_block_messages
from nico.express_backend_diagnostics import EXPRESS_BACKEND_DIAGNOSTICS_VERSION
from nico.mid_live_status_api import MID_LIVE_STATUS_ROUTE, register_mid_live_status_routes
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
    installed = bool(getattr(worker, "_nico_express_backend_diagnostics_v1", False))
    redaction = scanner_redaction_safety_status()
    return {
        "status": "ok"
        if installed
        and redaction["cycle_safe_redaction_installed"]
        and all(count == 1 for count in route_counts.values())
        else "blocked",
        "version": EXPRESS_BACKEND_DIAGNOSTICS_VERSION,
        "bounded_backend_diagnostics_installed": installed,
        "worker_name": str(getattr(worker, "__name__", "unknown"))[:120],
        "route_counts": route_counts,
        "scanner_redaction_safety_version": SCANNER_REDACTION_SAFETY_VERSION,
        "cycle_safe_scanner_redaction_installed": redaction["cycle_safe_redaction_installed"],
        "scanner_redaction_maximum_depth": redaction["maximum_depth"],
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


# Railway imports this module directly. Install late-bound production repairs only
# after the complete app has loaded so import order cannot leave an old route or
# scanner function active.
POSTGRES_TIMEOUTS = install_postgres_timeout_patch()
SCANNER_REDACTION_SAFETY = install_scanner_redaction_safety()
SNAPSHOT_SCANNER_HEARTBEAT = install_snapshot_scanner_heartbeat()
EXPRESS_PRODUCTION_BOOTSTRAP = install_assessment_block_messages()
app = production_app
MID_LIVE_STATUS = register_mid_live_status_routes(app)
_register_runtime_diagnostics(app)
EXPRESS_PRODUCTION_RUNTIME = express_runtime_status(app)

if not SCANNER_REDACTION_SAFETY["cycle_safe_redaction_installed"]:
    raise RuntimeError("Express production bootstrap did not install cycle-safe scanner redaction")
if not EXPRESS_PRODUCTION_RUNTIME["bounded_backend_diagnostics_installed"]:
    raise RuntimeError("Express production bootstrap did not install bounded backend diagnostics")
if any(count != 1 for count in EXPRESS_PRODUCTION_RUNTIME["route_counts"].values()):
    raise RuntimeError(
        f"Express production routes are missing or duplicated: {EXPRESS_PRODUCTION_RUNTIME['route_counts']}"
    )
if _route_count(app, MID_LIVE_STATUS_ROUTE[0], MID_LIVE_STATUS_ROUTE[1]) != 1:
    raise RuntimeError("Mid live-status route must be registered exactly once")

app.state.nico_postgres_timeouts = POSTGRES_TIMEOUTS
app.state.nico_scanner_redaction_safety = SCANNER_REDACTION_SAFETY
app.state.nico_snapshot_scanner_heartbeat = SNAPSHOT_SCANNER_HEARTBEAT
app.state.nico_express_production_bootstrap = EXPRESS_PRODUCTION_BOOTSTRAP
app.state.nico_express_production_runtime = EXPRESS_PRODUCTION_RUNTIME
app.state.nico_mid_live_status = MID_LIVE_STATUS

__all__ = [
    "app",
    "POSTGRES_TIMEOUTS",
    "SCANNER_REDACTION_SAFETY",
    "SNAPSHOT_SCANNER_HEARTBEAT",
    "EXPRESS_PRODUCTION_BOOTSTRAP",
    "EXPRESS_PRODUCTION_RUNTIME",
    "MID_LIVE_STATUS",
    "EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE",
    "EXPRESS_RUNTIME_REQUIRED_ROUTES",
    "express_runtime_status",
]
