from __future__ import annotations

import os
from typing import Any

TRUTHY_VALUES = {"1", "true", "yes", "on", "required"}


def durable_delivery_storage_required() -> bool:
    return os.getenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", "false").strip().lower() in TRUTHY_VALUES


def validate_delivery_persistence(persistence: Any, record_kind: str) -> dict[str, Any]:
    value = persistence if isinstance(persistence, dict) else {}
    required = durable_delivery_storage_required()
    durable = bool(value.get("durable"))
    adapter = str(value.get("adapter") or "unknown")
    ready = durable or not required
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "required": required,
        "durable": durable,
        "adapter": adapter,
        "record_kind": str(record_kind or "delivery_record"),
        "message": (
            f"Durable {record_kind} storage is available."
            if durable
            else (
                f"Durable {record_kind} storage is required for hosted client delivery but is unavailable. Configure DATABASE_URL and verify the Postgres schema before retrying."
                if required
                else f"{record_kind} storage is using the disclosed process-memory fallback."
            )
        ),
    }


def delivery_storage_readiness() -> dict[str, Any]:
    """Return sanitized readiness for every external-delivery record type."""

    from nico import approved_delivery_access as access_store
    from nico import approved_delivery_acknowledgments as acknowledgment_store
    from nico import approved_delivery_receipts as receipt_store

    components = {
        "access_grants": validate_delivery_persistence(access_store._persistence_status(), "access-grant"),
        "delivery_receipts": validate_delivery_persistence(receipt_store._persistence_status(), "delivery-receipt"),
        "client_acknowledgments": validate_delivery_persistence(acknowledgment_store._persistence_status(), "client-acknowledgment"),
    }
    required = durable_delivery_storage_required()
    ready = all(item.get("ready") for item in components.values())
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "durable_storage_required": required,
        "components": components,
        "rule": "Hosted external delivery must not create access grants, return PDFs, or record client acknowledgments when durable delivery storage is required but unavailable.",
    }
