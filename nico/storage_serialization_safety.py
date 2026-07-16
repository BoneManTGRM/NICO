from __future__ import annotations

import json
import math
from typing import Any, Callable

STORAGE_SERIALIZATION_SAFETY_VERSION = "nico.storage_serialization_safety.v1"
_MAX_DEPTH = 96
_METADATA_MARKER = "_nico_cycle_safe_storage_metadata_v1"
_SCAN_MARKER = "_nico_cycle_safe_express_scan_v1"


def _safe_text(value: Any) -> str:
    try:
        return str(value)
    except BaseException:
        return f"<{type(value).__module__}.{type(value).__qualname__}>"


def json_safe_storage_payload(
    value: Any,
    *,
    active_container_ids: set[int] | None = None,
    depth: int = 0,
) -> Any:
    """Return a bounded JSON-safe copy without preserving reference cycles.

    Storage adapters must not fail merely because an evidence provider returned a
    shared or self-referential Python container. Cycles remain explicit in the
    retained evidence rather than being silently discarded or terminating a run.
    """

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"$non_finite_float": _safe_text(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    if depth >= _MAX_DEPTH:
        return {"$truncated": "maximum_storage_depth"}

    active = active_container_ids if active_container_ids is not None else set()
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": "dict"}
        active.add(identity)
        try:
            return {
                _safe_text(key): json_safe_storage_payload(
                    item,
                    active_container_ids=active,
                    depth=depth + 1,
                )
                for key, item in value.items()
            }
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": type(value).__name__}
        active.add(identity)
        try:
            return [
                json_safe_storage_payload(
                    item,
                    active_container_ids=active,
                    depth=depth + 1,
                )
                for item in value
            ]
        finally:
            active.remove(identity)

    if isinstance(value, (set, frozenset)):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": type(value).__name__}
        active.add(identity)
        try:
            normalized = [
                json_safe_storage_payload(
                    item,
                    active_container_ids=active,
                    depth=depth + 1,
                )
                for item in value
            ]
        finally:
            active.remove(identity)
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str),
        )

    return _safe_text(value)


def _safe_metadata(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from nico.storage import utc_now

    normalized = json_safe_storage_payload(payload)
    item = normalized if isinstance(normalized, dict) else {"value": normalized}
    item.setdefault("id", item_id)
    item.setdefault("created_at", utc_now())
    item["updated_at"] = utc_now()
    return item


def _safe_express_scan(scan: dict[str, Any]) -> dict[str, Any]:
    from nico import express_snapshot_pipeline as pipeline
    from nico.scanner_redaction_safety import cycle_safe_redact_payload

    previous: Callable[[dict[str, Any]], dict[str, Any]] = getattr(
        _safe_express_scan,
        "_nico_previous",
        pipeline._safe_scan,
    )
    try:
        selected = previous(scan)
    except (RecursionError, ValueError, TypeError):
        selected = scan if isinstance(scan, dict) else {}
    normalized = cycle_safe_redact_payload(selected)
    return normalized if isinstance(normalized, dict) else {}


def install_storage_serialization_safety() -> dict[str, Any]:
    import nico.durable_runtime_storage as durable
    import nico.express_snapshot_pipeline as pipeline
    import nico.storage as storage

    metadata_installed = False
    current_metadata = storage._with_default_metadata
    if not getattr(current_metadata, _METADATA_MARKER, False):
        setattr(_safe_metadata, _METADATA_MARKER, True)
        setattr(_safe_metadata, "_nico_previous", current_metadata)
        storage._with_default_metadata = _safe_metadata
        durable._with_default_metadata = _safe_metadata
        metadata_installed = True
    else:
        durable._with_default_metadata = current_metadata

    scan_installed = False
    current_scan = pipeline._safe_scan
    if not getattr(current_scan, _SCAN_MARKER, False):
        setattr(_safe_express_scan, _SCAN_MARKER, True)
        setattr(_safe_express_scan, "_nico_previous", current_scan)
        pipeline._safe_scan = _safe_express_scan
        scan_installed = True

    return {
        "status": "installed" if metadata_installed or scan_installed else "already_installed",
        "version": STORAGE_SERIALIZATION_SAFETY_VERSION,
        "storage_metadata_boundary_installed": bool(
            getattr(storage._with_default_metadata, _METADATA_MARKER, False)
        ),
        "sqlite_metadata_boundary_installed": durable._with_default_metadata is storage._with_default_metadata,
        "express_scanner_boundary_installed": bool(
            getattr(pipeline._safe_scan, _SCAN_MARKER, False)
        ),
        "circular_reference_is_terminal": False,
        "maximum_depth": _MAX_DEPTH,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "STORAGE_SERIALIZATION_SAFETY_VERSION",
    "install_storage_serialization_safety",
    "json_safe_storage_payload",
]
