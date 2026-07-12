from __future__ import annotations

from typing import Any

from nico.scanner_recovery import ACTIVE_SCANNER_STATUSES, RECOVERY_REQUIRED_STATUS, scanner_is_stale
from nico.storage import STORE, StorageAdapter

SCANNER_RECOVERY_STATUS_SCHEMA = "nico.scanner_recovery_status.v1"
MAX_STATUS_RECORDS = 1000


def scanner_recovery_status(store: StorageAdapter | None = None) -> dict[str, Any]:
    active = store or STORE
    try:
        storage_status = dict(active.status())
    except Exception:
        storage_status = {}
    adapter = str(storage_status.get("adapter") or "unknown")
    durable = bool(storage_status.get("persistence_available"))
    if adapter != "postgres" or not durable:
        return {
            "artifact_schema": SCANNER_RECOVERY_STATUS_SCHEMA,
            "status": "unavailable",
            "clear": False,
            "adapter": adapter,
            "persistence_available": durable,
            "recovery_required": None,
            "stale_active": None,
            "active": None,
            "blockers": ["durable_postgres_required"],
        }

    try:
        records = active.list("scanner_runs")[:MAX_STATUS_RECORDS]
    except Exception:
        return {
            "artifact_schema": SCANNER_RECOVERY_STATUS_SCHEMA,
            "status": "unavailable",
            "clear": False,
            "adapter": adapter,
            "persistence_available": durable,
            "recovery_required": None,
            "stale_active": None,
            "active": None,
            "blockers": ["scanner_recovery_inventory_unavailable"],
        }

    recovery_required = 0
    stale_active = 0
    active_count = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        status = str(record.get("status") or "")
        if status == RECOVERY_REQUIRED_STATUS:
            recovery_required += 1
        if status in ACTIVE_SCANNER_STATUSES:
            active_count += 1
            if scanner_is_stale(record):
                stale_active += 1

    clear = recovery_required == 0 and stale_active == 0
    return {
        "artifact_schema": SCANNER_RECOVERY_STATUS_SCHEMA,
        "status": "clear" if clear else "attention_required",
        "clear": clear,
        "adapter": adapter,
        "persistence_available": durable,
        "recovery_required": recovery_required,
        "stale_active": stale_active,
        "active": active_count,
        "records_examined": len(records),
        "blockers": [],
        "human_review_required": not clear,
        "client_delivery_allowed": False,
    }


__all__ = ["SCANNER_RECOVERY_STATUS_SCHEMA", "scanner_recovery_status"]
