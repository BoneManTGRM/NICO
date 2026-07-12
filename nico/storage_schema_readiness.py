from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from nico.admin_security import require_admin_write
from nico.storage import STORE

STORAGE_SCHEMA_READINESS_SCHEMA = "nico.storage_schema_readiness.v1"
STORAGE_SCHEMA_CONTRACT_VERSION = "2026.07.13.1"
STORAGE_SCHEMA_MIGRATION_TABLE = "nico_schema_migrations"
STORAGE_SCHEMA_READINESS_ROUTE = ("GET", "/operations/storage-schema")
REQUIRED_STORAGE_SCHEMA_ROUTE = "GET /operations/storage-schema"

EXPECTED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "customers": ("customer_id", "name", "created_at"),
    "projects": ("project_id", "customer_id", "name", "created_at"),
    "authorized_repositories": (
        "repository_id",
        "customer_id",
        "project_id",
        "repository",
        "authorization_scope",
        "created_at",
    ),
    "assessment_runs": (
        "run_id",
        "customer_id",
        "project_id",
        "workflow",
        "status",
        "payload",
        "risk_trend",
        "dependency_trend",
        "ci_reliability_trend",
        "qa_readiness_trend",
        "backlog_health_trend",
        "created_at",
    ),
    "scanner_runs": (
        "scan_id",
        "customer_id",
        "project_id",
        "status",
        "payload",
        "created_at",
        "updated_at",
    ),
    "evidence_items": (
        "evidence_id",
        "customer_id",
        "project_id",
        "run_id",
        "filename",
        "content_type",
        "size_bytes",
        "metadata",
        "created_at",
    ),
    "reports": (
        "report_id",
        "customer_id",
        "project_id",
        "run_id",
        "format",
        "payload",
        "created_at",
    ),
    "client_jobs": (
        "job_id",
        "customer_id",
        "project_id",
        "status",
        "payload",
        "created_at",
        "updated_at",
    ),
    "client_job_exports": (
        "export_id",
        "job_id",
        "customer_id",
        "project_id",
        "format",
        "payload",
        "created_at",
    ),
    "approval_queue_items": (
        "approval_id",
        "customer_id",
        "project_id",
        "status",
        "payload",
        "created_at",
        "updated_at",
    ),
    "draft_pr_records": (
        "draft_pr_id",
        "customer_id",
        "project_id",
        "approval_id",
        "status",
        "payload",
        "created_at",
    ),
    "audit_log": (
        "audit_id",
        "customer_id",
        "project_id",
        "action",
        "payload",
        "created_at",
    ),
    STORAGE_SCHEMA_MIGRATION_TABLE: (
        "version",
        "contract_sha256",
        "applied_at",
        "verified_at",
    ),
}

MIGRATION_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {STORAGE_SCHEMA_MIGRATION_TABLE} (
  version TEXT PRIMARY KEY,
  contract_sha256 TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL,
  verified_at TIMESTAMPTZ NOT NULL
)
"""

_CACHED_READINESS: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def storage_schema_contract() -> dict[str, Any]:
    contract = {
        "version": STORAGE_SCHEMA_CONTRACT_VERSION,
        "tables": {
            table: list(columns)
            for table, columns in sorted(EXPECTED_TABLE_COLUMNS.items())
        },
        "migration_table": STORAGE_SCHEMA_MIGRATION_TABLE,
    }
    contract["contract_sha256"] = _canonical_hash(contract)
    return contract


def normalize_catalog_rows(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    catalog: dict[str, set[str]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        table = str(raw.get("table_name") or "").strip()
        column = str(raw.get("column_name") or "").strip()
        if table and column:
            catalog.setdefault(table, set()).add(column)
    return catalog


def compare_schema_catalog(catalog: dict[str, set[str]]) -> dict[str, Any]:
    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    for table, expected_columns in EXPECTED_TABLE_COLUMNS.items():
        observed = catalog.get(table)
        if observed is None:
            missing_tables.append(table)
            continue
        missing = sorted(set(expected_columns) - observed)
        if missing:
            missing_columns[table] = missing
    return {
        "complete": not missing_tables and not missing_columns,
        "missing_tables": sorted(missing_tables),
        "missing_columns": dict(sorted(missing_columns.items())),
        "expected_table_count": len(EXPECTED_TABLE_COLUMNS),
        "observed_table_count": len(catalog),
    }


def _safe_adapter_name(store: Any) -> str:
    try:
        return str(store.status().get("adapter") or "unknown")
    except Exception:
        return "unknown"


def _query_catalog(adapter: Any) -> list[dict[str, Any]]:
    query = getattr(adapter, "_query", None)
    if not callable(query):
        raise RuntimeError("storage adapter does not expose a bounded catalog query")
    return query(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
        ORDER BY table_name ASC, ordinal_position ASC
        """,
        (),
    )


def _ensure_migration_ledger(adapter: Any, contract: dict[str, Any], now: str) -> None:
    execute = getattr(adapter, "_execute", None)
    if not callable(execute):
        raise RuntimeError("storage adapter does not expose bounded migration execution")
    execute(MIGRATION_TABLE_DDL, ())
    execute(
        f"""
        INSERT INTO {STORAGE_SCHEMA_MIGRATION_TABLE} (version, contract_sha256, applied_at, verified_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (version) DO UPDATE
        SET verified_at=EXCLUDED.verified_at
        """,
        (
            STORAGE_SCHEMA_CONTRACT_VERSION,
            contract["contract_sha256"],
            now,
            now,
        ),
    )


def _read_migration_ledger(adapter: Any) -> list[dict[str, Any]]:
    query = getattr(adapter, "_query", None)
    if not callable(query):
        raise RuntimeError("storage adapter does not expose a bounded migration query")
    return query(
        f"""
        SELECT version, contract_sha256, applied_at, verified_at
        FROM {STORAGE_SCHEMA_MIGRATION_TABLE}
        ORDER BY applied_at ASC, version ASC
        """,
        (),
    )


def _blocked_without_postgres(
    adapter_name: str,
    persistence_available: bool,
    contract: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    return {
        "artifact_schema": STORAGE_SCHEMA_READINESS_SCHEMA,
        "status": "blocked",
        "schema_ready": False,
        "migration_ready": False,
        "adapter": adapter_name,
        "persistence_available": persistence_available,
        "contract_version": STORAGE_SCHEMA_CONTRACT_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "catalog": {
            "complete": False,
            "missing_tables": sorted(EXPECTED_TABLE_COLUMNS),
            "missing_columns": {},
            "expected_table_count": len(EXPECTED_TABLE_COLUMNS),
            "observed_table_count": 0,
        },
        "migration": {
            "current_version_present": False,
            "current_contract_matches": False,
            "record_count": 0,
            "versions": [],
        },
        "blockers": [
            "durable_postgres_required",
            "schema_catalog_unverified",
            "migration_ledger_unverified",
        ],
        "warnings": [],
        "verification_error_type": None,
        "verified_at": now,
        "next_action": "Restore durable Postgres, then verify the exact schema catalog and migration ledger before trusted production work.",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "guardrail": "Schema readiness proves database structure and migration identity only. It does not prove workflow records are complete or authorize client delivery.",
    }


def verify_storage_schema(store: Any = STORE) -> dict[str, Any]:
    contract = storage_schema_contract()
    now = _now()
    adapter_name = _safe_adapter_name(store)
    try:
        status_payload = dict(store.status())
    except Exception:
        status_payload = {}

    persistence_available = bool(status_payload.get("persistence_available"))
    if adapter_name != "postgres" or not persistence_available:
        return _blocked_without_postgres(
            adapter_name,
            persistence_available,
            contract,
            now,
        )

    adapter = getattr(store, "adapter", None)
    blockers: list[str] = []
    error_type = ""
    try:
        _ensure_migration_ledger(adapter, contract, now)
        catalog = normalize_catalog_rows(_query_catalog(adapter))
        catalog_result = compare_schema_catalog(catalog)
        ledger_rows = _read_migration_ledger(adapter)
        current_rows = [
            row
            for row in ledger_rows
            if str(row.get("version") or "") == STORAGE_SCHEMA_CONTRACT_VERSION
        ]
        current_contract_matches = any(
            str(row.get("contract_sha256") or "") == contract["contract_sha256"]
            for row in current_rows
        )
        migration_result = {
            "current_version_present": bool(current_rows),
            "current_contract_matches": current_contract_matches,
            "record_count": len(ledger_rows),
            "versions": [
                str(row.get("version") or "")[:80]
                for row in ledger_rows[:100]
            ],
        }
        if not catalog_result["complete"]:
            blockers.append("schema_catalog_incomplete")
        if not current_rows:
            blockers.append("migration_version_missing")
        elif not current_contract_matches:
            blockers.append("migration_contract_mismatch")
    except Exception as exc:
        error_type = type(exc).__name__[:120]
        catalog_result = {
            "complete": False,
            "missing_tables": [],
            "missing_columns": {},
            "expected_table_count": len(EXPECTED_TABLE_COLUMNS),
            "observed_table_count": 0,
        }
        migration_result = {
            "current_version_present": False,
            "current_contract_matches": False,
            "record_count": 0,
            "versions": [],
        }
        blockers.extend([
            "schema_verification_failed",
            "migration_ledger_unverified",
        ])

    schema_ready = bool(catalog_result.get("complete"))
    migration_ready = bool(
        migration_result.get("current_version_present")
        and migration_result.get("current_contract_matches")
    )
    status = "ready" if schema_ready and migration_ready and not blockers else "blocked"
    return {
        "artifact_schema": STORAGE_SCHEMA_READINESS_SCHEMA,
        "status": status,
        "schema_ready": schema_ready,
        "migration_ready": migration_ready,
        "adapter": adapter_name,
        "persistence_available": True,
        "contract_version": STORAGE_SCHEMA_CONTRACT_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "catalog": catalog_result,
        "migration": migration_result,
        "blockers": sorted(set(blockers)),
        "warnings": [],
        "verification_error_type": error_type or None,
        "verified_at": now,
        "next_action": (
            "Schema and migration state are verified for the current storage contract."
            if status == "ready"
            else "Apply or repair the required Postgres schema, preserve existing records, and rerun schema verification before trusted production work."
        ),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "guardrail": "Schema readiness proves database structure and migration identity only. It does not prove workflow records are complete or authorize client delivery.",
    }


def refresh_storage_schema_readiness(store: Any = STORE) -> dict[str, Any]:
    global _CACHED_READINESS
    _CACHED_READINESS = verify_storage_schema(store)
    return dict(_CACHED_READINESS)


def cached_storage_schema_readiness(store: Any = STORE) -> dict[str, Any]:
    if _CACHED_READINESS is None:
        return refresh_storage_schema_readiness(store)
    return dict(_CACHED_READINESS)


def _require_operator(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "status": "blocked",
            "code": "operator_authentication_required",
            "message": "Operator authentication is required to verify storage schema state.",
            "admin_write": status,
        },
    )


def storage_schema_readiness_response(
    refresh: bool = False,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    if refresh:
        return refresh_storage_schema_readiness()
    return cached_storage_schema_readiness()


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def install_storage_schema_readiness(target: FastAPI) -> dict[str, Any]:
    existing = _route_pairs(target)
    present = STORAGE_SCHEMA_READINESS_ROUTE in existing
    if not present:
        target.get("/operations/storage-schema", tags=["operations"])(
            storage_schema_readiness_response
        )
        target.openapi_schema = None

    from nico.operations_readiness import REQUIRED_OPERATION_ROUTES

    REQUIRED_OPERATION_ROUTES.add(REQUIRED_STORAGE_SCHEMA_ROUTE)
    startup_result = refresh_storage_schema_readiness()
    if STORAGE_SCHEMA_READINESS_ROUTE not in _route_pairs(target):
        raise RuntimeError("Storage schema readiness route registration failed")
    return {
        "installed": True,
        "route_reused": present,
        "route": REQUIRED_STORAGE_SCHEMA_ROUTE,
        "startup_status": startup_result.get("status"),
        "contract_version": STORAGE_SCHEMA_CONTRACT_VERSION,
        "contract_sha256": startup_result.get("contract_sha256"),
    }


__all__ = [
    "STORAGE_SCHEMA_READINESS_SCHEMA",
    "STORAGE_SCHEMA_CONTRACT_VERSION",
    "STORAGE_SCHEMA_MIGRATION_TABLE",
    "STORAGE_SCHEMA_READINESS_ROUTE",
    "REQUIRED_STORAGE_SCHEMA_ROUTE",
    "EXPECTED_TABLE_COLUMNS",
    "MIGRATION_TABLE_DDL",
    "storage_schema_contract",
    "normalize_catalog_rows",
    "compare_schema_catalog",
    "verify_storage_schema",
    "refresh_storage_schema_readiness",
    "cached_storage_schema_readiness",
    "storage_schema_readiness_response",
    "install_storage_schema_readiness",
]
