from __future__ import annotations

import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Protocol

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  customer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS authorized_repositories (
  repository_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  repository TEXT NOT NULL,
  authorization_scope JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS assessment_runs (
  run_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workflow TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  risk_trend TEXT,
  dependency_trend TEXT,
  ci_reliability_trend TEXT,
  qa_readiness_trend TEXT,
  backlog_health_trend TEXT,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS scanner_runs (
  scan_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_items (
  evidence_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT,
  filename TEXT NOT NULL,
  content_type TEXT,
  size_bytes INTEGER NOT NULL,
  metadata JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
  report_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  format TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS client_jobs (
  job_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS client_job_exports (
  export_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  customer_id TEXT,
  project_id TEXT,
  format TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_queue_items (
  approval_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_pr_records (
  draft_pr_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  approval_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  audit_id TEXT PRIMARY KEY,
  customer_id TEXT,
  project_id TEXT,
  action TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
"""

JSONB_TABLE_MAP = {
    "repositories": ("authorized_repositories", "repository_id"),
    "assessment_runs": ("assessment_runs", "run_id"),
    "scanner_runs": ("scanner_runs", "scan_id"),
    "evidence_items": ("evidence_items", "evidence_id"),
    "reports": ("reports", "report_id"),
    "client_jobs": ("client_jobs", "job_id"),
    "client_job_exports": ("client_job_exports", "export_id"),
    "approvals": ("approval_queue_items", "approval_id"),
    "draft_pr_records": ("draft_pr_records", "draft_pr_id"),
    "audit_log": ("audit_log", "audit_id"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _copy(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)


def _with_default_metadata(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(payload)
    item.setdefault("id", item_id)
    item.setdefault("created_at", utc_now())
    item["updated_at"] = utc_now()
    return item


class StorageAdapter(Protocol):
    def status(self) -> dict[str, Any]: ...
    def schema(self) -> str: ...
    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, table: str, item_id: str) -> dict[str, Any] | None: ...
    def list(self, table: str, customer_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]: ...


class MemoryAdapter:
    def __init__(self, persistence_note: str | None = None) -> None:
        self.persistence_note = persistence_note or "DATABASE_URL is not configured; using in-memory fallback and marking persistence unavailable."
        self._tables: dict[str, dict[str, dict[str, Any]]] = {
            "customers": {},
            "projects": {},
            "repositories": {},
            "assessment_runs": {},
            "scanner_runs": {},
            "evidence_items": {},
            "reports": {},
            "client_jobs": {},
            "client_job_exports": {},
            "approvals": {},
            "draft_pr_records": {},
            "audit_log": {},
        }

    def status(self) -> dict[str, Any]:
        return {
            "mode": "memory",
            "adapter": "memory",
            "database_url_configured": bool(os.getenv("DATABASE_URL", "").strip()),
            "persistence_available": False,
            "persistence_note": self.persistence_note,
            "schema_available": True,
            "adapter_contract_available": True,
            "migration_endpoint_available": True,
        }

    def schema(self) -> str:
        return POSTGRES_SCHEMA

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if table not in self._tables:
            self._tables[table] = {}
        item = _with_default_metadata(item_id, payload)
        self._tables[table][item_id] = item
        return _copy(item)

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        item = self._tables.get(table, {}).get(item_id)
        return _copy(item) if item is not None else None

    def list(self, table: str, customer_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
        items = list(self._tables.get(table, {}).values())
        if customer_id:
            items = [item for item in items if item.get("customer_id") == customer_id]
        if project_id:
            items = [item for item in items if item.get("project_id") == project_id]
        return deepcopy(items)


class PostgresAdapter:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except Exception as exc:  # pragma: no cover - exercised through Storage fallback tests
            raise RuntimeError(f"psycopg unavailable: {exc}") from exc
        self.database_url = database_url
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._jsonb = Jsonb
        self._init_schema()

    def _connect(self):
        return self._psycopg.connect(self.database_url, row_factory=self._dict_row)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(POSTGRES_SCHEMA)
            conn.commit()

    def status(self) -> dict[str, Any]:
        return {
            "mode": "postgres",
            "adapter": "postgres",
            "database_url_configured": True,
            "persistence_available": True,
            "persistence_note": "Postgres persistence is active. Assessment runs, reports, approvals, evidence, and audit records are durable.",
            "schema_available": True,
            "adapter_contract_available": True,
            "migration_endpoint_available": True,
        }

    def schema(self) -> str:
        return POSTGRES_SCHEMA

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = _with_default_metadata(item_id, payload)
        if table == "customers":
            self._put_customer(item_id, item)
        elif table == "projects":
            self._put_project(item_id, item)
        elif table in JSONB_TABLE_MAP:
            self._put_jsonb(table, item_id, item)
        else:
            raise ValueError(f"Unknown storage table: {table}")
        return _copy(item)

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        if table == "customers":
            rows = self._query("SELECT customer_id, name, created_at FROM customers WHERE customer_id=%s", (item_id,))
            return self._normalize_customer(rows[0]) if rows else None
        if table == "projects":
            rows = self._query("SELECT project_id, customer_id, name, created_at FROM projects WHERE project_id=%s", (item_id,))
            return self._normalize_project(rows[0]) if rows else None
        if table in JSONB_TABLE_MAP:
            db_table, id_col = JSONB_TABLE_MAP[table]
            rows = self._query(f"SELECT * FROM {db_table} WHERE {id_col}=%s", (item_id,))
            return self._normalize_jsonb(table, rows[0]) if rows else None
        return None

    def list(self, table: str, customer_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
        if table == "customers":
            rows = self._query("SELECT customer_id, name, created_at FROM customers ORDER BY created_at ASC", ())
            return [self._normalize_customer(row) for row in rows]
        if table == "projects":
            where, params = self._scope_where(customer_id, None)
            rows = self._query(f"SELECT project_id, customer_id, name, created_at FROM projects {where} ORDER BY created_at ASC", params)
            return [self._normalize_project(row) for row in rows]
        if table in JSONB_TABLE_MAP:
            db_table, _ = JSONB_TABLE_MAP[table]
            where, params = self._scope_where(customer_id, project_id)
            rows = self._query(f"SELECT * FROM {db_table} {where} ORDER BY created_at ASC", params)
            return [self._normalize_jsonb(table, row) for row in rows]
        return []

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()

    def _scope_where(self, customer_id: str | None, project_id: str | None) -> tuple[str, tuple[Any, ...]]:
        clauses = []
        params: list[Any] = []
        if customer_id:
            clauses.append("customer_id=%s")
            params.append(customer_id)
        if project_id:
            clauses.append("project_id=%s")
            params.append(project_id)
        return ("WHERE " + " AND ".join(clauses), tuple(params)) if clauses else ("", ())

    def _put_customer(self, item_id: str, item: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO customers (customer_id, name, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (customer_id) DO UPDATE SET name=EXCLUDED.name
            """,
            (item_id, str(item.get("name") or item_id), item.get("created_at")),
        )

    def _put_project(self, item_id: str, item: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO projects (project_id, customer_id, name, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_id) DO UPDATE SET customer_id=EXCLUDED.customer_id, name=EXCLUDED.name
            """,
            (item_id, item.get("customer_id") or "default_customer", str(item.get("name") or item_id), item.get("created_at")),
        )

    def _put_jsonb(self, table: str, item_id: str, item: dict[str, Any]) -> None:
        json_payload = self._jsonb(item)
        if table == "assessment_runs":
            self._execute(
                """
                INSERT INTO assessment_runs (run_id, customer_id, project_id, workflow, status, payload, risk_trend, dependency_trend, ci_reliability_trend, qa_readiness_trend, backlog_health_trend, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET customer_id=EXCLUDED.customer_id, project_id=EXCLUDED.project_id, workflow=EXCLUDED.workflow, status=EXCLUDED.status, payload=EXCLUDED.payload
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("workflow") or "unknown", item.get("status") or "unknown", json_payload, item.get("risk_trend"), item.get("dependency_trend"), item.get("ci_reliability_trend"), item.get("qa_readiness_trend"), item.get("backlog_health_trend"), item.get("created_at")),
            )
            return
        if table == "scanner_runs":
            self._execute(
                """
                INSERT INTO scanner_runs (scan_id, customer_id, project_id, status, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (scan_id) DO UPDATE SET status=EXCLUDED.status, payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("status") or "unknown", json_payload, item.get("created_at"), item.get("updated_at")),
            )
            return
        if table == "evidence_items":
            self._execute(
                """
                INSERT INTO evidence_items (evidence_id, customer_id, project_id, run_id, filename, content_type, size_bytes, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_id) DO UPDATE SET customer_id=EXCLUDED.customer_id, project_id=EXCLUDED.project_id, run_id=EXCLUDED.run_id, filename=EXCLUDED.filename, content_type=EXCLUDED.content_type, size_bytes=EXCLUDED.size_bytes, metadata=EXCLUDED.metadata
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("run_id"), item.get("filename") or item_id, item.get("content_type"), int(item.get("size_bytes") or 0), json_payload, item.get("created_at")),
            )
            return
        if table == "reports":
            self._execute(
                """
                INSERT INTO reports (report_id, customer_id, project_id, run_id, format, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE SET customer_id=EXCLUDED.customer_id, project_id=EXCLUDED.project_id, run_id=EXCLUDED.run_id, format=EXCLUDED.format, payload=EXCLUDED.payload
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("run_id") or item_id, item.get("format") or "package", json_payload, item.get("created_at")),
            )
            return
        if table == "client_jobs":
            self._execute(
                """
                INSERT INTO client_jobs (job_id, customer_id, project_id, status, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET status=EXCLUDED.status, payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("status") or "unknown", json_payload, item.get("created_at"), item.get("updated_at")),
            )
            return
        if table == "client_job_exports":
            self._execute(
                """
                INSERT INTO client_job_exports (export_id, job_id, customer_id, project_id, format, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (export_id) DO UPDATE SET payload=EXCLUDED.payload, format=EXCLUDED.format
                """,
                (item_id, item.get("job_id") or item_id, item.get("customer_id"), item.get("project_id"), item.get("format") or "json", json_payload, item.get("created_at")),
            )
            return
        if table == "approvals":
            self._execute(
                """
                INSERT INTO approval_queue_items (approval_id, customer_id, project_id, status, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (approval_id) DO UPDATE SET status=EXCLUDED.status, payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("status") or "pending", json_payload, item.get("created_at"), item.get("updated_at")),
            )
            return
        if table == "draft_pr_records":
            self._execute(
                """
                INSERT INTO draft_pr_records (draft_pr_id, customer_id, project_id, approval_id, status, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (draft_pr_id) DO UPDATE SET status=EXCLUDED.status, payload=EXCLUDED.payload
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("approval_id") or "unknown", item.get("status") or "unknown", json_payload, item.get("created_at")),
            )
            return
        if table == "audit_log":
            self._execute(
                """
                INSERT INTO audit_log (audit_id, customer_id, project_id, action, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_id) DO UPDATE SET payload=EXCLUDED.payload
                """,
                (item_id, item.get("customer_id"), item.get("project_id"), item.get("action") or "unknown", json_payload, item.get("created_at")),
            )
            return
        if table == "repositories":
            self._execute(
                """
                INSERT INTO authorized_repositories (repository_id, customer_id, project_id, repository, authorization_scope, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (repository_id) DO UPDATE SET customer_id=EXCLUDED.customer_id, project_id=EXCLUDED.project_id, repository=EXCLUDED.repository, authorization_scope=EXCLUDED.authorization_scope
                """,
                (item_id, item.get("customer_id") or "default_customer", item.get("project_id") or "default_project", item.get("repository") or item_id, json_payload, item.get("created_at")),
            )

    def _normalize_customer(self, row: dict[str, Any]) -> dict[str, Any]:
        return {"customer_id": row.get("customer_id"), "name": row.get("name"), "created_at": str(row.get("created_at")), "id": row.get("customer_id")}

    def _normalize_project(self, row: dict[str, Any]) -> dict[str, Any]:
        return {"project_id": row.get("project_id"), "customer_id": row.get("customer_id"), "name": row.get("name"), "created_at": str(row.get("created_at")), "id": row.get("project_id")}

    def _normalize_jsonb(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row.get("payload") or row.get("metadata") or row.get("authorization_scope") or {})
        if table == "assessment_runs":
            payload.update({"run_id": row.get("run_id"), "customer_id": row.get("customer_id"), "project_id": row.get("project_id"), "workflow": row.get("workflow"), "status": row.get("status"), "created_at": str(row.get("created_at"))})
        elif table == "scanner_runs":
            payload.update({"scan_id": row.get("scan_id"), "customer_id": row.get("customer_id"), "project_id": row.get("project_id"), "status": row.get("status"), "created_at": str(row.get("created_at")), "updated_at": str(row.get("updated_at"))})
        elif table == "reports":
            payload.update({"report_id": row.get("report_id"), "customer_id": row.get("customer_id"), "project_id": row.get("project_id"), "run_id": row.get("run_id"), "format": row.get("format"), "created_at": str(row.get("created_at"))})
        elif table == "approvals":
            payload.update({"approval_id": row.get("approval_id"), "customer_id": row.get("customer_id"), "project_id": row.get("project_id"), "status": row.get("status"), "created_at": str(row.get("created_at")), "updated_at": str(row.get("updated_at"))})
        elif table == "audit_log":
            payload.update({"audit_id": row.get("audit_id"), "customer_id": row.get("customer_id"), "project_id": row.get("project_id"), "action": row.get("action"), "created_at": str(row.get("created_at"))})
        else:
            _, id_col = JSONB_TABLE_MAP[table]
            payload.setdefault(id_col, row.get(id_col))
            payload.setdefault("customer_id", row.get("customer_id"))
            payload.setdefault("project_id", row.get("project_id"))
            payload.setdefault("created_at", str(row.get("created_at")))
            if row.get("updated_at") is not None:
                payload.setdefault("updated_at", str(row.get("updated_at")))
        payload.setdefault("id", row.get(JSONB_TABLE_MAP[table][1]))
        return payload


class Storage:
    """Storage facade with a safe memory fallback and optional Postgres persistence."""

    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.disable_postgres = os.getenv("NICO_DISABLE_POSTGRES", "false").lower() == "true"
        self.adapter_error = ""
        self.adapter: StorageAdapter
        if self.database_url and not self.disable_postgres:
            try:
                self.adapter = PostgresAdapter(self.database_url)
            except Exception as exc:
                self.adapter_error = str(exc)
                self.adapter = MemoryAdapter(
                    "DATABASE_URL is configured, but Postgres persistence could not start; using in-memory fallback and marking persistence unavailable."
                )
        else:
            note = (
                "Postgres persistence is disabled by NICO_DISABLE_POSTGRES; using in-memory fallback and marking persistence unavailable."
                if self.database_url and self.disable_postgres
                else "DATABASE_URL is not configured; using in-memory fallback and marking persistence unavailable."
            )
            self.adapter = MemoryAdapter(note)

    @property
    def mode(self) -> str:
        return str(self.status().get("mode"))

    @property
    def adapter_name(self) -> str:
        return str(self.status().get("adapter"))

    @property
    def persistence_available(self) -> bool:
        return bool(self.status().get("persistence_available"))

    @property
    def persistence_note(self) -> str:
        return str(self.status().get("persistence_note"))

    def status(self) -> dict[str, Any]:
        status = dict(self.adapter.status())
        status["database_url_configured"] = bool(self.database_url)
        status["postgres_disabled"] = self.disable_postgres
        if self.adapter_error:
            status["adapter_error"] = self.adapter_error[:240]
        if not status.get("persistence_available"):
            status["durability_warning"] = "Retained run history, reports, approvals, and final-review evidence may disappear after restart while memory fallback is active."
        return status

    def schema(self) -> str:
        return self.adapter.schema()

    def migration_plan(self) -> dict[str, Any]:
        status = self.status()
        return {
            "status": "active" if status.get("persistence_available") else "planned",
            "safe_default": "memory_fallback",
            "database_url_configured": bool(self.database_url),
            "postgres_disabled": self.disable_postgres,
            "requires_driver": "psycopg is required for Postgres persistence.",
            "tests_without_database_url": "required",
            "schema": POSTGRES_SCHEMA,
            "storage_status": status,
        }

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.adapter.put(table, item_id, payload)

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        return self.adapter.get(table, item_id)

    def list(self, table: str, customer_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
        return self.adapter.list(table, customer_id=customer_id, project_id=project_id)

    def audit(self, action: str, payload: dict[str, Any], customer_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
        audit_id = new_id("audit")
        return self.put("audit_log", audit_id, {
            "audit_id": audit_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "action": action,
            "payload": payload,
        })


STORE = Storage()
