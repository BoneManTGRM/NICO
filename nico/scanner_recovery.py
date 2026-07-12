from __future__ import annotations

import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from nico.admin_security import require_admin_write
from nico.storage import STORE, StorageAdapter, utc_now

SCANNER_RECOVERY_SCHEMA = "nico.scanner_recovery.v1"
SCANNER_RECOVERY_ROUTE = ("GET", "/operations/recovery")
SCANNER_RESUME_ROUTE = ("POST", "/operations/recovery/scanner/{scan_id}/resume")
REQUIRED_SCANNER_RECOVERY_ROUTES = {
    SCANNER_RECOVERY_ROUTE,
    SCANNER_RESUME_ROUTE,
}
REQUIRED_SCANNER_RECOVERY_ROUTE_NAMES = {
    "GET /operations/recovery",
    "POST /operations/recovery/scanner/{scan_id}/resume",
}
ACTIVE_SCANNER_STATUSES = {"queued", "running"}
RECOVERY_REQUIRED_STATUS = "recovery_required"
TERMINAL_SCANNER_STATUSES = {"complete", "failed", "error", "blocked", "cancelled"}
DEFAULT_STALE_SECONDS = 600
MAX_RECONCILE_RECORDS = 1000
MAX_INVENTORY_LIMIT = 500

_MEMORY_TRANSITION_LOCK = threading.Lock()
_STARTUP_RESULT: dict[str, Any] | None = None


class ScannerResumeRequest(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=120)


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def configured_stale_seconds() -> int:
    raw = os.getenv("NICO_SCANNER_RECOVERY_STALE_SECONDS", str(DEFAULT_STALE_SECONDS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_STALE_SECONDS
    return max(60, min(value, 86400))


def scanner_age_seconds(record: dict[str, Any], *, now: datetime | None = None) -> float | None:
    observed = _parse_datetime(record.get("updated_at") or record.get("created_at"))
    if observed is None:
        return None
    current = now or _now_datetime()
    return max(0.0, (current - observed).total_seconds())


def scanner_is_stale(
    record: dict[str, Any],
    *,
    stale_seconds: int | None = None,
    now: datetime | None = None,
) -> bool:
    if str(record.get("status") or "") not in ACTIVE_SCANNER_STATUSES:
        return False
    age = scanner_age_seconds(record, now=now)
    return age is None or age >= float(stale_seconds or configured_stale_seconds())


def _safe_scan_summary(record: dict[str, Any]) -> dict[str, Any]:
    recovery = record.get("recovery") if isinstance(record.get("recovery"), dict) else {}
    return {
        "scan_id": str(record.get("scan_id") or record.get("id") or ""),
        "run_id": str(record.get("run_id") or ""),
        "customer_id": str(record.get("customer_id") or "default_customer"),
        "project_id": str(record.get("project_id") or "default_project"),
        "repository": str(record.get("repository") or ""),
        "status": str(record.get("status") or "unknown"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "completed_at": record.get("completed_at"),
        "tools_requested": [str(item)[:80] for item in (record.get("tools_requested") or [])[:40]],
        "recovery": {
            "state": recovery.get("state") or "",
            "reason": recovery.get("reason") or "",
            "previous_status": recovery.get("previous_status") or "",
            "detected_at": recovery.get("detected_at"),
            "resume_requested_at": recovery.get("resume_requested_at"),
            "resume_requested_by": recovery.get("resume_requested_by") or "",
            "attempt": int(recovery.get("attempt") or 0),
            "resume_allowed": bool(recovery.get("resume_allowed")),
            "automatic_resume": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _adapter_name(active: StorageAdapter) -> str:
    try:
        return str(active.status().get("adapter") or "unknown")
    except Exception:
        return "unknown"


def _persistence_available(active: StorageAdapter) -> bool:
    try:
        return bool(active.status().get("persistence_available"))
    except Exception:
        return False


def _normalize_postgres_row(adapter: Any, row: dict[str, Any]) -> dict[str, Any]:
    normalizer = getattr(adapter, "_normalize_jsonb", None)
    if callable(normalizer):
        return normalizer("scanner_runs", row)
    payload = dict(row.get("payload") or {})
    payload.update(
        {
            "scan_id": row.get("scan_id"),
            "customer_id": row.get("customer_id"),
            "project_id": row.get("project_id"),
            "status": row.get("status"),
            "created_at": str(row.get("created_at")),
            "updated_at": str(row.get("updated_at")),
        }
    )
    return payload


def _postgres_atomic_transition(
    active: StorageAdapter,
    scan_id: str,
    expected_statuses: set[str],
    new_status: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    adapter = getattr(active, "adapter", None)
    query = getattr(adapter, "_query", None)
    jsonb = getattr(adapter, "_jsonb", None)
    if not callable(query) or jsonb is None:
        raise RuntimeError("Postgres scanner transition capability is unavailable")
    expected = sorted({str(item) for item in expected_statuses if str(item)})
    if not expected:
        return None
    merged_patch = deepcopy(patch)
    merged_patch["status"] = new_status
    merged_patch["updated_at"] = patch.get("updated_at") or utc_now()
    rows = query(
        """
        UPDATE scanner_runs
        SET status=%s,
            payload=payload || %s,
            updated_at=%s
        WHERE scan_id=%s
          AND status = ANY(%s)
        RETURNING *
        """,
        (
            new_status,
            jsonb(merged_patch),
            merged_patch["updated_at"],
            scan_id,
            expected,
        ),
    )
    if not rows:
        return None
    return _normalize_postgres_row(adapter, rows[0])


def atomic_scanner_transition(
    scan_id: str,
    expected_statuses: set[str],
    new_status: str,
    patch: dict[str, Any],
    *,
    store: StorageAdapter | None = None,
) -> dict[str, Any] | None:
    active = _store(store)
    if _adapter_name(active) == "postgres" and _persistence_available(active):
        return _postgres_atomic_transition(active, scan_id, expected_statuses, new_status, patch)

    with _MEMORY_TRANSITION_LOCK:
        current = active.get("scanner_runs", scan_id)
        if not isinstance(current, dict):
            return None
        if str(current.get("status") or "") not in expected_statuses:
            return None
        updated = deepcopy(current)
        updated.update(deepcopy(patch))
        updated["scan_id"] = scan_id
        updated["status"] = new_status
        updated["updated_at"] = patch.get("updated_at") or utc_now()
        return active.put("scanner_runs", scan_id, updated)


def _recovery_patch(
    record: dict[str, Any],
    *,
    now_text: str,
    age_seconds: float | None,
) -> dict[str, Any]:
    previous = str(record.get("status") or "unknown")
    existing = record.get("recovery") if isinstance(record.get("recovery"), dict) else {}
    return {
        "recovery_required_at": now_text,
        "updated_at": now_text,
        "recovery": {
            "artifact_schema": SCANNER_RECOVERY_SCHEMA,
            "state": RECOVERY_REQUIRED_STATUS,
            "reason": "stale_process_local_execution",
            "previous_status": previous,
            "detected_at": now_text,
            "stale_age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
            "resume_allowed": True,
            "automatic_resume": False,
            "attempt": int(existing.get("attempt") or 0),
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def reconcile_interrupted_scanner_runs(
    *,
    store: StorageAdapter | None = None,
    stale_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active = _store(store)
    threshold = max(60, min(int(stale_seconds or configured_stale_seconds()), 86400))
    current = now or _now_datetime()
    now_text = current.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    adapter = _adapter_name(active)
    durable = _persistence_available(active)
    if adapter != "postgres" or not durable:
        return {
            "artifact_schema": SCANNER_RECOVERY_SCHEMA,
            "status": "blocked",
            "adapter": adapter,
            "persistence_available": durable,
            "stale_seconds": threshold,
            "examined": 0,
            "reconciled": 0,
            "fresh_active": 0,
            "recovery_required": 0,
            "blockers": ["durable_postgres_required"],
            "automatic_resume": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    records = active.list("scanner_runs")[:MAX_RECONCILE_RECORDS]
    reconciled: list[str] = []
    fresh_active = 0
    transition_conflicts = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        status = str(record.get("status") or "")
        if status not in ACTIVE_SCANNER_STATUSES:
            continue
        if not scanner_is_stale(record, stale_seconds=threshold, now=current):
            fresh_active += 1
            continue
        scan_id = str(record.get("scan_id") or record.get("id") or "")
        if not scan_id:
            continue
        age = scanner_age_seconds(record, now=current)
        transitioned = atomic_scanner_transition(
            scan_id,
            {status},
            RECOVERY_REQUIRED_STATUS,
            _recovery_patch(record, now_text=now_text, age_seconds=age),
            store=active,
        )
        if transitioned:
            reconciled.append(scan_id)
            try:
                active.audit(
                    "scanner.recovery_required",
                    {
                        "scan_id": scan_id,
                        "previous_status": status,
                        "stale_age_seconds": round(age, 3) if age is not None else None,
                    },
                    customer_id=str(record.get("customer_id") or "default_customer"),
                    project_id=str(record.get("project_id") or "default_project"),
                )
            except Exception:
                pass
        else:
            transition_conflicts += 1

    recovery_required = sum(
        1
        for record in active.list("scanner_runs")[:MAX_RECONCILE_RECORDS]
        if isinstance(record, dict) and str(record.get("status") or "") == RECOVERY_REQUIRED_STATUS
    )
    return {
        "artifact_schema": SCANNER_RECOVERY_SCHEMA,
        "status": "attention_required" if recovery_required else "clear",
        "adapter": adapter,
        "persistence_available": durable,
        "stale_seconds": threshold,
        "examined": len(records),
        "reconciled": len(reconciled),
        "reconciled_scan_ids": reconciled[:100],
        "fresh_active": fresh_active,
        "transition_conflicts": transition_conflicts,
        "recovery_required": recovery_required,
        "blockers": [],
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def scanner_recovery_inventory(
    *,
    store: StorageAdapter | None = None,
    refresh: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    active = _store(store)
    bounded_limit = max(1, min(int(limit), MAX_INVENTORY_LIMIT))
    reconciliation = (
        reconcile_interrupted_scanner_runs(store=active)
        if refresh
        else dict(_STARTUP_RESULT or {})
    )
    records = active.list("scanner_runs")[:MAX_RECONCILE_RECORDS]
    recovery_items = [
        _safe_scan_summary(record)
        for record in records
        if isinstance(record, dict)
        and str(record.get("status") or "") == RECOVERY_REQUIRED_STATUS
    ]
    active_items = [
        _safe_scan_summary(record)
        for record in records
        if isinstance(record, dict)
        and str(record.get("status") or "") in ACTIVE_SCANNER_STATUSES
    ]
    recovery_items.sort(key=lambda item: str(item.get("updated_at") or ""))
    active_items.sort(key=lambda item: str(item.get("updated_at") or ""))
    return {
        "artifact_schema": SCANNER_RECOVERY_SCHEMA,
        "status": "attention_required" if recovery_items else "clear",
        "generated_at": utc_now(),
        "adapter": _adapter_name(active),
        "persistence_available": _persistence_available(active),
        "stale_seconds": configured_stale_seconds(),
        "counts": {
            "recovery_required": len(recovery_items),
            "active": len(active_items),
            "total_scanner_records_examined": len(records),
        },
        "recovery_required": recovery_items[:bounded_limit],
        "active": active_items[:bounded_limit],
        "limit": bounded_limit,
        "reconciliation": reconciliation,
        "operator_action": "Review each interrupted scanner record, then resume only the intended run through the authenticated same-ID resume endpoint.",
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _resume_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "scan_id": str(record.get("scan_id") or record.get("id") or ""),
        "run_id": str(record.get("run_id") or ""),
        "repository": str(record.get("repository") or ""),
        "customer_id": str(record.get("customer_id") or "default_customer"),
        "project_id": str(record.get("project_id") or "default_project"),
        "authorized": True,
        "authorized_by": str(record.get("authorized_by") or ""),
        "authorization_scope": str(record.get("authorization_scope") or ""),
        "tools": [str(item) for item in (record.get("tools_requested") or [])[:40]],
        "draft_pr_creation_allowed": bool(record.get("draft_pr_creation_allowed", False)),
    }


def _valid_resume_source(record: dict[str, Any]) -> tuple[bool, str]:
    if not str(record.get("repository") or "").strip():
        return False, "repository_missing"
    if not str(record.get("authorized_by") or "").strip():
        return False, "authorized_by_missing"
    if not str(record.get("authorization_scope") or "").strip():
        return False, "authorization_scope_missing"
    return True, ""


def resume_interrupted_scanner_run(
    scan_id: str,
    *,
    actor: str,
    store: StorageAdapter | None = None,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> dict[str, Any]:
    active = _store(store)
    normalized_scan_id = str(scan_id or "").strip()
    if not normalized_scan_id.startswith("scan_"):
        return {
            "status": "not_found",
            "code": "scanner_run_not_found",
            "scan_id": normalized_scan_id,
        }
    current = active.get("scanner_runs", normalized_scan_id)
    if not isinstance(current, dict):
        return {
            "status": "not_found",
            "code": "scanner_run_not_found",
            "scan_id": normalized_scan_id,
        }
    current_status = str(current.get("status") or "unknown")
    if current_status in ACTIVE_SCANNER_STATUSES | TERMINAL_SCANNER_STATUSES:
        return {
            "status": current_status,
            "idempotent_reuse": True,
            "scan": _safe_scan_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }
    if current_status != RECOVERY_REQUIRED_STATUS:
        return {
            "status": "blocked",
            "code": "scanner_not_recoverable",
            "scan": _safe_scan_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }
    valid, reason = _valid_resume_source(current)
    if not valid:
        return {
            "status": "blocked",
            "code": reason,
            "scan": _safe_scan_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    existing_recovery = current.get("recovery") if isinstance(current.get("recovery"), dict) else {}
    now_text = utc_now()
    attempt = int(existing_recovery.get("attempt") or 0) + 1
    claimed = atomic_scanner_transition(
        normalized_scan_id,
        {RECOVERY_REQUIRED_STATUS},
        "queued",
        {
            "queued_at": now_text,
            "completed_at": None,
            "updated_at": now_text,
            "recovery": {
                "artifact_schema": SCANNER_RECOVERY_SCHEMA,
                "state": "resume_claimed",
                "reason": existing_recovery.get("reason") or "stale_process_local_execution",
                "previous_status": RECOVERY_REQUIRED_STATUS,
                "detected_at": existing_recovery.get("detected_at"),
                "resume_requested_at": now_text,
                "resume_requested_by": str(actor or "operator")[:120],
                "resume_allowed": False,
                "automatic_resume": False,
                "attempt": attempt,
            },
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        store=active,
    )
    if not claimed:
        latest = active.get("scanner_runs", normalized_scan_id) or current
        latest_status = str(latest.get("status") or "unknown")
        if latest_status in ACTIVE_SCANNER_STATUSES | TERMINAL_SCANNER_STATUSES:
            return {
                "status": latest_status,
                "idempotent_reuse": True,
                "scan": _safe_scan_summary(latest),
                "automatic_resume": False,
                "client_delivery_allowed": False,
            }
        return {
            "status": "blocked",
            "code": "scanner_resume_claim_failed",
            "scan": _safe_scan_summary(latest),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    payload = _resume_payload(claimed)
    try:
        from nico import scanner_worker

        scanner_worker.SCAN_JOBS[normalized_scan_id] = deepcopy(claimed)
        thread = thread_factory(
            target=scanner_worker._run_scan,
            args=(normalized_scan_id, payload),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        error_type = type(exc).__name__[:120]
        failed = atomic_scanner_transition(
            normalized_scan_id,
            {"queued"},
            RECOVERY_REQUIRED_STATUS,
            {
                "updated_at": utc_now(),
                "recovery": {
                    "artifact_schema": SCANNER_RECOVERY_SCHEMA,
                    "state": RECOVERY_REQUIRED_STATUS,
                    "reason": "resume_thread_start_failed",
                    "previous_status": "queued",
                    "detected_at": now_text,
                    "resume_allowed": True,
                    "automatic_resume": False,
                    "attempt": attempt,
                    "error_type": error_type,
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            store=active,
        )
        return {
            "status": "blocked",
            "code": "scanner_resume_start_failed",
            "error_type": error_type,
            "scan": _safe_scan_summary(failed or claimed),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    try:
        active.audit(
            "scanner.resume_claimed",
            {
                "scan_id": normalized_scan_id,
                "attempt": attempt,
                "actor": str(actor or "operator")[:120],
            },
            customer_id=str(claimed.get("customer_id") or "default_customer"),
            project_id=str(claimed.get("project_id") or "default_project"),
        )
    except Exception:
        pass
    return {
        "status": "queued",
        "idempotent_reuse": False,
        "scan": _safe_scan_summary(claimed),
        "resume": {
            "same_scan_id": True,
            "attempt": attempt,
            "requested_at": now_text,
            "requested_by": str(actor or "operator")[:120],
        },
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _require_operator(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "status": "blocked",
            "code": "operator_authentication_required",
            "message": "Operator authentication is required for scanner recovery actions.",
            "admin_write": status,
        },
    )


def scanner_recovery_inventory_response(
    refresh: bool = False,
    limit: int = 200,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    if limit < 1 or limit > MAX_INVENTORY_LIMIT:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "blocked",
                "code": "invalid_recovery_limit",
                "message": f"limit must be between 1 and {MAX_INVENTORY_LIMIT}.",
            },
        )
    return scanner_recovery_inventory(refresh=refresh, limit=limit)


def scanner_recovery_resume_response(
    scan_id: str,
    req: ScannerResumeRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    result = resume_interrupted_scanner_run(scan_id, actor=req.actor)
    if result.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail={
                "status": "not_found",
                "code": result.get("code") or "scanner_run_not_found",
                "message": "Scanner run not found.",
            },
        )
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "blocked",
                "code": result.get("code") or "scanner_resume_blocked",
                "message": "Scanner resume was blocked by recovery-state or authorization validation.",
                "error_type": result.get("error_type"),
            },
        )
    return result


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def install_scanner_recovery(target: FastAPI) -> dict[str, Any]:
    global _STARTUP_RESULT
    existing = _route_pairs(target)
    if SCANNER_RECOVERY_ROUTE not in existing:
        target.get("/operations/recovery", tags=["operations"])(
            scanner_recovery_inventory_response
        )
    if SCANNER_RESUME_ROUTE not in existing:
        target.post(
            "/operations/recovery/scanner/{scan_id}/resume",
            tags=["operations"],
        )(scanner_recovery_resume_response)
    target.openapi_schema = None

    from nico.operations_readiness import REQUIRED_OPERATION_ROUTES

    REQUIRED_OPERATION_ROUTES.update(REQUIRED_SCANNER_RECOVERY_ROUTE_NAMES)
    _STARTUP_RESULT = reconcile_interrupted_scanner_runs()
    missing = REQUIRED_SCANNER_RECOVERY_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(
            f"Scanner recovery route registration incomplete; missing={sorted(missing)}"
        )
    return {
        "installed": True,
        "routes": sorted(REQUIRED_SCANNER_RECOVERY_ROUTE_NAMES),
        "routes_reused": all(route in existing for route in REQUIRED_SCANNER_RECOVERY_ROUTES),
        "startup_reconciliation": dict(_STARTUP_RESULT),
        "automatic_resume": False,
    }


__all__ = [
    "SCANNER_RECOVERY_SCHEMA",
    "SCANNER_RECOVERY_ROUTE",
    "SCANNER_RESUME_ROUTE",
    "REQUIRED_SCANNER_RECOVERY_ROUTES",
    "REQUIRED_SCANNER_RECOVERY_ROUTE_NAMES",
    "ACTIVE_SCANNER_STATUSES",
    "RECOVERY_REQUIRED_STATUS",
    "TERMINAL_SCANNER_STATUSES",
    "ScannerResumeRequest",
    "configured_stale_seconds",
    "scanner_age_seconds",
    "scanner_is_stale",
    "atomic_scanner_transition",
    "reconcile_interrupted_scanner_runs",
    "scanner_recovery_inventory",
    "resume_interrupted_scanner_run",
    "scanner_recovery_inventory_response",
    "scanner_recovery_resume_response",
    "install_scanner_recovery",
]
