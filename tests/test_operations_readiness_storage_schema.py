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


def _schema(*, ready: bool = True) -> dict:
    return {
        "status": "ready" if ready else "blocked",
        "schema_ready": ready,
        "migration_ready": ready,
        "contract_version": "2026.07.13.1",
        "contract_sha256": "b" * 64,
        "blockers": [] if ready else ["schema_catalog_incomplete"],
    }


def _result(schema: dict) -> dict:
    return build_operations_readiness(
        sorted(REQUIRED_OPERATION_ROUTES),
        deployment=_deployment(),
        storage=_storage(),
        storage_schema=schema,
        features=_features(),
        report_truth=_truth(),
        runtime=_runtime(),
    )


def test_verified_schema_is_a_required_passing_readiness_check() -> None:
    result = _result(_schema())
    check = next(item for item in result["checks"] if item["id"] == "storage_schema_verified")

    assert result["status"] == "ready"
    assert check["required"] is True
    assert check["passed"] is True
    assert result["storage_schema"] == {
        "status": "ready",
        "schema_ready": True,
        "migration_ready": True,
        "contract_version": "2026.07.13.1",
        "contract_sha256": "b" * 64,
        "blockers": [],
    }


def test_durable_postgres_with_an_unverified_schema_is_still_blocked() -> None:
    result = _result(_schema(ready=False))
    check = next(item for item in result["checks"] if item["id"] == "storage_schema_verified")

    assert result["status"] == "blocked"
    assert result["operational_ready"] is False
    assert "durable_storage" not in result["blockers"]
    assert "storage_schema_verified" in result["blockers"]
    assert check["passed"] is False
    assert check["observed"]["blockers"] == ["schema_catalog_incomplete"]
    assert "operations/storage-schema" in check["remediation"]


def test_storage_schema_route_is_part_of_the_static_readiness_contract() -> None:
    assert "GET /operations/storage-schema" in REQUIRED_OPERATION_ROUTES
