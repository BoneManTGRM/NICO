from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_run_store import ConnectionFactory
from nico.comprehensive_runtime import configure_comprehensive_runtime
from nico.comprehensive_stage_adapter import CapabilityExecutor

VERSION = "nico.comprehensive_production_bootstrap.v1"


def _required_capabilities() -> tuple[str, ...]:
    return tuple(str(item["capability"]) for item in execution_plan())


def _resolve_executors(
    app: FastAPI,
    explicit: Mapping[str, CapabilityExecutor] | None,
) -> dict[str, CapabilityExecutor]:
    source: Any = explicit
    if source is None:
        source = getattr(app.state, "comprehensive_capability_executors", None)
    if not isinstance(source, Mapping):
        return {}
    return {str(key): value for key, value in source.items() if callable(value)}


def _blocked_state(*, reason: str, supplied: int) -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "configured": False,
        "status": "blocked",
        "reason": reason,
        "required_capability_count": len(_required_capabilities()),
        "supplied_capability_count": supplied,
        "persistence_adapter": "unavailable",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_comprehensive_production_bootstrap(
    app: FastAPI,
    *,
    capability_executors: Mapping[str, CapabilityExecutor] | None = None,
    database_url: str | None = None,
    connection_factory: ConnectionFactory | None = None,
    dialect: str | None = None,
) -> ComprehensiveApiController | None:
    """Install or safely defer the native Comprehensive production runtime.

    The bootstrap may run before deployment secrets or capability providers are
    available. In that state it still mounts the complete native route group, but
    every request fails closed with 503. A later call can atomically attach the
    durable controller without replacing the routes.
    """

    existing = getattr(app.state, "comprehensive_api_controller", None)
    runtime = getattr(app.state, "comprehensive_runtime", None)
    if isinstance(existing, ComprehensiveApiController) and isinstance(runtime, dict) and runtime.get("configured") is True:
        return existing

    executors = _resolve_executors(app, capability_executors)
    required = _required_capabilities()
    missing = [name for name in required if not callable(executors.get(name))]
    if missing:
        register_comprehensive_api_routes(app)
        app.state.comprehensive_runtime = _blocked_state(
            reason="comprehensive_capabilities_missing:" + ",".join(missing),
            supplied=len(executors),
        )
        return None

    resolved_url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
    if connection_factory is None and not resolved_url:
        register_comprehensive_api_routes(app)
        app.state.comprehensive_runtime = _blocked_state(
            reason="comprehensive_database_url_required",
            supplied=len(executors),
        )
        return None

    try:
        controller = configure_comprehensive_runtime(
            app,
            capability_executors=executors,
            database_url=resolved_url or None,
            connection_factory=connection_factory,
            dialect=dialect,
        )
    except RuntimeError as exc:
        register_comprehensive_api_routes(app)
        app.state.comprehensive_runtime = _blocked_state(reason=str(exc), supplied=len(executors))
        return None

    app.state.comprehensive_capability_executors = executors
    state = dict(getattr(app.state, "comprehensive_runtime", {}) or {})
    state.update(
        {
            "bootstrap_schema": VERSION,
            "status": "ready",
            "configured": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    app.state.comprehensive_runtime = state
    return controller


__all__ = ["VERSION", "install_comprehensive_production_bootstrap"]
