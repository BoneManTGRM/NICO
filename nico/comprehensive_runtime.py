from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore, ConnectionFactory
from nico.comprehensive_stage_adapter import CapabilityExecutor

VERSION = "nico.comprehensive_runtime.v1"


def _required_capabilities() -> tuple[str, ...]:
    return tuple(str(item["capability"]) for item in execution_plan())


def _postgres_connection_factory(database_url: str) -> ConnectionFactory:
    normalized = str(database_url or "").strip()
    if not normalized:
        raise RuntimeError("comprehensive_database_url_required")
    if not normalized.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("comprehensive_database_url_must_be_postgres")

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - dependency is present in production package
        raise RuntimeError("psycopg_required_for_comprehensive_runtime") from exc

    return lambda: psycopg.connect(normalized)


def configure_comprehensive_runtime(
    app: FastAPI,
    *,
    capability_executors: Mapping[str, CapabilityExecutor],
    database_url: str | None = None,
    connection_factory: ConnectionFactory | None = None,
    dialect: str | None = None,
) -> ComprehensiveApiController:
    """Bind native Comprehensive routes to one durable runtime.

    Production defaults to ``DATABASE_URL`` and requires Postgres. Tests and
    disconnected verification may inject an explicit DB-API connection factory.
    Every required capability must be provided before routes are exposed; missing
    executors are never treated as passing evidence.
    """

    required = _required_capabilities()
    supplied = {str(key): value for key, value in capability_executors.items()}
    missing = [name for name in required if not callable(supplied.get(name))]
    if missing:
        raise RuntimeError("comprehensive_capabilities_missing:" + ",".join(missing))

    if connection_factory is None:
        resolved_url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
        connection_factory = _postgres_connection_factory(resolved_url)
        resolved_dialect = "postgres"
        persistence_adapter = "postgres"
    else:
        resolved_dialect = str(dialect or "").strip().lower()
        if resolved_dialect not in {"sqlite", "postgres"}:
            raise RuntimeError("comprehensive_runtime_dialect_required")
        persistence_adapter = resolved_dialect

    store = ComprehensiveRunStore(connection_factory, dialect=resolved_dialect)
    store.ensure_schema()
    service = ComprehensiveRunService(store, {name: supplied[name] for name in required})
    controller = ComprehensiveApiController(service)
    register_comprehensive_api_routes(app, controller=controller)

    app.state.comprehensive_runtime = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "configured": True,
        "persistence_adapter": persistence_adapter,
        "required_capability_count": len(required),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return controller


__all__ = ["VERSION", "configure_comprehensive_runtime"]
