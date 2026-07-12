from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Callable

from nico.storage import STORE, StorageAdapter, utc_now

ASSESSMENT_CHECKPOINT_SCHEMA = "nico.assessment_execution_checkpoint.v1"
ACTIVE_EXECUTION_STATUS = "running"
TERMINAL_EXECUTION_STATUSES = {"complete", "failed", "blocked", "cancelled"}
CHECKPOINT_PHASES = {
    "preflight",
    "step_started",
    "step_completed",
    "step_failed",
    "orchestration_finalized",
}
MONOTONIC_INTENT_FIELDS = {"build_reports", "create_final_review_request"}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _retained_response(result: dict[str, Any]) -> dict[str, Any]:
    retained = deepcopy(result)
    reports = retained.get("reports")
    if isinstance(reports, dict) and reports.get("pdf_base64"):
        reports["pdf_base64"] = ""
        reports["pdf_retention_note"] = (
            "Checkpoint state does not duplicate PDF bytes; use the report record."
        )
    retained.pop("optional_evidence_submission", None)
    return retained


def _scan_id(result: dict[str, Any]) -> str:
    scanner = result.get("scanner") if isinstance(result.get("scanner"), dict) else {}
    evidence = (
        result.get("scanner_evidence")
        if isinstance(result.get("scanner_evidence"), dict)
        else {}
    )
    return str(scanner.get("scan_id") or evidence.get("scan_id") or "")


def _completed_steps(result: dict[str, Any]) -> list[str]:
    completed: list[str] = []
    for item in result.get("progress") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "") not in {"complete", "skipped"}:
            continue
        step = str(item.get("step") or "").strip()
        if step and step not in completed:
            completed.append(step)
    return completed


def _request_snapshot(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(existing)
    for key, value in payload.items():
        if key.startswith("_"):
            continue
        if key in MONOTONIC_INTENT_FIELDS:
            merged[key] = bool(merged.get(key)) or bool(value)
        else:
            merged[key] = deepcopy(value)
    return merged


def build_checkpoint_result(
    result: dict[str, Any],
    *,
    step: str,
    phase: str,
    recovery_attempt: int = 0,
) -> dict[str, Any]:
    if phase not in CHECKPOINT_PHASES:
        raise ValueError("unsupported assessment checkpoint phase")
    checkpointed = deepcopy(result)
    heartbeat = utc_now()
    current_status = str(checkpointed.get("status") or "planned")
    if phase != "orchestration_finalized" and current_status not in TERMINAL_EXECUTION_STATUSES:
        checkpointed["status"] = ACTIVE_EXECUTION_STATUS
    progress = checkpointed.get("progress") if isinstance(checkpointed.get("progress"), list) else []
    completed = _completed_steps(checkpointed)
    checkpointed["execution_checkpoint"] = {
        "artifact_schema": ASSESSMENT_CHECKPOINT_SCHEMA,
        "current_step": str(step or "preflight")[:80],
        "phase": phase,
        "heartbeat_at": heartbeat,
        "completed_steps": completed,
        "completed_step_count": len(completed),
        "progress_sha256": _hash(progress),
        "recovery_attempt": max(0, int(recovery_attempt or 0)),
    }
    checkpointed["recovery"] = {
        "state": (
            "complete"
            if checkpointed.get("status") == "complete"
            else "failed"
            if checkpointed.get("status") in {"failed", "blocked"}
            else "active"
        ),
        "automatic_resume": False,
        "human_review_required": True,
        "attempt": max(0, int(recovery_attempt or 0)),
        "last_checkpoint_step": str(step or "preflight")[:80],
        "last_checkpoint_phase": phase,
        "heartbeat_at": heartbeat,
    }
    checkpointed["execution_heartbeat_at"] = heartbeat
    checkpointed["human_review_required"] = True
    checkpointed["client_ready"] = False
    checkpointed["client_delivery_allowed"] = False
    return checkpointed


def persist_assessment_checkpoint(
    result: dict[str, Any],
    request_payload: dict[str, Any],
    *,
    workflow: str,
    service_tier: str,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _store(store)
    run_id = str(result.get("run_id") or request_payload.get("run_id") or "").strip()
    expected_prefix = "midrun_" if workflow == "mid_assessment" else "fullrun_"
    if not run_id.startswith(expected_prefix):
        raise ValueError(f"{workflow} checkpoint requires a {expected_prefix} run_id")

    existing = active.get("assessment_runs", run_id) or {}
    existing_workflow = str(existing.get("workflow") or "")
    if existing_workflow and existing_workflow != workflow:
        raise ValueError("run_id is already bound to a different workflow")

    request = _request_snapshot(
        dict(existing.get("request") or {}),
        request_payload,
    )
    repository = str(
        result.get("repository")
        or request.get("repository")
        or request.get("target")
        or existing.get("repository")
        or ""
    )
    customer_id = str(
        result.get("customer_id")
        or request.get("customer_id")
        or existing.get("customer_id")
        or "default_customer"
    )
    project_id = str(
        result.get("project_id")
        or request.get("project_id")
        or existing.get("project_id")
        or "default_project"
    )
    response = _retained_response(result)
    snapshot = (
        response.get("repository_snapshot")
        if isinstance(response.get("repository_snapshot"), dict)
        else {}
    )
    reports = response.get("reports") if isinstance(response.get("reports"), dict) else {}
    approval = response.get("approval") if isinstance(response.get("approval"), dict) else {}
    now = utc_now()
    record = {
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "workflow": workflow,
        "service_tier": service_tier,
        "status": str(result.get("status") or existing.get("status") or ACTIVE_EXECUTION_STATUS),
        "repository": repository,
        "request": request,
        "response": response,
        "scan_id": _scan_id(result) or str(existing.get("scan_id") or request.get("scan_id") or ""),
        "snapshot_id": str(snapshot.get("snapshot_id") or existing.get("snapshot_id") or ""),
        "snapshot_commit_sha": str(snapshot.get("commit_sha") or existing.get("snapshot_commit_sha") or ""),
        "report_id": str(reports.get("report_id") or existing.get("report_id") or ""),
        "approval_id": str(approval.get("approval_id") or existing.get("approval_id") or ""),
        "execution_checkpoint": deepcopy(response.get("execution_checkpoint") or {}),
        "recovery": deepcopy(response.get("recovery") or existing.get("recovery") or {}),
        "created_at": existing.get("created_at") or result.get("generated_at") or now,
        "updated_at": now,
    }
    return active.put("assessment_runs", run_id, record)


def initial_checkpoint_result(
    request_payload: dict[str, Any],
    *,
    workflow: str,
    service_tier: str,
) -> dict[str, Any]:
    run_id = str(request_payload.get("run_id") or "")
    repository = str(request_payload.get("repository") or request_payload.get("target") or "")
    result = {
        "status": ACTIVE_EXECUTION_STATUS,
        "run_id": run_id,
        "repository": repository,
        "customer_id": str(request_payload.get("customer_id") or "default_customer"),
        "project_id": str(request_payload.get("project_id") or "default_project"),
        "mode": service_tier,
        "workflow": workflow,
        "progress": [],
        "scanner": {"scan_id": str(request_payload.get("scan_id") or ""), "status": "not_started"},
        "scanner_evidence": {"status": "not_attached", "scan_id": str(request_payload.get("scan_id") or "")},
        "reports": {},
        "approval": {},
        "generated_at": utc_now(),
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }
    return build_checkpoint_result(result, step="preflight", phase="preflight")


def make_checkpoint_writer(
    request_payload: dict[str, Any],
    *,
    workflow: str,
    service_tier: str,
    store: StorageAdapter | None = None,
) -> Callable[[dict[str, Any], str, str], None]:
    active = _store(store)

    def write(result: dict[str, Any], step: str, phase: str) -> None:
        run_id = str(result.get("run_id") or request_payload.get("run_id") or "")
        existing = active.get("assessment_runs", run_id) or {}
        recovery = existing.get("recovery") if isinstance(existing.get("recovery"), dict) else {}
        attempt = int(recovery.get("attempt") or 0)
        checkpointed = build_checkpoint_result(
            result,
            step=step,
            phase=phase,
            recovery_attempt=attempt,
        )
        persist_assessment_checkpoint(
            checkpointed,
            request_payload,
            workflow=workflow,
            service_tier=service_tier,
            store=active,
        )

    return write


__all__ = [
    "ASSESSMENT_CHECKPOINT_SCHEMA",
    "ACTIVE_EXECUTION_STATUS",
    "TERMINAL_EXECUTION_STATUSES",
    "CHECKPOINT_PHASES",
    "build_checkpoint_result",
    "persist_assessment_checkpoint",
    "initial_checkpoint_result",
    "make_checkpoint_writer",
]
