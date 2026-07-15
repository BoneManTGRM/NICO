from __future__ import annotations

from typing import Any

from fastapi import FastAPI

import nico.express_async_api as express
from nico.api.production import app as production_app
from nico.assessment_block_messages import install_assessment_block_messages
from nico.express_backend_diagnostics import EXPRESS_BACKEND_DIAGNOSTICS_VERSION

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
    return {
        "status": "ok" if installed and all(count == 1 for count in route_counts.values()) else "blocked",
        "version": EXPRESS_BACKEND_DIAGNOSTICS_VERSION,
        "bounded_backend_diagnostics_installed": installed,
        "worker_name": str(getattr(worker, "__name__", "unknown"))[:120],
        "route_counts": route_counts,
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


# The Railway process imports this module directly. Install the worker patch here,
# after the complete production app has loaded, so indirect package import ordering
# cannot leave the original opaque express_async_api._execute function active.
EXPRESS_PRODUCTION_BOOTSTRAP = install_assessment_block_messages()
app = production_app
_register_runtime_diagnostics(app)
EXPRESS_PRODUCTION_RUNTIME = express_runtime_status(app)

if not EXPRESS_PRODUCTION_RUNTIME["bounded_backend_diagnostics_installed"]:
    raise RuntimeError("Express production bootstrap did not install bounded backend diagnostics")
if any(count != 1 for count in EXPRESS_PRODUCTION_RUNTIME["route_counts"].values()):
    raise RuntimeError(
        f"Express production routes are missing or duplicated: {EXPRESS_PRODUCTION_RUNTIME['route_counts']}"
    )

app.state.nico_express_production_bootstrap = EXPRESS_PRODUCTION_BOOTSTRAP
app.state.nico_express_production_runtime = EXPRESS_PRODUCTION_RUNTIME

__all__ = [
    "app",
    "EXPRESS_PRODUCTION_BOOTSTRAP",
    "EXPRESS_PRODUCTION_RUNTIME",
    "EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE",
    "EXPRESS_RUNTIME_REQUIRED_ROUTES",
    "express_runtime_status",
]
