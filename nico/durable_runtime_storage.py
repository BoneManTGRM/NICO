from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from nico.storage import POSTGRES_SCHEMA, STORE, _with_default_metadata, utc_now

DURABLE_RUNTIME_STORAGE_VERSION = "nico.durable_runtime_storage.v2"
SQLITE_RESTART_PROBE_VERSION = "nico.sqlite_restart_probe.v1"
_PROCESS_INSTANCE_ID = uuid.uuid4().hex
_RESTART_INSTANCE_KEY = "durability_probe_process_instance"
_RESTART_VERIFIED_KEY = "durability_probe_restart_verified"
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
CREATE TABLE IF NOT EXISTS nico_runtime_meta (
    meta_key TEXT PRIMARY KEY,
    meta_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _enabled() -> bool:
    return os.getenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "false").strip().lower() == "true"


def _path() -> Path:
    configured = os.getenv("NICO_SQLITE_PATH", "/data/nico-runtime.sqlite3").strip()
    return Path(configured or "/data/nico-runtime.sqlite3")


def _json_default(value: Any) -> str:
    return str(value)


class SQLiteRuntimeAdapter:
    """SQLite lifecycle adapter with explicit deployment-survival proof.

    A writable SQLite file proves only that records can be written in the current
    process. It is considered restart-proven only after the same database observes
    a different process-instance marker on a later application boot. Runtime
    storage truth additionally requires the database directory to be a verified
    persistent mount before it may be called durable.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()
        self._restart_probe = self._initialize_restart_probe()

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

    def _meta_value(self, connection: sqlite3.Connection, key: str) -> str:
        row = connection.execute(
            "SELECT meta_value FROM nico_runtime_meta WHERE meta_key=?",
            (key,),
        ).fetchone()
        return str(row["meta_value"] or "") if row is not None else ""

    def _put_meta(self, connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """
            INSERT INTO nico_runtime_meta (meta_key, meta_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value=excluded.meta_value,
                updated_at=excluded.updated_at
            """,
            (key, value, utc_now()),
        )

    def _initialize_restart_probe(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_instance = self._meta_value(connection, _RESTART_INSTANCE_KEY)
            previously_verified = self._meta_value(connection, _RESTART_VERIFIED_KEY).lower() == "true"
            process_instance_changed = bool(
                previous_instance and previous_instance != _PROCESS_INSTANCE_ID
            )
            verified = bool(previously_verified or process_instance_changed)
            self._put_meta(connection, _RESTART_INSTANCE_KEY, _PROCESS_INSTANCE_ID)
            self._put_meta(connection, _RESTART_VERIFIED_KEY, "true" if verified else "false")
            connection.commit()
        return {
            "version": SQLITE_RESTART_PROBE_VERSION,
            "previous_instance_seen": bool(previous_instance),
            "process_instance_changed": process_instance_changed,
            "restart_probe_verified": verified,
            "verification_pending_restart": not verified,
        }

    def status(self) -> dict[str, Any]:
        writable = False
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            writable = os.access(self.database_path.parent, os.W_OK)
        except Exception:
            writable = False
        probe = dict(self._restart_probe)
        return {
            "mode": "sqlite",
            "adapter": "sqlite",
            "database_url_configured": bool(os.getenv("DATABASE_URL", "").strip()),
            "persistence_available": writable,
            "recording_ready": writable,
            "persistence_note": (
                "SQLite lifecycle recording is active. Deployment survival remains a separate verified property."
            ),
            "schema_available": True,
            "adapter_contract_available": True,
            "migration_endpoint_available": True,
            "database_path": str(self.database_path),
            "journal_mode": "wal",
            "restart_probe_version": probe["version"],
            "restart_probe_previous_instance_seen": probe["previous_instance_seen"],
            "restart_probe_process_instance_changed": probe["process_instance_changed"],
            "restart_probe_verified": probe["restart_probe_verified"],
            "verification_pending_restart": probe["verification_pending_restart"],
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
            "status": "already_recording",
            "version": DURABLE_RUNTIME_STORAGE_VERSION,
            "adapter": current.get("adapter") or current.get("mode") or "unknown",
            "persistence_available": True,
            "durability_verified": bool(current.get("durability_verified")),
        }
    if not _enabled():
        return {
            "status": "disabled",
            "version": DURABLE_RUNTIME_STORAGE_VERSION,
            "adapter": current.get("adapter") or current.get("mode") or "unknown",
            "persistence_available": False,
            "durability_verified": False,
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
    "SQLITE_RESTART_PROBE_VERSION",
    "SQLiteRuntimeAdapter",
    "install_durable_runtime_storage",
]
