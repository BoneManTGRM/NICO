from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from nico.storage import POSTGRES_SCHEMA, STORE, PostgresAdapter, _with_default_metadata

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
_DEFAULT_SQLITE_PATH = "/data/nico-runtime.sqlite3"
_POSTGRES_URL_KEYS = (
    "DATABASE_URL",
    "DATABASE_PRIVATE_URL",
    "POSTGRES_URL",
    "POSTGRES_PRIVATE_URL",
    "RAILWAY_DATABASE_URL",
    "RAILWAY_POSTGRES_URL",
)


def _enabled() -> bool:
    return os.getenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "false").strip().lower() == "true"


def _clean_url(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


def _resolved_postgres_url() -> tuple[str, str]:
    """Resolve a private Postgres connection without exposing credentials.

    Railway and other hosted environments do not always inject the connection
    under the same variable name. Direct URL aliases are preferred. A standard
    libpq PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE set is also supported.
    Public database URLs are intentionally not selected automatically unless an
    operator explicitly maps one of the supported private aliases.
    """

    for key in _POSTGRES_URL_KEYS:
        value = _clean_url(os.getenv(key, ""))
        if value:
            return value, key

    host = os.getenv("PGHOST", "").strip()
    user = os.getenv("PGUSER", "").strip()
    password = os.getenv("PGPASSWORD", "")
    database = os.getenv("PGDATABASE", "").strip()
    if not (host and user and database):
        return "", ""
    port = os.getenv("PGPORT", "5432").strip() or "5432"
    if not re.fullmatch(r"\d{1,5}", port):
        return "", ""
    credentials = quote(user, safe="")
    if password:
        credentials += ":" + quote(password, safe="")
    query: dict[str, str] = {}
    sslmode = os.getenv("PGSSLMODE", "").strip()
    if sslmode:
        query["sslmode"] = sslmode
    suffix = "?" + urlencode(query) if query else ""
    return f"postgresql://{credentials}@{host}:{port}/{quote(database, safe='')}{suffix}", "PG*"


def _path() -> Path:
    explicit = os.getenv("NICO_SQLITE_PATH", "").strip()
    mount = (
        os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
        or os.getenv("NICO_DURABLE_VOLUME_PATH", "").strip()
    )
    # Docker ships with /data as a safe local default. When Railway provides a
    # mounted-volume path, prefer that path unless an operator deliberately set a
    # different SQLite file. This converts the existing hosted fallback into a
    # deployment-surviving record without falsely treating the container layer as
    # durable.
    if mount and (not explicit or explicit == _DEFAULT_SQLITE_PATH):
        return Path(mount) / "nico-runtime.sqlite3"
    return Path(explicit or _DEFAULT_SQLITE_PATH)


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
        resolved_url, resolved_source = _resolved_postgres_url()
        return {
            "mode": "sqlite",
            "adapter": "sqlite",
            "database_url_configured": bool(resolved_url),
            "database_url_source": resolved_source or "",
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


def _install_resolved_postgres() -> dict[str, Any] | None:
    if getattr(STORE, "disable_postgres", False):
        return None
    database_url, source = _resolved_postgres_url()
    if not database_url:
        return None
    try:
        adapter = PostgresAdapter(database_url)
    except Exception as exc:
        STORE.adapter_error = f"Resolved Postgres connection from {source} failed: {type(exc).__name__}: {exc}"
        return {
            "status": "postgres_unavailable",
            "adapter": "memory",
            "persistence_available": False,
            "database_url_source": source,
        }
    STORE.database_url = database_url
    STORE.adapter = adapter
    STORE.adapter_error = ""
    status = STORE.status()
    return {
        "status": "installed_postgres",
        "adapter": "postgres",
        "persistence_available": bool(status.get("persistence_available")),
        "database_url_source": source,
    }


def install_durable_runtime_storage() -> dict[str, Any]:
    current = STORE.status()
    if bool(current.get("persistence_available")) and current.get("adapter") == "postgres":
        return {
            "status": "already_durable",
            "version": DURABLE_RUNTIME_STORAGE_VERSION,
            "adapter": "postgres",
            "persistence_available": True,
        }

    postgres = _install_resolved_postgres()
    if postgres and postgres.get("persistence_available"):
        return {"version": DURABLE_RUNTIME_STORAGE_VERSION, **postgres}

    current = STORE.status()
    if bool(current.get("persistence_available")) and current.get("adapter") != "memory":
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
            "postgres_resolution": postgres or {"status": "not_configured"},
        }

    database_path = _path()
    adapter = SQLiteRuntimeAdapter(database_path)
    status = adapter.status()
    if not status.get("persistence_available"):
        raise RuntimeError("SQLite runtime storage path is not writable")
    STORE.adapter = adapter
    STORE.adapter_error = ""
    return {
        "status": "installed",
        "version": DURABLE_RUNTIME_STORAGE_VERSION,
        "resolved_sqlite_path": str(database_path),
        "railway_volume_path_used": bool(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip())
        and database_path.parent == Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()),
        "postgres_resolution": postgres or {"status": "not_configured"},
        **status,
    }


__all__ = [
    "DURABLE_RUNTIME_STORAGE_VERSION",
    "SQLiteRuntimeAdapter",
    "_path",
    "_resolved_postgres_url",
    "install_durable_runtime_storage",
]
