from __future__ import annotations

from fastapi import FastAPI

from nico.operations_readiness import REQUIRED_OPERATION_ROUTES, build_operations_readiness
from nico.operations_readiness_api import application_route_inventory, register_operations_readiness_routes


def _deployment() -> dict:
    return {
        "build_marker": "nico-test-build",
        "expected_build_commit": "a" * 40,
        "deployed_commit": "a" * 40,
        "matches_expected_build": True,
    }


def _storage(persistent: bool = True) -> dict:
    return {
        "status": "ok",
        "database_configured": persistent,
        "persistence_available": persistent,
        "storage": {"adapter": "postgres" if persistent else "memory"},
        "warnings": [] if persistent else ["Storage persistence is unavailable."],
    }


def _features(admin_configured: bool = True) -> dict:
    return {
        "status": "ok",
        "scanner_execution_enabled": True,
        "project_commands_allowed": False,
        "admin": {
            "admin_writes_configured": admin_configured,
            "admin_write_mode": "blocked" if admin_configured else "read_only",
        },
    }


def _truth() -> dict:
    return {"status": "ok", "guard_active": True, "version": "truth-v1"}


def _runtime() -> dict:
    return {"status": "ok", "source": "environment", "version": "1"}


def test_operations_readiness_is_ready_only_when_required_and_advisory_checks_pass() -> None:
    result = build_operations_readiness(
        sorted(REQUIRED_OPERATION_ROUTES),
        deployment=_deployment(),
        storage=_storage(),
        features=_features(),
        report_truth=_truth(),
        runtime=_runtime(),
    )

    assert result["artifact_schema"] == "nico.operations_readiness.v1"
    assert result["status"] == "ready"
    assert result["operational_ready"] is True
    assert result["required_checks"] == result["required_passed"]
    assert result["advisory_checks"] == result["advisory_passed"]
    assert result["blockers"] == []
    assert result["warnings"] == []
    assert result["client_delivery_allowed"] is False


def test_operations_readiness_blocks_on_nondurable_storage_and_missing_route() -> None:
    routes = sorted(REQUIRED_OPERATION_ROUTES - {"POST /assessment/full-run"})
    result = build_operations_readiness(
        routes,
        deployment=_deployment(),
        storage=_storage(persistent=False),
        features=_features(),
        report_truth=_truth(),
        runtime=_runtime(),
    )

    assert result["status"] == "blocked"
    assert result["operational_ready"] is False
    assert "durable_storage" in result["blockers"]
    assert "required_routes_registered" in result["blockers"]
    assert result["missing_routes"] == ["POST /assessment/full-run"]
    assert "before accepting trusted production work" in result["next_action"]


def test_operations_readiness_degrades_for_advisory_admin_configuration() -> None:
    result = build_operations_readiness(
        sorted(REQUIRED_OPERATION_ROUTES),
        deployment=_deployment(),
        storage=_storage(),
        features=_features(admin_configured=False),
        report_truth=_truth(),
        runtime=_runtime(),
    )

    assert result["status"] == "degraded"
    assert result["blockers"] == []
    assert result["warnings"] == ["operator_admin_configured"]
    assert result["operational_ready"] is False


def test_operations_route_registration_is_idempotent_and_inventory_is_machine_readable() -> None:
    app = FastAPI()
    app.get("/health")(lambda: {"status": "ok"})

    register_operations_readiness_routes(app)
    register_operations_readiness_routes(app)

    inventory = application_route_inventory(app)
    assert "GET /health" in inventory
    assert inventory.count("GET /operations/readiness") == 1
