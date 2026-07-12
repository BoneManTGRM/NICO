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

ASSESSMENT_RECOVERY_SCHEMA = "nico.assessment_recovery.v1"
ASSESSMENT_RECOVERY_INVENTORY_ROUTE = ("GET", "/operations/recovery/assessments")
ASSESSMENT_RECOVERY_RESUME_ROUTE = (
    "POST",
    "/operations/recovery/assessment/{run_id}/resume",
)
REQUIRED_ASSESSMENT_RECOVERY_ROUTES = {
    ASSESSMENT_RECOVERY_INVENTORY_ROUTE,
    ASSESSMENT_RECOVERY_RESUME_ROUTE,
}
REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES = {
    "GET /operations/recovery/assessments",
    "POST /operations/recovery/assessment/{run_id}/resume",
}
SUPPORTED_WORKFLOWS = {"mid_assessment", "full_assessment"}
ACTIVE_ASSESSMENT_STATUSES = {"running", "resuming", "planned"}
RECOVERY_REQUIRED_STATUS = "recovery_required"
TERMINAL_ASSESSMENT_STATUSES = {
    "complete",
    "failed",
    "blocked",
    "cancelled",
    "approved",
    "delivered",
}
DEFAULT_ASSESSMENT_STALE_SECONDS = 900
MAX_RECONCILE_RECORDS = 1000
MAX_INVENTORY_LIMIT = 500

_MEMORY_TRANSITION_LOCK = threading.Lock()
_STARTUP_RESULT: dict[str, Any] | None = None


class AssessmentResumeRequest(BaseModel):
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


def configured_assessment_stale_seconds() -> int:
    raw = os.getenv(
        "NICO_ASSESSMENT_RECOVERY_STALE_SECONDS",
        str(DEFAULT_ASSESSMENT_STALE_SECONDS),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_ASSESSMENT_STALE_SECONDS
    return max(60, min(value, 86400))


def assessment_age_seconds(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
) -> float | None:
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    checkpoint = (
        response.get("execution_checkpoint")
        if isinstance(response.get("execution_checkpoint"), dict)
        else record.get("execution_checkpoint")
        if isinstance(record.get("execution_checkpoint"), dict)
        else {}
    )
    observed = _parse_datetime(
        checkpoint.get("heartbeat_at")
        or response.get("execution_heartbeat_at")
        or record.get("updated_at")
        or record.get("created_at")
    )
    if observed is None:
        return None
    current = now or _now_datetime()
    return max(0.0, (current - observed).total_seconds())


def assessment_is_stale(
    record: dict[str, Any],
    *,
    stale_seconds: int | None = None,
    now: datetime | None = None,
) -> bool:
    if str(record.get("workflow") or "") not in SUPPORTED_WORKFLOWS:
        return False
    if str(record.get("status") or "") not in ACTIVE_ASSESSMENT_STATUSES:
        return False
    age = assessment_age_seconds(record, now=now)
    return age is None or age >= float(
        stale_seconds or configured_assessment_stale_seconds()
    )


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
        return normalizer("assessment_runs", row)
    payload = dict(row.get("payload") or {})
    payload.update(
        {
            "run_id": row.get("run_id"),
            "customer_id": row.get("customer_id"),
            "project_id": row.get("project_id"),
            "workflow": row.get("workflow"),
            "status": row.get("status"),
            "created_at": str(row.get("created_at")),
        }
    )
    return payload


def _postgres_atomic_transition(
    active: StorageAdapter,
    run_id: str,
    expected_statuses: set[str],
    new_status: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    adapter = getattr(active, "adapter", None)
    query = getattr(adapter, "_query", None)
    jsonb = getattr(adapter, "_jsonb", None)
    if not callable(query) or jsonb is None:
        raise RuntimeError("Postgres assessment transition capability is unavailable")
    expected = sorted({str(item) for item in expected_statuses if str(item)})
    if not expected:
        return None
    merged_patch = deepcopy(patch)
    merged_patch["status"] = new_status
    merged_patch["updated_at"] = patch.get("updated_at") or utc_now()
    rows = query(
        """
        UPDATE assessment_runs
        SET status=%s,
            payload=payload || %s
        WHERE run_id=%s
          AND status = ANY(%s)
        RETURNING *
        """,
        (
            new_status,
            jsonb(merged_patch),
            run_id,
            expected,
        ),
    )
    if not rows:
        return None
    return _normalize_postgres_row(adapter, rows[0])


def atomic_assessment_transition(
    run_id: str,
    expected_statuses: set[str],
    new_status: str,
    patch: dict[str, Any],
    *,
    store: StorageAdapter | None = None,
) -> dict[str, Any] | None:
    active = _store(store)
    if _adapter_name(active) == "postgres" and _persistence_available(active):
        return _postgres_atomic_transition(
            active,
            run_id,
            expected_statuses,
            new_status,
            patch,
        )

    with _MEMORY_TRANSITION_LOCK:
        current = active.get("assessment_runs", run_id)
        if not isinstance(current, dict):
            return None
        if str(current.get("status") or "") not in expected_statuses:
            return None
        updated = deepcopy(current)
        updated.update(deepcopy(patch))
        updated["run_id"] = run_id
        updated["status"] = new_status
        updated["updated_at"] = patch.get("updated_at") or utc_now()
        return active.put("assessment_runs", run_id, updated)


def _safe_checkpoint(record: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    checkpoint = (
        response.get("execution_checkpoint")
        if isinstance(response.get("execution_checkpoint"), dict)
        else record.get("execution_checkpoint")
        if isinstance(record.get("execution_checkpoint"), dict)
        else {}
    )
    return {
        "current_step": str(checkpoint.get("current_step") or "")[:80],
        "phase": str(checkpoint.get("phase") or "")[:80],
        "heartbeat_at": checkpoint.get("heartbeat_at"),
        "completed_steps": [
            str(item)[:80]
            for item in (checkpoint.get("completed_steps") or [])[:20]
        ],
        "progress_sha256": str(checkpoint.get("progress_sha256") or "")[:64],
    }


def _safe_run_summary(record: dict[str, Any]) -> dict[str, Any]:
    recovery = record.get("recovery") if isinstance(record.get("recovery"), dict) else {}
    if not recovery:
        response = record.get("response") if isinstance(record.get("response"), dict) else {}
        recovery = response.get("recovery") if isinstance(response.get("recovery"), dict) else {}
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    return {
        "run_id": str(record.get("run_id") or record.get("id") or ""),
        "workflow": str(record.get("workflow") or "unknown"),
        "service_tier": str(record.get("service_tier") or request.get("mode") or ""),
        "customer_id": str(record.get("customer_id") or "default_customer"),
        "project_id": str(record.get("project_id") or "default_project"),
        "repository": str(record.get("repository") or ""),
        "status": str(record.get("status") or "unknown"),
        "scan_id": str(record.get("scan_id") or ""),
        "snapshot_id": str(record.get("snapshot_id") or ""),
        "snapshot_commit_sha": str(record.get("snapshot_commit_sha") or ""),
        "report_id": str(record.get("report_id") or ""),
        "approval_id": str(record.get("approval_id") or ""),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "execution_checkpoint": _safe_checkpoint(record),
        "recovery": {
            "state": str(recovery.get("state") or ""),
            "reason": str(recovery.get("reason") or ""),
            "previous_status": str(recovery.get("previous_status") or ""),
            "detected_at": recovery.get("detected_at"),
            "resume_requested_at": recovery.get("resume_requested_at"),
            "resume_requested_by": str(recovery.get("resume_requested_by") or "")[:120],
            "attempt": int(recovery.get("attempt") or 0),
            "resume_allowed": bool(recovery.get("resume_allowed")),
            "automatic_resume": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _recovery_patch(
    record: dict[str, Any],
    *,
    now_text: str,
    age_seconds: float | None,
) -> dict[str, Any]:
    existing = record.get("recovery") if isinstance(record.get("recovery"), dict) else {}
    if not existing:
        response = record.get("response") if isinstance(record.get("response"), dict) else {}
        existing = response.get("recovery") if isinstance(response.get("recovery"), dict) else {}
    return {
        "updated_at": now_text,
        "recovery": {
            "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
            "state": RECOVERY_REQUIRED_STATUS,
            "reason": "stale_assessment_execution",
            "previous_status": str(record.get("status") or "unknown"),
            "detected_at": now_text,
            "stale_age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
            "resume_allowed": True,
            "automatic_resume": False,
            "attempt": int(existing.get("attempt") or 0),
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def reconcile_interrupted_assessment_runs(
    *,
    store: StorageAdapter | None = None,
    stale_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active = _store(store)
    threshold = max(
        60,
        min(
            int(stale_seconds or configured_assessment_stale_seconds()),
            86400,
        ),
    )
    current = now or _now_datetime()
    now_text = current.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    adapter = _adapter_name(active)
    durable = _persistence_available(active)
    if adapter != "postgres" or not durable:
        return {
            "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
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

    records = active.list("assessment_runs")[:MAX_RECONCILE_RECORDS]
    reconciled: list[str] = []
    fresh_active = 0
    conflicts = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        workflow = str(record.get("workflow") or "")
        status = str(record.get("status") or "")
        if workflow not in SUPPORTED_WORKFLOWS or status not in ACTIVE_ASSESSMENT_STATUSES:
            continue
        if not assessment_is_stale(
            record,
            stale_seconds=threshold,
            now=current,
        ):
            fresh_active += 1
            continue
        run_id = str(record.get("run_id") or record.get("id") or "")
        if not run_id:
            continue
        age = assessment_age_seconds(record, now=current)
        transitioned = atomic_assessment_transition(
            run_id,
            {status},
            RECOVERY_REQUIRED_STATUS,
            _recovery_patch(record, now_text=now_text, age_seconds=age),
            store=active,
        )
        if transitioned:
            reconciled.append(run_id)
            try:
                active.audit(
                    "assessment.recovery_required",
                    {
                        "run_id": run_id,
                        "workflow": workflow,
                        "previous_status": status,
                        "stale_age_seconds": round(age, 3) if age is not None else None,
                    },
                    customer_id=str(record.get("customer_id") or "default_customer"),
                    project_id=str(record.get("project_id") or "default_project"),
                )
            except Exception:
                pass
        else:
            conflicts += 1

    refreshed = active.list("assessment_runs")[:MAX_RECONCILE_RECORDS]
    recovery_required = sum(
        1
        for record in refreshed
        if isinstance(record, dict)
        and str(record.get("workflow") or "") in SUPPORTED_WORKFLOWS
        and str(record.get("status") or "") == RECOVERY_REQUIRED_STATUS
    )
    return {
        "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
        "status": "attention_required" if recovery_required else "clear",
        "adapter": adapter,
        "persistence_available": durable,
        "stale_seconds": threshold,
        "examined": len(records),
        "reconciled": len(reconciled),
        "reconciled_run_ids": reconciled[:100],
        "fresh_active": fresh_active,
        "transition_conflicts": conflicts,
        "recovery_required": recovery_required,
        "blockers": [],
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def assessment_recovery_inventory(
    *,
    store: StorageAdapter | None = None,
    refresh: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    active = _store(store)
    bounded_limit = max(1, min(int(limit), MAX_INVENTORY_LIMIT))
    reconciliation = (
        reconcile_interrupted_assessment_runs(store=active)
        if refresh
        else dict(_STARTUP_RESULT or {})
    )
    records = active.list("assessment_runs")[:MAX_RECONCILE_RECORDS]
    recovery_items = [
        _safe_run_summary(record)
        for record in records
        if isinstance(record, dict)
        and str(record.get("workflow") or "") in SUPPORTED_WORKFLOWS
        and str(record.get("status") or "") == RECOVERY_REQUIRED_STATUS
    ]
    active_items = [
        _safe_run_summary(record)
        for record in records
        if isinstance(record, dict)
        and str(record.get("workflow") or "") in SUPPORTED_WORKFLOWS
        and str(record.get("status") or "") in ACTIVE_ASSESSMENT_STATUSES
    ]
    recovery_items.sort(key=lambda item: str(item.get("updated_at") or ""))
    active_items.sort(key=lambda item: str(item.get("updated_at") or ""))
    return {
        "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
        "status": "attention_required" if recovery_items else "clear",
        "generated_at": utc_now(),
        "adapter": _adapter_name(active),
        "persistence_available": _persistence_available(active),
        "stale_seconds": configured_assessment_stale_seconds(),
        "counts": {
            "recovery_required": len(recovery_items),
            "active": len(active_items),
            "mid_recovery_required": sum(
                1 for item in recovery_items if item.get("workflow") == "mid_assessment"
            ),
            "full_recovery_required": sum(
                1 for item in recovery_items if item.get("workflow") == "full_assessment"
            ),
            "total_records_examined": len(records),
        },
        "recovery_required": recovery_items[:bounded_limit],
        "active": active_items[:bounded_limit],
        "limit": bounded_limit,
        "reconciliation": reconciliation,
        "operator_action": (
            "Review the saved scope, authorization, checkpoint, snapshot, scanner, report, and approval identities before resuming the same run ID."
        ),
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _valid_resume_source(record: dict[str, Any]) -> tuple[bool, str]:
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    repository = str(record.get("repository") or request.get("repository") or request.get("target") or "").strip()
    if not repository:
        return False, "repository_missing"
    if not str(record.get("customer_id") or request.get("customer_id") or "").strip():
        return False, "customer_scope_missing"
    if not str(record.get("project_id") or request.get("project_id") or "").strip():
        return False, "project_scope_missing"
    if not str(request.get("authorized_by") or "").strip():
        return False, "authorized_by_missing"
    if not str(request.get("authorization_scope") or "").strip():
        return False, "authorization_scope_missing"
    if not bool(request.get("authorization_confirmed") or request.get("authorized")):
        return False, "authorization_confirmation_missing"
    snapshot_id = str(record.get("snapshot_id") or "")
    snapshot_commit = str(record.get("snapshot_commit_sha") or "")
    if bool(snapshot_id) != bool(snapshot_commit):
        return False, "snapshot_identity_incomplete"
    return True, ""


def _model_kwargs(model_type: Any, values: dict[str, Any]) -> dict[str, Any]:
    fields = getattr(model_type, "model_fields", None)
    if fields is None:
        fields = getattr(model_type, "__fields__", {})
    allowed = {str(item) for item in fields or {}}
    return {key: deepcopy(value) for key, value in values.items() if key in allowed}


def _resume_request(record: dict[str, Any]) -> Any:
    request = deepcopy(record.get("request") or {})
    request["authorization_confirmed"] = True
    request["authorized"] = True
    request["auto_continue"] = True
    workflow = str(record.get("workflow") or "")
    if workflow == "mid_assessment":
        from nico.mid_assessment_api import MidAssessmentStatusRequest

        return MidAssessmentStatusRequest(
            **_model_kwargs(MidAssessmentStatusRequest, request)
        )
    if workflow == "full_assessment":
        from nico.full_assessment_api import FullAssessmentStatusRequest

        return FullAssessmentStatusRequest(
            **_model_kwargs(FullAssessmentStatusRequest, request)
        )
    raise ValueError("unsupported assessment workflow")


def _invoke_resume(record: dict[str, Any], req: Any) -> dict[str, Any]:
    run_id = str(record.get("run_id") or "")
    workflow = str(record.get("workflow") or "")
    if workflow == "mid_assessment":
        import nico.mid_assessment_api as mid_api

        return mid_api.mid_assessment_status_response(run_id, req)
    if workflow == "full_assessment":
        import nico.full_assessment_api as full_api

        return full_api.full_assessment_status_response(run_id, req)
    raise ValueError("unsupported assessment workflow")


def _return_to_recovery(
    run_id: str,
    *,
    actor: str,
    attempt: int,
    error_type: str,
    store: StorageAdapter,
) -> dict[str, Any] | None:
    return atomic_assessment_transition(
        run_id,
        {"resuming", "running", "planned"},
        RECOVERY_REQUIRED_STATUS,
        {
            "updated_at": utc_now(),
            "recovery": {
                "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
                "state": RECOVERY_REQUIRED_STATUS,
                "reason": "resume_execution_failed",
                "previous_status": "resuming",
                "detected_at": utc_now(),
                "resume_requested_by": str(actor or "operator")[:120],
                "resume_allowed": True,
                "automatic_resume": False,
                "attempt": attempt,
                "error_type": str(error_type or "AssessmentResumeError")[:120],
            },
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        store=store,
    )


def resume_interrupted_assessment_run(
    run_id: str,
    *,
    actor: str,
    store: StorageAdapter | None = None,
    invoker: Callable[[dict[str, Any], Any], dict[str, Any]] = _invoke_resume,
) -> dict[str, Any]:
    active = _store(store)
    normalized_run_id = str(run_id or "").strip()
    if not (
        normalized_run_id.startswith("midrun_")
        or normalized_run_id.startswith("fullrun_")
    ):
        return {
            "status": "not_found",
            "code": "assessment_run_not_found",
            "run_id": normalized_run_id,
        }
    current = active.get("assessment_runs", normalized_run_id)
    if not isinstance(current, dict) or str(current.get("workflow") or "") not in SUPPORTED_WORKFLOWS:
        return {
            "status": "not_found",
            "code": "assessment_run_not_found",
            "run_id": normalized_run_id,
        }
    current_status = str(current.get("status") or "unknown")
    if current_status in ACTIVE_ASSESSMENT_STATUSES | TERMINAL_ASSESSMENT_STATUSES:
        return {
            "status": current_status,
            "idempotent_reuse": True,
            "run": _safe_run_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }
    if current_status != RECOVERY_REQUIRED_STATUS:
        return {
            "status": "blocked",
            "code": "assessment_not_recoverable",
            "run": _safe_run_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }
    valid, reason = _valid_resume_source(current)
    if not valid:
        return {
            "status": "blocked",
            "code": reason,
            "run": _safe_run_summary(current),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    scan_id = str(current.get("scan_id") or "")
    if scan_id:
        scan = active.get("scanner_runs", scan_id) or {}
        scan_status = str(scan.get("status") or "not_found")
        if scan_status == RECOVERY_REQUIRED_STATUS:
            return {
                "status": "blocked",
                "code": "scanner_recovery_required",
                "run": _safe_run_summary(current),
                "automatic_resume": False,
                "client_delivery_allowed": False,
            }
        scan_run_id = str(scan.get("run_id") or "")
        if scan and scan_run_id and scan_run_id != normalized_run_id:
            return {
                "status": "blocked",
                "code": "scanner_run_identity_mismatch",
                "run": _safe_run_summary(current),
                "automatic_resume": False,
                "client_delivery_allowed": False,
            }

    existing_recovery = current.get("recovery") if isinstance(current.get("recovery"), dict) else {}
    if not existing_recovery:
        response = current.get("response") if isinstance(current.get("response"), dict) else {}
        existing_recovery = response.get("recovery") if isinstance(response.get("recovery"), dict) else {}
    attempt = int(existing_recovery.get("attempt") or 0) + 1
    now_text = utc_now()
    claimed = atomic_assessment_transition(
        normalized_run_id,
        {RECOVERY_REQUIRED_STATUS},
        "resuming",
        {
            "updated_at": now_text,
            "recovery": {
                "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
                "state": "resume_claimed",
                "reason": existing_recovery.get("reason") or "stale_assessment_execution",
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
        latest = active.get("assessment_runs", normalized_run_id) or current
        latest_status = str(latest.get("status") or "unknown")
        if latest_status in ACTIVE_ASSESSMENT_STATUSES | TERMINAL_ASSESSMENT_STATUSES:
            return {
                "status": latest_status,
                "idempotent_reuse": True,
                "run": _safe_run_summary(latest),
                "automatic_resume": False,
                "client_delivery_allowed": False,
            }
        return {
            "status": "blocked",
            "code": "assessment_resume_claim_failed",
            "run": _safe_run_summary(latest),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    try:
        req = _resume_request(claimed)
        result = invoker(claimed, req)
    except Exception as exc:
        error_type = type(exc).__name__[:120]
        recovered = _return_to_recovery(
            normalized_run_id,
            actor=actor,
            attempt=attempt,
            error_type=error_type,
            store=active,
        )
        return {
            "status": "blocked",
            "code": "assessment_resume_failed",
            "error_type": error_type,
            "run": _safe_run_summary(recovered or claimed),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    final_status = str(result.get("status") or "unknown")
    if final_status in {"failed", "blocked"}:
        recovered = _return_to_recovery(
            normalized_run_id,
            actor=actor,
            attempt=attempt,
            error_type="AssessmentResumeResultFailed",
            store=active,
        )
        return {
            "status": "blocked",
            "code": "assessment_resume_failed",
            "error_type": "AssessmentResumeResultFailed",
            "run": _safe_run_summary(recovered or claimed),
            "automatic_resume": False,
            "client_delivery_allowed": False,
        }

    latest = active.get("assessment_runs", normalized_run_id) or claimed
    try:
        active.audit(
            "assessment.resume_claimed",
            {
                "run_id": normalized_run_id,
                "workflow": claimed.get("workflow") or "unknown",
                "attempt": attempt,
                "actor": str(actor or "operator")[:120],
                "result_status": final_status,
            },
            customer_id=str(claimed.get("customer_id") or "default_customer"),
            project_id=str(claimed.get("project_id") or "default_project"),
        )
    except Exception:
        pass
    return {
        "status": final_status,
        "idempotent_reuse": False,
        "run": _safe_run_summary(latest),
        "resume": {
            "same_run_id": True,
            "attempt": attempt,
            "requested_at": now_text,
            "requested_by": str(actor or "operator")[:120],
        },
        "result": result,
        "automatic_resume": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def assessment_recovery_status(
    *,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _store(store)
    adapter = _adapter_name(active)
    durable = _persistence_available(active)
    if adapter != "postgres" or not durable:
        return {
            "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
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
        records = active.list("assessment_runs")[:MAX_RECONCILE_RECORDS]
    except Exception:
        return {
            "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
            "status": "unavailable",
            "clear": False,
            "adapter": adapter,
            "persistence_available": durable,
            "recovery_required": None,
            "stale_active": None,
            "active": None,
            "blockers": ["assessment_recovery_inventory_unavailable"],
        }
    recovery_required = 0
    stale_active = 0
    active_count = 0
    for record in records:
        if not isinstance(record, dict) or str(record.get("workflow") or "") not in SUPPORTED_WORKFLOWS:
            continue
        status = str(record.get("status") or "")
        if status == RECOVERY_REQUIRED_STATUS:
            recovery_required += 1
        if status in ACTIVE_ASSESSMENT_STATUSES:
            active_count += 1
            if assessment_is_stale(record):
                stale_active += 1
    clear = recovery_required == 0 and stale_active == 0
    return {
        "artifact_schema": ASSESSMENT_RECOVERY_SCHEMA,
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


def _require_operator(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "status": "blocked",
            "code": "operator_authentication_required",
            "message": "Operator authentication is required for assessment recovery actions.",
            "admin_write": status,
        },
    )


def assessment_recovery_inventory_response(
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
    return assessment_recovery_inventory(refresh=refresh, limit=limit)


def assessment_recovery_resume_response(
    run_id: str,
    req: AssessmentResumeRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    result = resume_interrupted_assessment_run(run_id, actor=req.actor)
    if result.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail={
                "status": "not_found",
                "code": result.get("code") or "assessment_run_not_found",
                "message": "Assessment run not found.",
            },
        )
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "blocked",
                "code": result.get("code") or "assessment_resume_blocked",
                "message": "Assessment resume was blocked by recovery-state, identity, or authorization validation.",
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


def install_assessment_recovery(target: FastAPI) -> dict[str, Any]:
    global _STARTUP_RESULT
    existing = _route_pairs(target)
    if ASSESSMENT_RECOVERY_INVENTORY_ROUTE not in existing:
        target.get("/operations/recovery/assessments", tags=["operations"])(
            assessment_recovery_inventory_response
        )
    if ASSESSMENT_RECOVERY_RESUME_ROUTE not in existing:
        target.post(
            "/operations/recovery/assessment/{run_id}/resume",
            tags=["operations"],
        )(assessment_recovery_resume_response)
    target.openapi_schema = None

    from nico.operations_readiness import REQUIRED_OPERATION_ROUTES

    REQUIRED_OPERATION_ROUTES.update(REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES)
    _STARTUP_RESULT = reconcile_interrupted_assessment_runs()
    missing = REQUIRED_ASSESSMENT_RECOVERY_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(
            f"Assessment recovery route registration incomplete; missing={sorted(missing)}"
        )
    return {
        "installed": True,
        "routes": sorted(REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES),
        "routes_reused": all(
            route in existing for route in REQUIRED_ASSESSMENT_RECOVERY_ROUTES
        ),
        "startup_reconciliation": dict(_STARTUP_RESULT),
        "automatic_resume": False,
    }


__all__ = [
    "ASSESSMENT_RECOVERY_SCHEMA",
    "ASSESSMENT_RECOVERY_INVENTORY_ROUTE",
    "ASSESSMENT_RECOVERY_RESUME_ROUTE",
    "REQUIRED_ASSESSMENT_RECOVERY_ROUTES",
    "REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES",
    "SUPPORTED_WORKFLOWS",
    "ACTIVE_ASSESSMENT_STATUSES",
    "RECOVERY_REQUIRED_STATUS",
    "TERMINAL_ASSESSMENT_STATUSES",
    "AssessmentResumeRequest",
    "configured_assessment_stale_seconds",
    "assessment_age_seconds",
    "assessment_is_stale",
    "atomic_assessment_transition",
    "reconcile_interrupted_assessment_runs",
    "assessment_recovery_inventory",
    "resume_interrupted_assessment_run",
    "assessment_recovery_status",
    "assessment_recovery_inventory_response",
    "assessment_recovery_resume_response",
    "install_assessment_recovery",
]
