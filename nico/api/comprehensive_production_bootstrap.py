from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from nico.api.production_bootstrap import app as production_app
from nico.comprehensive_api_routes import COMPREHENSIVE_API_ROUTES
from nico.comprehensive_production_bootstrap import install_comprehensive_production_bootstrap
from nico.comprehensive_production_capabilities import build_production_capability_executors

VERSION = "nico.api.comprehensive_production_bootstrap.v2"


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def install_comprehensive_on_production_app(target: FastAPI) -> dict[str, Any]:
    """Mount the native Comprehensive boundary on the deployed application.

    The complete capability executor map is always bound. Individual production
    providers resolve dynamically from application state and fail closed at their
    exact stage when evidence is unavailable. Durable storage remains mandatory
    before the controller is exposed.
    """

    executors = build_production_capability_executors(target)
    controller = install_comprehensive_production_bootstrap(
        target,
        capability_executors=executors,
    )
    route_counts = {
        f"{method} {path}": _route_count(target, method, path)
        for method, path in sorted(COMPREHENSIVE_API_ROUTES)
    }
    runtime = dict(getattr(target.state, "comprehensive_runtime", {}) or {})
    provider_status = dict(
        getattr(target.state, "nico_comprehensive_capability_provider_status", {}) or {}
    )
    ready = (
        controller is not None
        and runtime.get("configured") is True
        and runtime.get("status") == "ready"
        and runtime.get("client_delivery_allowed") is False
        and runtime.get("human_review_required") is True
        and all(count == 1 for count in route_counts.values())
    )
    status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "status": "ready" if ready else "blocked",
        "configured": bool(runtime.get("configured")),
        "reason": str(runtime.get("reason") or ""),
        "persistence_adapter": str(runtime.get("persistence_adapter") or "unavailable"),
        "route_counts": route_counts,
        "capability_provider_status": provider_status,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    target.state.nico_comprehensive_production_runtime = status
    return status


app = production_app
COMPREHENSIVE_PRODUCTION_RUNTIME = install_comprehensive_on_production_app(app)

if any(count != 1 for count in COMPREHENSIVE_PRODUCTION_RUNTIME["route_counts"].values()):
    raise RuntimeError(
        "Comprehensive production routes are missing or duplicated: "
        f"{COMPREHENSIVE_PRODUCTION_RUNTIME['route_counts']}"
    )
if COMPREHENSIVE_PRODUCTION_RUNTIME["human_review_required"] is not True:
    raise RuntimeError("Comprehensive production runtime must require human review")
if COMPREHENSIVE_PRODUCTION_RUNTIME["client_delivery_allowed"] is not False:
    raise RuntimeError("Comprehensive production runtime must block client delivery")


__all__ = [
    "app",
    "COMPREHENSIVE_PRODUCTION_RUNTIME",
    "VERSION",
    "install_comprehensive_on_production_app",
]
