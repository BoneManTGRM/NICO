from __future__ import annotations

import json
import threading
from copy import deepcopy
from typing import Any, Iterable

from nico import durable_runtime_storage
from nico import storage
from nico.storage import utc_now

RUNTIME_HEARTBEAT_ATOMIC_VERSION = "nico.runtime_heartbeat_atomic.v1"
_ACTIVE_DEFAULT = {"queued", "running", "starting", "pending"}
_MEMORY_LOCK = threading.RLock()
_PATCH_MARKER = "_nico_atomic_heartbeat_v1"


def _active_status(current: dict[str, Any], active_statuses: Iterable[str]) -> bool:
    allowed = {str(item).lower() for item in active_statuses}
    return str(current.get("status") or "").lower() in allowed


def _merge_heartbeat(
    current: dict[str, Any],
    patch: dict[str, Any],
    *,
    nested_key: str | None,
) -> dict[str, Any]:
    updated = deepcopy(current)
    now_text = str(patch.get("heartbeat_at") or utc_now())
    nested = updated.get(nested_key) if nested_key and isinstance(updated.get(nested_key), dict) else {}
    sequence = max(
        int(updated.get("heartbeat_sequence") or 0),
        int(nested.get("heartbeat_sequence") or 0),
    ) + 1
    bounded_patch = {
        str(key)[:80]: value
        for key, value in patch.items()
        if isinstance(value, (str, int, float, bool, type(None)))
    }
    bounded_patch["heartbeat_at"] = now_text
    bounded_patch["heartbeat_sequence"] = sequence
    bounded_patch["updated_at"] = now_text
    updated.update(bounded_patch)
    updated["heartbeat_sequence"] = sequence
    updated["heartbeat_at"] = now_text
    updated["updated_at"] = now_text
    if nested_key:
        nested_response = deepcopy(nested)
        nested_response.update(bounded_patch)
        nested_response["heartbeat_sequence"] = sequence
        nested_response["heartbeat_at"] = now_text
        nested_response["updated_at"] = now_text
        nested_response.setdefault("human_review_required", True)
        nested_response["client_ready"] = False
        updated[nested_key] = nested_response
    updated.setdefault("human_review_required", True)
    updated["client_ready"] = False
    return updated


def _memory_patch_heartbeat(
    self: storage.MemoryAdapter,
    table: str,
    item_id: str,
    *,
    patch: dict[str, Any],
    active_statuses: Iterable[str] = _ACTIVE_DEFAULT,
    nested_key: str | None = None,
) -> dict[str, Any] | None:
    with _MEMORY_LOCK:
        current = deepcopy(self._tables.get(table, {}).get(item_id) or {})
        if not current or not _active_status(current, active_statuses):
            return None
        updated = _merge_heartbeat(current, patch, nested_key=nested_key)
        updated.setdefault("id", item_id)
        updated.setdefault("created_at", current.get("created_at") or utc_now())
        self._tables.setdefault(table, {})[item_id] = deepcopy(updated)
        return deepcopy(updated)


def _sqlite_patch_heartbeat(
    self: durable_runtime_storage.SQLiteRuntimeAdapter,
    table: str,
    item_id: str,
    *,
    patch: dict[str, Any],
    active_statuses: Iterable[str] = _ACTIVE_DEFAULT,
    nested_key: str | None = None,
) -> dict[str, Any] | None:
    with self._lock, self._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT payload FROM nico_records WHERE table_name=? AND item_id=?",
            (table, item_id),
        ).fetchone()
        if row is None:
            connection.rollback()
            return None
        current = json.loads(str(row["payload"]))
        if not isinstance(current, dict) or not _active_status(current, active_statuses):
            connection.rollback()
            return None
        updated = _merge_heartbeat(current, patch, nested_key=nested_key)
        serialized = json.dumps(updated, sort_keys=True, separators=(",", ":"), default=str)
        connection.execute(
            """
            UPDATE nico_records
            SET customer_id=?, project_id=?, created_at=?, updated_at=?, payload=?
            WHERE table_name=? AND item_id=?
            """,
            (
                str(updated.get("customer_id")) if updated.get("customer_id") is not None else None,
                str(updated.get("project_id")) if updated.get("project_id") is not None else None,
                str(updated.get("created_at") or ""),
                str(updated.get("updated_at") or ""),
                serialized,
                table,
                item_id,
            ),
        )
        connection.commit()
        return deepcopy(updated)


def _postgres_patch_heartbeat(
    self: storage.PostgresAdapter,
    table: str,
    item_id: str,
    *,
    patch: dict[str, Any],
    active_statuses: Iterable[str] = _ACTIVE_DEFAULT,
    nested_key: str | None = None,
) -> dict[str, Any] | None:
    if table not in {"assessment_runs", "scanner_runs"}:
        raise ValueError(f"Atomic heartbeat table is unsupported: {table}")
    db_table, id_column = storage.JSONB_TABLE_MAP[table]
    with self._connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {db_table} WHERE {id_column}=%s FOR UPDATE",
                (item_id,),
            )
            row = cursor.fetchone()
            if not row:
                connection.rollback()
                return None
            current = self._normalize_jsonb(table, row)
            if not _active_status(current, active_statuses):
                connection.rollback()
                return None
            updated = _merge_heartbeat(current, patch, nested_key=nested_key)
            if table == "assessment_runs":
                cursor.execute(
                    "UPDATE assessment_runs SET status=%s, payload=%s WHERE run_id=%s",
                    (str(updated.get("status") or "running"), self._jsonb(updated), item_id),
                )
            else:
                cursor.execute(
                    "UPDATE scanner_runs SET status=%s, payload=%s, updated_at=%s WHERE scan_id=%s",
                    (
                        str(updated.get("status") or "running"),
                        self._jsonb(updated),
                        updated.get("updated_at"),
                        item_id,
                    ),
                )
        connection.commit()
    return deepcopy(updated)


def _storage_patch_heartbeat(
    self: storage.Storage,
    table: str,
    item_id: str,
    *,
    patch: dict[str, Any],
    active_statuses: Iterable[str] = _ACTIVE_DEFAULT,
    nested_key: str | None = None,
) -> dict[str, Any] | None:
    method = getattr(self.adapter, "patch_heartbeat", None)
    if not callable(method):
        raise RuntimeError("Configured storage adapter does not support atomic heartbeat writes")
    return method(
        table,
        item_id,
        patch=patch,
        active_statuses=active_statuses,
        nested_key=nested_key,
    )


def install_runtime_heartbeat_atomic_patch() -> dict[str, Any]:
    classes = (
        (storage.MemoryAdapter, _memory_patch_heartbeat),
        (storage.PostgresAdapter, _postgres_patch_heartbeat),
        (durable_runtime_storage.SQLiteRuntimeAdapter, _sqlite_patch_heartbeat),
        (storage.Storage, _storage_patch_heartbeat),
    )
    installed = 0
    for cls, method in classes:
        current = getattr(cls, "patch_heartbeat", None)
        if getattr(current, _PATCH_MARKER, False):
            continue
        setattr(method, _PATCH_MARKER, True)
        setattr(cls, "patch_heartbeat", method)
        installed += 1
    return {
        "status": "installed" if installed else "already_installed",
        "version": RUNTIME_HEARTBEAT_ATOMIC_VERSION,
        "classes_patched": installed,
        "compare_status_before_write": True,
        "terminal_state_can_be_reopened": False,
        "stage_payload_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "RUNTIME_HEARTBEAT_ATOMIC_VERSION",
    "install_runtime_heartbeat_atomic_patch",
]
