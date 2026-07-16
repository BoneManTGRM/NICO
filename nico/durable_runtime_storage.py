from __future__ import annotations

import json
import os
import sqlite3
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from nico.storage import POSTGRES_SCHEMA, STORE, _with_default_metadata

DURABLE_RUNTIME_STORAGE_VERSION = "nico.durable_runtime_storage.v1"
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS nico_records (
    table_name TEXT NOT NULL,
    item_id TEXT NOT NULL,
    customer_id TEXT,
    project_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    payload TEXT NOT NULL,
    PRIMARY KEY (table_name, item_id)
);
CREATE INDEX IF NOT EXISTS idx_nico_records_scope
    ON nico_records(table_name, customer_id, project_id);
CREATE INDEX IF NOT EXISTS idx_nico_records_updated
    ON nico_records(table_name, updated_at);
"""


def _enabled() -> bool:
    return os.getenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "false").strip().lower() == "true"


def _path() -> Path:
    configured = os.getenv("NICO_SQLITE_PATH", "/data/nico-runtime.sqlite3").strip()
    return Path(configured or "/data/nico-runtime.sqlite3")


def _json_default(value: Any) -> str:
    return str(value)


class SQLiteRuntimeAdapter:
    """Small durable adapter for hosted lifecycle state when Postgres is absent.

    The adapter uses WAL mode and short transactions. It implements the same
    storage facade contract used by MemoryAdapter and PostgresAdapter without
    changing assessment payloads or inventing evidence.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database_path),
            timeout=15.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(_SQLITE_SCHEMA)
            connection.commit()

    def status(self) -> dict[str, Any]:
        writable = False
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            writable = os.access(self.database_path.parent, os.W_OK)
        except Exception:
            writable = False
        return {
            "mode": "sqlite",
            "adapter": "sqlite",
            "database_url_configured": bool(os.getenv("DATABASE_URL", "").strip()),
            "persistence_available": writable,
            "persistence_note": "SQLite lifecycle persistence is active on the hosted data path. Assessment runs, scanner heartbeats, reports, approvals, and recovery evidence survive process restarts while the mounted data path remains available.",
            "schema_available": True,
            "adapter_contract_available": True,
            "migration_endpoint_available": True,
            "database_path": str(self.database_path),
            "journal_mode": "wal",
        }

    def schema(self) -> str:
        return _SQLITE_SCHEMA

    def migration_plan(self) -> dict[str, Any]:
        return {
            "status": "active",
            "source": "sqlite_runtime",
            "target": "postgres_optional",
            "database_path": str(self.database_path),
            "schema": POSTGRES_SCHEMA,
            "storage_status": self.status(),
        }

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = _with_default_metadata(item_id, payload)
        serialized = json.dumps(item, sort_keys=True, separators=(",", ":"), default=_json_default)
        customer_id = item.get("customer_id")
        project_id = item.get("project_id")
        created_at = str(item.get("created_at") or "")
        updated_at = str(item.get("updated_at") or created_at)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO nico_records (
                    table_name, item_id, customer_id, project_id,
                    created_at, updated_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(table_name, item_id) DO UPDATE SET
                    customer_id=excluded.customer_id,
                    project_id=excluded.project_id,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (
                    table,
                    item_id,
                    str(customer_id) if customer_id is not None else None,
                    str(project_id) if project_id is not None else None,
                    created_at,
                    updated_at,
                    serialized,
                ),
            )
            connection.commit()
        return deepcopy(item)

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM nico_records WHERE table_name=? AND item_id=?",
                (table, item_id),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row["payload"]))
        return deepcopy(value) if isinstance(value, dict) else None

    def list(
        self,
        table: str,
        customer_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["table_name=?"]
        params: list[Any] = [table]
        if customer_id:
            clauses.append("customer_id=?")
            params.append(customer_id)
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        sql = (
            "SELECT payload FROM nico_records WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC, item_id ASC"
        )
        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            value = json.loads(str(row["payload"]))
            if isinstance(value, dict):
                values.append(value)
        return deepcopy(values)


def install_durable_runtime_storage() -> dict[str, Any]:
    current = STORE.status()
    if bool(current.get("persistence_available")):
        return {
            "status": "already_durable",
            "version": DURABLE_RUNTIME_STORAGE_VERSION,
            "adapter": current.get("adapter") or current.get("mode") or "unknown",
            "persistence_available": True,
        }
    if not _enabled():
        return {
            "status": "disabled",
            "version": DURABLE_RUNTIME_STORAGE_VERSION,
            "adapter": current.get("adapter") or current.get("mode") or "unknown",
            "persistence_available": False,
        }

    adapter = SQLiteRuntimeAdapter(_path())
    status = adapter.status()
    if not status.get("persistence_available"):
        raise RuntimeError("SQLite runtime storage path is not writable")
    STORE.adapter = adapter
    STORE.adapter_error = ""
    return {
        "status": "installed",
        "version": DURABLE_RUNTIME_STORAGE_VERSION,
        **status,
    }


__all__ = [
    "DURABLE_RUNTIME_STORAGE_VERSION",
    "SQLiteRuntimeAdapter",
    "install_durable_runtime_storage",
]
