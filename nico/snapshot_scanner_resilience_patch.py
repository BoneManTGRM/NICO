from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any, Callable

from nico.storage import STORE, StorageAdapter, utc_now

SNAPSHOT_SCANNER_RESILIENCE_VERSION = "nico.snapshot_scanner_resilience.v1"
_WORKER_MARKER = "_nico_snapshot_worker_failure_boundary_v1"
_RECOVERY_MARKER = "_nico_snapshot_recovery_v1"


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _terminalize_worker_failure(
    scan_id: str,
    exc: Exception,
    *,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    from nico import scanner_worker as base

    active = _store(store)
    current = deepcopy(base.SCAN_JOBS.get(scan_id) or active.get("scanner_runs", scan_id) or {})
    now_text = utc_now()
    current.update(
        {
            "scan_id": scan_id,
            "status": "failed",
            "current_stage": "worker_failed",
            "completed_at": now_text,
            "updated_at": now_text,
            "active_tool": "",
            "failure_type": type(exc).__name__[:120],
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    base.SCAN_JOBS[scan_id] = current
    active.put("scanner_runs", scan_id, current)
    try:
        active.audit(
            "scanner.snapshot_failed",
            {
                "scan_id": scan_id,
                "run_id": current.get("run_id") or "",
                "snapshot_id": current.get("snapshot_id") or "",
                "snapshot_commit_sha": current.get("snapshot_commit_sha") or "",
                "failure_type": current["failure_type"],
                "stage": "worker_failed",
            },
            customer_id=str(current.get("customer_id") or "default_customer"),
            project_id=str(current.get("project_id") or "default_project"),
        )
    except Exception:
        pass
    return current


def _run_with_failure_boundary(
    original: Callable[[str, dict[str, Any]], Any],
    scan_id: str,
    payload: dict[str, Any],
    *,
    store: StorageAdapter | None = None,
) -> Any:
    try:
        return original(scan_id, payload)
    except Exception as exc:
        _terminalize_worker_failure(scan_id, exc, store=store)
        return None


def _snapshot_bound(record: dict[str, Any]) -> bool:
    return bool(record.get("snapshot_id") and record.get("snapshot_commit_sha"))


def _snapshot_resume_payload(record: dict[str, Any]) -> dict[str, Any]:
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
        "snapshot_id": str(record.get("snapshot_id") or ""),
        "snapshot_commit_sha": str(record.get("snapshot_commit_sha") or ""),
        "draft_pr_creation_allowed": False,
    }


def _resume_snapshot_scanner_run(
    scan_id: str,
    *,
    actor: str,
    store: StorageAdapter | None = None,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> dict[str, Any]:
    from nico import scanner_recovery as recovery
    from nico import scanner_worker as base
    from nico import snapshot_scanner_worker

    active = recovery._store(store)
    normalized_scan_id = str(scan_id or "").strip()
    current = active.get("scanner_runs", normalized_scan_id)
    if not isinstance(current, dict):
        return {
            "status": "not_found",
            "code": "scanner_run_not_found",
            "scan_id": normalized_scan_id,
        }

    current_status = str(current.get("status") or "unknown")
    if current_status in recovery.ACTIVE_SCANNER_STATUSES | recovery.TERMINAL_SCANNER_STATUSES:
        return {
            "status": current_status,
            "idempotent_reuse": True,
            "scan": recovery._safe_scan_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }
    if current_status != recovery.RECOVERY_REQUIRED_STATUS:
        return {
            "status": "blocked",
            "code": "scanner_not_recoverable",
            "scan": recovery._safe_scan_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }
    if not _snapshot_bound(current):
        return {
            "status": "blocked",
            "code": "snapshot_identity_missing",
            "scan": recovery._safe_scan_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    valid, reason = recovery._valid_resume_source(current)
    if not valid:
        return {
            "status": "blocked",
            "code": reason,
            "scan": recovery._safe_scan_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    existing_recovery = current.get("recovery") if isinstance(current.get("recovery"), dict) else {}
    now_text = utc_now()
    attempt = int(existing_recovery.get("attempt") or 0) + 1
    claimed = recovery.atomic_scanner_transition(
        normalized_scan_id,
        {recovery.RECOVERY_REQUIRED_STATUS},
        "queued",
        {
            "queued_at": now_text,
            "completed_at": None,
            "updated_at": now_text,
            "active_tool": "",
            "snapshot_id": current.get("snapshot_id"),
            "snapshot_commit_sha": current.get("snapshot_commit_sha"),
            "recovery": {
                "artifact_schema": recovery.SCANNER_RECOVERY_SCHEMA,
                "state": "resume_claimed",
                "reason": existing_recovery.get("reason") or "stale_process_local_execution",
                "previous_status": recovery.RECOVERY_REQUIRED_STATUS,
                "detected_at": existing_recovery.get("detected_at"),
                "resume_requested_at": now_text,
                "resume_requested_by": str(actor or "operator")[:120],
                "resume_allowed": False,
                "automatic_resume": False,
                "attempt": attempt,
                "snapshot_bound": True,
                "same_scan_id": True,
                "same_run_id": True,
            },
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        store=active,
    )
    if not claimed:
        latest = active.get("scanner_runs", normalized_scan_id) or current
        latest_status = str(latest.get("status") or "unknown")
        if latest_status in recovery.ACTIVE_SCANNER_STATUSES | recovery.TERMINAL_SCANNER_STATUSES:
            return {
                "status": latest_status,
                "idempotent_reuse": True,
                "scan": recovery._safe_scan_summary(latest),
                "automatic_resume": False,
                "client_delivery_allowed": False,
            }
        return {
            "status": "blocked",
            "code": "scanner_resume_claim_failed",
            "scan": recovery._safe_scan_summary(latest),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    payload = _snapshot_resume_payload(claimed)
    try:
        base.SCAN_JOBS[normalized_scan_id] = deepcopy(claimed)
        thread = thread_factory(
            target=snapshot_scanner_worker._run_snapshot_scan,
            args=(normalized_scan_id, payload),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        error_type = type(exc).__name__[:120]
        failed = recovery.atomic_scanner_transition(
            normalized_scan_id,
            {"queued"},
            recovery.RECOVERY_REQUIRED_STATUS,
            {
                "updated_at": utc_now(),
                "recovery": {
                    "artifact_schema": recovery.SCANNER_RECOVERY_SCHEMA,
                    "state": recovery.RECOVERY_REQUIRED_STATUS,
                    "reason": "resume_thread_start_failed",
                    "previous_status": "queued",
                    "detected_at": now_text,
                    "resume_allowed": True,
                    "automatic_resume": False,
                    "attempt": attempt,
                    "error_type": error_type,
                    "snapshot_bound": True,
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
            "scan": recovery._safe_scan_summary(failed or claimed),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    try:
        active.audit(
            "scanner.snapshot_resume_claimed",
            {
                "scan_id": normalized_scan_id,
                "run_id": payload["run_id"],
                "snapshot_id": payload["snapshot_id"],
                "snapshot_commit_sha": payload["snapshot_commit_sha"],
                "attempt": attempt,
                "actor": str(actor or "operator")[:120],
            },
            customer_id=payload["customer_id"],
            project_id=payload["project_id"],
        )
    except Exception:
        pass
    return {
        "status": "queued",
        "idempotent_reuse": False,
        "scan": recovery._safe_scan_summary(claimed),
        "resume": {
            "same_scan_id": True,
            "same_run_id": True,
            "same_snapshot_id": True,
            "same_snapshot_commit_sha": True,
            "attempt": attempt,
            "requested_at": now_text,
            "requested_by": str(actor or "operator")[:120],
        },
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_snapshot_scanner_resilience() -> dict[str, Any]:
    from nico import scanner_recovery as recovery
    from nico import snapshot_scanner_worker

    current_worker = snapshot_scanner_worker._run_snapshot_scan
    if not getattr(current_worker, _WORKER_MARKER, False):
        def guarded_worker(scan_id: str, payload: dict[str, Any]) -> Any:
            return _run_with_failure_boundary(
                current_worker,
                scan_id,
                payload,
                store=snapshot_scanner_worker.STORE,
            )

        setattr(guarded_worker, _WORKER_MARKER, True)
        setattr(guarded_worker, "_nico_previous", current_worker)
        snapshot_scanner_worker._run_snapshot_scan = guarded_worker

    current_recovery = recovery.resume_interrupted_scanner_run
    if not getattr(current_recovery, _RECOVERY_MARKER, False):
        def snapshot_aware_recovery(
            scan_id: str,
            *,
            actor: str,
            store: StorageAdapter | None = None,
            thread_factory: Callable[..., threading.Thread] = threading.Thread,
        ) -> dict[str, Any]:
            active = recovery._store(store)
            record = active.get("scanner_runs", str(scan_id or "").strip())
            if isinstance(record, dict) and _snapshot_bound(record):
                return _resume_snapshot_scanner_run(
                    scan_id,
                    actor=actor,
                    store=active,
                    thread_factory=thread_factory,
                )
            return current_recovery(
                scan_id,
                actor=actor,
                store=active,
                thread_factory=thread_factory,
            )

        setattr(snapshot_aware_recovery, _RECOVERY_MARKER, True)
        setattr(snapshot_aware_recovery, "_nico_previous", current_recovery)
        recovery.resume_interrupted_scanner_run = snapshot_aware_recovery

    return {
        "status": "installed",
        "version": SNAPSHOT_SCANNER_RESILIENCE_VERSION,
        "snapshot_resume_uses_snapshot_worker": True,
        "same_scan_id_preserved": True,
        "same_run_id_preserved": True,
        "same_snapshot_identity_preserved": True,
        "top_level_worker_failure_is_terminal": True,
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "SNAPSHOT_SCANNER_RESILIENCE_VERSION",
    "install_snapshot_scanner_resilience",
]
