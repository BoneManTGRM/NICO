from __future__ import annotations

import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Storage:
    """Small storage abstraction.

    Production can wire DATABASE_URL to a Postgres implementation later. This class keeps
    NICO safe today by falling back to in-memory storage rather than failing deploys.
    """

    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.mode = "postgres_unavailable" if self.database_url else "memory"
        self.persistence_available = False
        self.persistence_note = (
            "DATABASE_URL is configured, but this safe MVP uses the in-memory fallback until the Postgres adapter is enabled."
            if self.database_url else
            "DATABASE_URL is not configured; using in-memory fallback and marking persistence unavailable."
        )
        self._tables: dict[str, dict[str, dict[str, Any]]] = {
            "customers": {},
            "projects": {},
            "repositories": {},
            "assessment_runs": {},
            "scanner_runs": {},
            "evidence_items": {},
            "reports": {},
            "approvals": {},
            "draft_pr_records": {},
            "audit_log": {},
        }

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "persistence_available": self.persistence_available,
            "persistence_note": self.persistence_note,
            "schema_available": True,
        }

    def schema(self) -> str:
        return POSTGRES_SCHEMA

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if table not in self._tables:
            self._tables[table] = {}
        item = deepcopy(payload)
        item.setdefault("id", item_id)
        item.setdefault("created_at", utc_now())
        item["updated_at"] = utc_now()
        self._tables[table][item_id] = item
        return deepcopy(item)

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        item = self._tables.get(table, {}).get(item_id)
        return deepcopy(item) if item is not None else None

    def list(self, table: str, customer_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
        items = list(self._tables.get(table, {}).values())
        if customer_id:
            items = [item for item in items if item.get("customer_id") == customer_id]
        if project_id:
            items = [item for item in items if item.get("project_id") == project_id]
        return deepcopy(items)

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
