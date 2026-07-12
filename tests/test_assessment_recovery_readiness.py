from __future__ import annotations

from nico.assessment_recovery_readiness_patch import build_operations_readiness
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES


def _deployment() -> dict:
    return {
        "build_marker": "test-build",
        "expected_build_commit": "a" * 40,
        "deployed_commit": "a" * 40,
        "matches_expected_build": True,
    }


def _storage() -> dict:
    return {
        "status": "ok",
        "database_configured": True,
        "persistence_available": True,
        "storage": {"adapter": "postgres"},
        "warnings": [],
    }


def _schema() -> dict:
    return {
        "status": "ready",
        "schema_ready": True,
        "migration_ready": True,
        "contract_version": "2026.07.13.1",
        "contract_sha256": "b" * 64,
        "blockers": [],
    }


def _features() -> dict:
    return {
        "scanner_execution_enabled": True,
        "project_commands_allowed": False,
        "admin": {
            "admin_writes_configured": True,
            "admin_write_mode": "blocked",
        },
    }


def _truth() -> dict:
    return {"status": "ok", "guard_active": True, "version": "truth-v1"}


def _runtime() -> dict:
    return {"status": "ok", "source": "environment", "version": "1"}


def _scanner_clear() -> dict:
    return {
        "status": "clear",
        "clear": True,
        "recovery_required": 0,
        "stale_active": 0,
        "active": 0,
        "blockers": [],
    }


def _build(assessment_recovery: dict) -> dict:
    return build_operations_readiness(
        sorted(REQUIRED_OPERATION_ROUTES),
        deployment=_deployment(),
        storage=_storage(),
        storage_schema=_schema(),
        scanner_recovery=_scanner_clear(),
        assessment_recovery=assessment_recovery,
        features=_features(),
        report_truth=_truth(),
        runtime=_runtime(),
    )


def test_clear_assessment_recovery_queue_passes_advisory_readiness() -> None:
    result = _build(
        {
            "status": "clear",
            "clear": True,
            "recovery_required": 0,
            "stale_active": 0,
            "active": 1,
            "blockers": [],
        }
    )
    check = next(
        item
        for item in result["checks"]
        if item["id"] == "assessment_recovery_queue_clear"
    )

    assert result["status"] == "ready"
    assert check["required"] is False
    assert check["passed"] is True
    assert result["assessment_recovery"]["clear"] is True


def test_interrupted_assessment_queue_degrades_readiness_without_authorizing_delivery() -> None:
    result = _build(
        {
            "status": "attention_required",
            "clear": False,
            "recovery_required": 2,
            "stale_active": 1,
            "active": 1,
            "blockers": [],
        }
    )
    check = next(
        item
        for item in result["checks"]
        if item["id"] == "assessment_recovery_queue_clear"
    )

    assert result["status"] == "degraded"
    assert "assessment_recovery_queue_clear" in result["warnings"]
    assert check["passed"] is False
    assert check["observed"]["recovery_required"] == 2
    assert "/operations/recovery/assessments" in check["remediation"]
    assert result["client_delivery_allowed"] is False


def test_assessment_recovery_routes_are_required_for_production_readiness() -> None:
    assert "GET /operations/recovery/assessments" in REQUIRED_OPERATION_ROUTES
    assert (
        "POST /operations/recovery/assessment/{run_id}/resume"
        in REQUIRED_OPERATION_ROUTES
    )
