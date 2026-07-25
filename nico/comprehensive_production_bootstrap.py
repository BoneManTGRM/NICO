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
from nico.durable_runtime_storage import _path as _durable_runtime_path
from nico.durable_runtime_storage import _resolved_postgres_url

VERSION = "nico.comprehensive_production_bootstrap.v3"


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
    comprehensive_path = str(os.getenv("NICO_COMPREHENSIVE_SQLITE_PATH") or "").strip()
    if comprehensive_path:
        return Path(comprehensive_path).expanduser()
    return _durable_runtime_path().expanduser()


def _durable_volume_path() -> Path | None:
    configured = str(
        os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
        or os.getenv("NICO_DURABLE_VOLUME_PATH")
        or ""
    ).strip()
    return Path(configured).expanduser() if configured else None


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _sqlite_survives_container_replacement(path: Path) -> bool:
    volume = _durable_volume_path()
    if volume is not None and _path_within(path, volume):
        return True
    # Explicit acknowledgement is retained for non-Railway platforms whose mounted
    # volume cannot be discovered automatically. It must be set by the deployer.
    return _env_true("NICO_SQLITE_PERSISTENCE_CONFIRMED")


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
        "storage_source": "unavailable",
        "durability_verified": False,
        "survives_container_replacement_verified": False,
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
    """Install the native Comprehensive production runtime with durable run identity.

    Postgres is preferred and is resolved from the same bounded private aliases used by
    the rest of NICO's production storage. SQLite is accepted only when explicitly
    enabled. When durable assessment storage is required, SQLite must live under a
    detected mounted volume or carry an explicit deployment acknowledgement. A writable
    container filesystem is not treated as deployment-surviving because replacement
    would erase a partially completed run and produce ``comprehensive_run_not_found``.

    If no deployment-surviving adapter is available, routes remain mounted but fail
    closed with HTTP 503. Missing executors are never treated as passing evidence.
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

    explicit_url = str(database_url or "").strip()
    if explicit_url:
        resolved_url = explicit_url
        database_url_source = "explicit_database_url"
    else:
        resolved_url, database_url_source = _resolved_postgres_url()

    resolved_factory = connection_factory
    resolved_dialect = dialect
    storage_source = "explicit_connection_factory" if connection_factory is not None else "postgres"
    survives_container_replacement = False

    if resolved_factory is None and not resolved_url:
        if not _env_true("NICO_ENABLE_SQLITE_DURABLE_STORAGE"):
            register_comprehensive_api_routes(app)
            app.state.comprehensive_runtime = _blocked_state(
                reason="comprehensive_durable_storage_required",
                supplied=len(executors),
            )
            return None
        path = _sqlite_path()
        survives_container_replacement = _sqlite_survives_container_replacement(path)
        if _env_true("NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE") and not survives_container_replacement:
            register_comprehensive_api_routes(app)
            app.state.comprehensive_runtime = _blocked_state(
                reason="comprehensive_sqlite_persistent_volume_required",
                supplied=len(executors),
            )
            return None
        try:
            resolved_factory = _sqlite_connection_factory(path)
            resolved_dialect = "sqlite"
            storage_source = "mounted_durable_sqlite" if survives_container_replacement else "explicit_sqlite_test_or_local"
        except Exception:
            register_comprehensive_api_routes(app)
            app.state.comprehensive_runtime = _blocked_state(
                reason="comprehensive_sqlite_storage_unavailable",
                supplied=len(executors),
            )
            return None
    elif resolved_factory is None:
        storage_source = f"postgres:{database_url_source or 'configured'}"
        survives_container_replacement = True
    else:
        survives_container_replacement = str(resolved_dialect or "").strip().lower() == "postgres"

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
    adapter = str(state.get("persistence_adapter") or "unavailable")
    state.update(
        {
            "bootstrap_schema": VERSION,
            "status": "ready",
            "configured": True,
            "storage_source": storage_source,
            "database_url_source": database_url_source or "",
            # SQLite on a stable path survives process restart, but only Postgres or a
            # proven mounted volume survives container replacement.
            "durability_verified": adapter in {"postgres", "sqlite"},
            "survives_container_replacement_verified": bool(
                adapter == "postgres" or (adapter == "sqlite" and survives_container_replacement)
            ),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    app.state.comprehensive_runtime = state
    return controller


__all__ = ["VERSION", "install_comprehensive_production_bootstrap"]