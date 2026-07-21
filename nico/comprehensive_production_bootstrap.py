from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_run_store import ConnectionFactory
from nico.comprehensive_runtime import configure_comprehensive_runtime
from nico.comprehensive_stage_adapter import CapabilityExecutor

VERSION = "nico.comprehensive_production_bootstrap.v2"


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


def _env_true(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _sqlite_path() -> Path:
    configured = str(
        os.getenv("NICO_COMPREHENSIVE_SQLITE_PATH")
        or os.getenv("NICO_SQLITE_PATH")
        or "/data/nico-runtime.sqlite3"
    ).strip()
    if not configured:
        raise RuntimeError("comprehensive_sqlite_path_required")
    return Path(configured).expanduser()


def _sqlite_connection_factory(path: Path) -> ConnectionFactory:
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    def connect():
        connection = sqlite3.connect(
            str(target),
            timeout=30.0,
            check_same_thread=False,
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    # Prove the configured location is writable before the routes claim readiness.
    probe = connect()
    probe.execute("CREATE TABLE IF NOT EXISTS nico_runtime_storage_probe (id INTEGER PRIMARY KEY)")
    probe.commit()
    probe.close()
    return connect


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

    Postgres remains the preferred production adapter. When ``DATABASE_URL`` is
    absent, deployments may opt into the repository's durable SQLite contract by
    setting ``NICO_ENABLE_SQLITE_DURABLE_STORAGE=true`` and mounting the configured
    ``NICO_SQLITE_PATH`` on persistent storage. The Docker image already uses this
    explicit contract with one web worker and ``/data`` as the durable location.

    If neither durable adapter is available, all native routes remain mounted but
    fail closed with HTTP 503. Missing executors are never treated as passing
    evidence, and client delivery remains blocked for every adapter.
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
    resolved_factory = connection_factory
    resolved_dialect = dialect
    storage_source = "explicit_connection_factory" if connection_factory is not None else "postgres"

    if resolved_factory is None and not resolved_url:
        if not _env_true("NICO_ENABLE_SQLITE_DURABLE_STORAGE"):
            register_comprehensive_api_routes(app)
            app.state.comprehensive_runtime = _blocked_state(
                reason="comprehensive_durable_storage_required",
                supplied=len(executors),
            )
            return None
        try:
            resolved_factory = _sqlite_connection_factory(_sqlite_path())
            resolved_dialect = "sqlite"
            storage_source = "configured_durable_sqlite"
        except Exception:
            register_comprehensive_api_routes(app)
            app.state.comprehensive_runtime = _blocked_state(
                reason="comprehensive_sqlite_storage_unavailable",
                supplied=len(executors),
            )
            return None

    try:
        controller = configure_comprehensive_runtime(
            app,
            capability_executors=executors,
            database_url=resolved_url or None,
            connection_factory=resolved_factory,
            dialect=resolved_dialect,
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
            "storage_source": storage_source,
            "durability_verified": state.get("persistence_adapter") in {"postgres", "sqlite"},
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    app.state.comprehensive_runtime = state
    return controller


__all__ = ["VERSION", "install_comprehensive_production_bootstrap"]
