from __future__ import annotations

import os
from copy import deepcopy
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore, ConnectionFactory
from nico.comprehensive_stage_adapter import CapabilityExecutor
from nico.comprehensive_stage_background_v2 import ComprehensiveStagePublicationCoordinator

VERSION = "nico.comprehensive_runtime.v2"


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


class _DetachedProductionComprehensiveRunService(ComprehensiveRunService):
    """Production transport boundary for one exact Comprehensive stage.

    Provider work must never own the lifetime of ``POST .../continue``. The request
    commits a small canonical running marker and returns; one detached worker then
    executes the exact stage and publishes its result under optimistic concurrency.
    Final report generation keeps its dedicated atomic publication coordinator.
    """

    def __init__(
        self,
        store: ComprehensiveRunStore,
        capability_executors: Mapping[str, CapabilityExecutor],
    ) -> None:
        super().__init__(store, capability_executors)
        self._detached_stage_publication = ComprehensiveStagePublicationCoordinator(store)

    def _run_next_stage(self, record: dict[str, Any]) -> dict[str, Any]:
        completed = list(record.get("completed_stages") or [])
        if len(completed) >= len(COMPREHENSIVE_STAGES):
            return record

        stage_id = COMPREHENSIVE_STAGES[len(completed)]
        if stage_id == FINAL_REPORT_STAGE_ID:
            return super()._run_next_stage(record)

        executor = self._stage_executors.get(stage_id)
        if executor is None:
            return super()._run_next_stage(record)

        identity = record["identity"]
        retained_stage_results = (
            record.get("stage_results")
            if isinstance(record.get("stage_results"), dict)
            else {}
        )
        # Keep request-thread work bounded. The bound capability executor performs its
        # defensive deep copy inside the detached worker, after the response can return.
        prior_stage_results = {
            completed_stage: retained_stage_results[completed_stage]
            for completed_stage in completed
            if completed_stage in retained_stage_results
        }
        context = {
            "artifact_schema": VERSION,
            "service_id": "comprehensive",
            "stage_id": stage_id,
            "run_id": identity["run_id"],
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
            "evidence_ledger_id": identity["evidence_ledger_id"],
            "customer_id": identity["customer_id"],
            "project_id": identity["project_id"],
            "assessment_depth": identity["assessment_depth"],
            "report_language": identity["report_language"],
            "human_evidence": deepcopy(record.get("human_evidence") or {}),
            "prior_stage_results": prior_stage_results,
            "recovery_history": deepcopy(record.get("recovery_history") or []),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return self._detached_stage_publication.advance(
            record,
            stage_id=stage_id,
            executor=executor,
            context=context,
        )


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

    The production Postgres path executes stage providers behind a canonical detached
    stage marker. This keeps continuation transport bounded independently of provider
    runtime and makes an ambiguous browser/proxy timeout unnecessary for normal stage
    execution. Explicit test factories retain the synchronous contract for deterministic
    unit and compatibility coverage.
    """

    required = _required_capabilities()
    supplied = {str(key): value for key, value in capability_executors.items()}
    missing = [name for name in required if not callable(supplied.get(name))]
    if missing:
        raise RuntimeError("comprehensive_capabilities_missing:" + ",".join(missing))

    explicit_connection_factory = connection_factory is not None
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
    detached_stage_execution = (
        resolved_dialect == "postgres" and not explicit_connection_factory
    )
    service_class = (
        _DetachedProductionComprehensiveRunService
        if detached_stage_execution
        else ComprehensiveRunService
    )
    service = service_class(store, {name: supplied[name] for name in required})
    controller = ComprehensiveApiController(service)
    register_comprehensive_api_routes(app, controller=controller)

    app.state.comprehensive_runtime = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "configured": True,
        "persistence_adapter": persistence_adapter,
        "required_capability_count": len(required),
        "detached_stage_execution": detached_stage_execution,
        "continuation_transport_owns_provider_lifetime": False
        if detached_stage_execution
        else True,
        "exact_run_stage_lease": "canonical_stage_result"
        if detached_stage_execution
        else "not_enabled",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return controller


__all__ = ["VERSION", "configure_comprehensive_runtime"]
