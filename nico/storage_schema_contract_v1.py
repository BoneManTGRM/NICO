"""Storage contract data and pure comparison helpers; no storage initialization."""
from __future__ import annotations

import hashlib
import json
from typing import Any

STORAGE_SCHEMA_CONTRACT_VERSION = "2026.09.08.1"

STORAGE_SCHEMA_MIGRATION_TABLE = "nico_schema_migrations"

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
    "scanner_raw_artifacts": (
        "artifact_id", "run_id", "scan_id", "customer_id", "project_id",
        "repository", "commit_sha", "scanner_name", "raw_sha256",
        "gzip_sha256", "gzip_blob", "created_at",
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
