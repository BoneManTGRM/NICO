from __future__ import annotations

from nico.backup_restore_readiness_patch import build_operations_readiness
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


def _assessment_clear() -> dict:
    return {
        "status": "clear",
        "clear": True,
        "recovery_required": 0,
        "stale_active": 0,
        "active": 0,
        "blockers": [],
    }


def _build(backup_restore: dict) -> dict:
    return build_operations_readiness(
        sorted(REQUIRED_OPERATION_ROUTES),
        deployment=_deployment(),
        storage=_storage(),
        storage_schema=_schema(),
        scanner_recovery=_scanner_clear(),
        assessment_recovery=_assessment_clear(),
        backup_restore=backup_restore,
        features=_features(),
        report_truth=_truth(),
        runtime=_runtime(),
    )


def test_current_backup_and_restore_evidence_passes_advisory_check() -> None:
    result = _build(
        {
            "status": "ready",
            "backup_restore_ready": True,
            "persistence_available": True,
            "blockers": [],
            "warnings": [],
            "latest_backup": {"present": True, "completed_at": "2026-07-13T00:00:00Z"},
            "latest_restore_drill": {"present": True, "completed_at": "2026-07-12T00:00:00Z"},
        }
    )
    check = next(item for item in result["checks"] if item["id"] == "backup_restore_verified")

    assert result["status"] == "ready"
    assert check["required"] is False
    assert check["passed"] is True
    assert result["backup_restore"]["ready"] is True
    assert result["backup_restore"]["automatic_backup"] is False
    assert result["backup_restore"]["automatic_restore"] is False
    assert result["backup_restore"]["client_delivery_allowed"] is False


def test_missing_evidence_degrades_but_does_not_claim_postgres_failure() -> None:
    result = _build(
        {
            "status": "blocked",
            "backup_restore_ready": False,
            "persistence_available": True,
            "blockers": ["backup_evidence_missing", "restore_drill_missing"],
            "warnings": [],
            "latest_backup": {"present": False},
            "latest_restore_drill": {"present": False},
        }
    )
    check = next(item for item in result["checks"] if item["id"] == "backup_restore_verified")

    assert result["status"] == "degraded"
    assert result["operational_ready"] is False
    assert "backup_restore_verified" in result["warnings"]
    assert "backup_restore_verified" not in result["blockers"]
    assert check["passed"] is False
    assert check["observed"]["backup_present"] is False
    assert check["observed"]["restore_drill_present"] is False
    assert "/operations/backup-restore" in check["remediation"]
    assert result["client_delivery_allowed"] is False


def test_backup_restore_routes_are_required_in_operations_inventory() -> None:
    assert "GET /operations/backup-restore" in REQUIRED_OPERATION_ROUTES
    assert "POST /operations/backup-restore/backup-evidence" in REQUIRED_OPERATION_ROUTES
    assert "POST /operations/backup-restore/restore-drill" in REQUIRED_OPERATION_ROUTES


def test_missing_backup_route_blocks_required_route_check() -> None:
    routes = set(REQUIRED_OPERATION_ROUTES)
    routes.remove("POST /operations/backup-restore/restore-drill")
    result = build_operations_readiness(
        sorted(routes),
        deployment=_deployment(),
        storage=_storage(),
        storage_schema=_schema(),
        scanner_recovery=_scanner_clear(),
        assessment_recovery=_assessment_clear(),
        backup_restore={
            "status": "ready",
            "backup_restore_ready": True,
            "latest_backup": {"present": True},
            "latest_restore_drill": {"present": True},
            "blockers": [],
            "warnings": [],
        },
        features=_features(),
        report_truth=_truth(),
        runtime=_runtime(),
    )

    assert result["status"] == "blocked"
    assert "required_routes_registered" in result["blockers"]
    assert "POST /operations/backup-restore/restore-drill" in result["missing_routes"]
