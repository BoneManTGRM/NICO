from __future__ import annotations

from nico.operations_readiness import REQUIRED_OPERATION_ROUTES, build_operations_readiness


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


def _build(recovery: dict) -> dict:
    return build_operations_readiness(
        sorted(REQUIRED_OPERATION_ROUTES),
        deployment=_deployment(),
        storage=_storage(),
        storage_schema=_schema(),
        scanner_recovery=recovery,
        features=_features(),
        report_truth=_truth(),
        runtime=_runtime(),
    )


def test_clear_scanner_recovery_queue_passes_advisory_readiness() -> None:
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
    check = next(item for item in result["checks"] if item["id"] == "scanner_recovery_queue_clear")

    assert result["status"] == "ready"
    assert check["required"] is False
    assert check["passed"] is True
    assert result["scanner_recovery"]["clear"] is True


def test_interrupted_scanner_queue_degrades_but_does_not_falsely_block_core_storage() -> None:
    result = _build(
        {
            "status": "attention_required",
            "clear": False,
            "recovery_required": 2,
            "stale_active": 0,
            "active": 0,
            "blockers": [],
        }
    )
    check = next(item for item in result["checks"] if item["id"] == "scanner_recovery_queue_clear")

    assert result["status"] == "degraded"
    assert result["blockers"] == []
    assert result["warnings"] == ["scanner_recovery_queue_clear"]
    assert check["passed"] is False
    assert check["observed"]["recovery_required"] == 2
    assert "/operations/recovery" in check["remediation"]
    assert result["client_delivery_allowed"] is False


def test_recovery_routes_are_required_for_production_readiness() -> None:
    assert "GET /operations/recovery" in REQUIRED_OPERATION_ROUTES
    assert "POST /operations/recovery/scanner/{scan_id}/resume" in REQUIRED_OPERATION_ROUTES
