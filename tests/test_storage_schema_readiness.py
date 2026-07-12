from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.storage_schema_readiness as schema_readiness
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES
from nico.storage_schema_readiness import (
    EXPECTED_TABLE_COLUMNS,
    REQUIRED_STORAGE_SCHEMA_ROUTE,
    STORAGE_SCHEMA_CONTRACT_VERSION,
    STORAGE_SCHEMA_MIGRATION_TABLE,
    STORAGE_SCHEMA_READINESS_ROUTE,
    compare_schema_catalog,
    install_storage_schema_readiness,
    normalize_catalog_rows,
    storage_schema_contract,
    verify_storage_schema,
)


class _FakePostgresAdapter:
    def __init__(self, catalog: dict[str, set[str]] | None = None) -> None:
        self.catalog = catalog or {
            table: set(columns)
            for table, columns in EXPECTED_TABLE_COLUMNS.items()
        }
        self.ledger: list[dict[str, Any]] = []
        self.fail_queries = False
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executions.append((sql, params))
        if "INSERT INTO nico_schema_migrations" in sql:
            version, contract_sha256, applied_at, verified_at = params
            existing = next((item for item in self.ledger if item["version"] == version), None)
            if existing:
                existing["contract_sha256"] = contract_sha256
                existing["verified_at"] = verified_at
            else:
                self.ledger.append(
                    {
                        "version": version,
                        "contract_sha256": contract_sha256,
                        "applied_at": applied_at,
                        "verified_at": verified_at,
                    }
                )

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        if self.fail_queries:
            raise RuntimeError("database unavailable with secret=must-not-leak")
        if "information_schema.columns" in sql:
            return [
                {"table_name": table, "column_name": column}
                for table in sorted(self.catalog)
                for column in sorted(self.catalog[table])
            ]
        if "FROM nico_schema_migrations" in sql:
            return deepcopy(self.ledger)
        raise AssertionError(f"Unexpected query: {sql}")


class _FakeStore:
    def __init__(self, adapter: Any, *, persistence_available: bool = True) -> None:
        self.adapter = adapter
        self._persistence_available = persistence_available

    def status(self) -> dict[str, Any]:
        return {
            "adapter": "postgres" if self._persistence_available else "memory",
            "persistence_available": self._persistence_available,
            "database_url_configured": self._persistence_available,
        }


def _complete_catalog() -> dict[str, set[str]]:
    return {
        table: set(columns)
        for table, columns in EXPECTED_TABLE_COLUMNS.items()
    }


def test_storage_schema_contract_is_stable_and_hash_bound() -> None:
    first = storage_schema_contract()
    second = storage_schema_contract()

    assert first == second
    assert first["version"] == STORAGE_SCHEMA_CONTRACT_VERSION
    assert len(first["contract_sha256"]) == 64
    assert first["tables"][STORAGE_SCHEMA_MIGRATION_TABLE] == [
        "version",
        "contract_sha256",
        "applied_at",
        "verified_at",
    ]


def test_catalog_normalization_and_comparison_report_exact_missing_state() -> None:
    rows = [
        {"table_name": "assessment_runs", "column_name": "run_id"},
        {"table_name": "assessment_runs", "column_name": "status"},
        {"table_name": "reports", "column_name": "report_id"},
        {"table_name": "", "column_name": "ignored"},
    ]

    catalog = normalize_catalog_rows(rows)
    result = compare_schema_catalog(catalog)

    assert catalog == {
        "assessment_runs": {"run_id", "status"},
        "reports": {"report_id"},
    }
    assert result["complete"] is False
    assert "customers" in result["missing_tables"]
    assert "assessment_runs" in result["missing_columns"]
    assert "payload" in result["missing_columns"]["assessment_runs"]


def test_complete_postgres_schema_records_and_verifies_current_migration() -> None:
    adapter = _FakePostgresAdapter()
    store = _FakeStore(adapter)

    result = verify_storage_schema(store)

    assert result["status"] == "ready"
    assert result["schema_ready"] is True
    assert result["migration_ready"] is True
    assert result["blockers"] == []
    assert result["catalog"]["complete"] is True
    assert result["migration"]["current_version_present"] is True
    assert result["migration"]["current_contract_matches"] is True
    assert result["migration"]["record_count"] == 1
    assert result["client_delivery_allowed"] is False
    assert any("CREATE TABLE IF NOT EXISTS nico_schema_migrations" in sql for sql, _ in adapter.executions)
    assert any("INSERT INTO nico_schema_migrations" in sql for sql, _ in adapter.executions)


def test_missing_table_or_column_blocks_schema_readiness() -> None:
    catalog = _complete_catalog()
    catalog.pop("reports")
    catalog["assessment_runs"].remove("payload")
    adapter = _FakePostgresAdapter(catalog)

    result = verify_storage_schema(_FakeStore(adapter))

    assert result["status"] == "blocked"
    assert result["schema_ready"] is False
    assert result["migration_ready"] is True
    assert "schema_catalog_incomplete" in result["blockers"]
    assert result["catalog"]["missing_tables"] == ["reports"]
    assert result["catalog"]["missing_columns"]["assessment_runs"] == ["payload"]


def test_memory_fallback_is_never_represented_as_schema_ready() -> None:
    store = _FakeStore(object(), persistence_available=False)

    result = verify_storage_schema(store)

    assert result["status"] == "blocked"
    assert result["schema_ready"] is False
    assert result["migration_ready"] is False
    assert "durable_postgres_required" in result["blockers"]
    assert "schema_catalog_unverified" in result["blockers"]
    assert result["adapter"] == "memory"


def test_database_error_is_bounded_to_error_type_without_raw_message() -> None:
    adapter = _FakePostgresAdapter()
    adapter.fail_queries = True

    result = verify_storage_schema(_FakeStore(adapter))
    rendered = repr(result)

    assert result["status"] == "blocked"
    assert result["verification_error_type"] == "RuntimeError"
    assert "schema_verification_failed" in result["blockers"]
    assert "must-not-leak" not in rendered
    assert "database unavailable" not in rendered


def test_admin_route_requires_auth_supports_refresh_and_is_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    ready = {
        "artifact_schema": "nico.storage_schema_readiness.v1",
        "status": "ready",
        "schema_ready": True,
        "migration_ready": True,
        "contract_version": STORAGE_SCHEMA_CONTRACT_VERSION,
        "contract_sha256": "a" * 64,
        "blockers": [],
    }
    calls = {"count": 0}

    def fake_refresh(store=schema_readiness.STORE):
        calls["count"] += 1
        return dict(ready)

    monkeypatch.setattr(schema_readiness, "refresh_storage_schema_readiness", fake_refresh)
    monkeypatch.setattr(schema_readiness, "cached_storage_schema_readiness", lambda store=schema_readiness.STORE: dict(ready))

    app = FastAPI()
    first = install_storage_schema_readiness(app)
    second = install_storage_schema_readiness(app)
    client = TestClient(app)

    denied = client.get("/operations/storage-schema")
    assert denied.status_code == 403

    cached = client.get(
        "/operations/storage-schema",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert cached.status_code == 200
    assert cached.json()["status"] == "ready"

    refreshed = client.get(
        "/operations/storage-schema?refresh=true",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert refreshed.status_code == 200
    assert calls["count"] >= 3

    route_pairs = {
        (str(method).upper(), str(getattr(route, "path", "")))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert first["route_reused"] is False
    assert second["route_reused"] is True
    assert STORAGE_SCHEMA_READINESS_ROUTE in route_pairs
    assert REQUIRED_STORAGE_SCHEMA_ROUTE in REQUIRED_OPERATION_ROUTES
