from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.full_assessment_runs import explicit_model_fields, persistence_metadata
from nico.storage import STORE, StorageAdapter, utc_now

MID_ASSESSMENT_WORKFLOW = "mid_assessment"
MID_REQUEST_FIELDS = {
    "target",
    "repository",
    "scan_id",
    "customer_id",
    "project_id",
    "client_name",
    "project_name",
    "authorized_by",
    "authorization_scope",
    "authorization_confirmed",
    "authorized",
    "mode",
    "timeframe_days",
    "run_scanners",
    "refresh_full_evidence",
    "build_reports",
    "create_final_review_request",
    "auto_continue",
    "tools",
}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _request_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(payload[key]) for key in MID_REQUEST_FIELDS if key in payload}


def _retained_response(result: dict[str, Any]) -> dict[str, Any]:
    retained = deepcopy(result)
    reports = retained.get("reports")
    if isinstance(reports, dict):
        reports["pdf_base64"] = ""
        reports["pdf_retention_note"] = "Mid draft PDF bytes are not duplicated inside the run state record."
    return retained


def _scan_id(result: dict[str, Any]) -> str:
    scanner = result.get("scanner") if isinstance(result.get("scanner"), dict) else {}
    evidence = result.get("scanner_evidence") if isinstance(result.get("scanner_evidence"), dict) else {}
    return str(scanner.get("scan_id") or evidence.get("scan_id") or "")


def persist_mid_assessment_run(
    result: dict[str, Any],
    request_payload: dict[str, Any],
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _store(store)
    run_id = str(result.get("run_id") or request_payload.get("run_id") or "").strip()
    if not run_id.startswith("midrun_"):
        raise ValueError("Mid assessment run_id must use the midrun_ identity prefix")

    existing = active.get("assessment_runs", run_id) or {}
    if existing and existing.get("workflow") not in {None, "", MID_ASSESSMENT_WORKFLOW}:
        raise ValueError("run_id is already bound to a different workflow")
    request = dict(existing.get("request") or {})
    request.update(_request_snapshot(request_payload))
    repository = str(result.get("repository") or request.get("repository") or request.get("target") or existing.get("repository") or "")
    customer_id = str(result.get("customer_id") or request.get("customer_id") or existing.get("customer_id") or "default_customer")
    project_id = str(result.get("project_id") or request.get("project_id") or existing.get("project_id") or "default_project")
    now = utc_now()
    response = _retained_response(result)
    snapshot = response.get("repository_snapshot") if isinstance(response.get("repository_snapshot"), dict) else {}
    record = {
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "workflow": MID_ASSESSMENT_WORKFLOW,
        "service_tier": "mid",
        "status": str(result.get("status") or existing.get("status") or "unknown"),
        "repository": repository,
        "request": request,
        "response": response,
        "scan_id": _scan_id(result) or str(existing.get("scan_id") or request.get("scan_id") or ""),
        "snapshot_id": str(snapshot.get("snapshot_id") or existing.get("snapshot_id") or ""),
        "snapshot_commit_sha": str(snapshot.get("commit_sha") or existing.get("snapshot_commit_sha") or ""),
        "report_id": str(existing.get("report_id") or ""),
        "approval_id": str(existing.get("approval_id") or ""),
        "created_at": existing.get("created_at") or result.get("generated_at") or now,
        "updated_at": now,
    }
    return active.put("assessment_runs", run_id, record)


def load_mid_assessment_run(run_id: str, store: StorageAdapter | None = None) -> dict[str, Any] | None:
    record = _store(store).get("assessment_runs", run_id)
    if not record or record.get("workflow") != MID_ASSESSMENT_WORKFLOW:
        return None
    return record


def build_mid_status_payload(
    run_id: str,
    request_payload: dict[str, Any],
    explicit_fields: set[str],
    store: StorageAdapter | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    record = load_mid_assessment_run(run_id, store=store)
    payload: dict[str, Any] = dict(record.get("request") or {}) if record else {}
    for key in explicit_fields:
        if key in request_payload and key in MID_REQUEST_FIELDS:
            payload[key] = deepcopy(request_payload[key])
    payload["run_id"] = run_id
    payload["mode"] = "mid"
    payload["build_reports"] = False
    payload["create_final_review_request"] = False
    if record:
        payload.setdefault("repository", record.get("repository") or "")
        payload.setdefault("customer_id", record.get("customer_id") or "default_customer")
        payload.setdefault("project_id", record.get("project_id") or "default_project")
        if record.get("scan_id") and "scan_id" not in explicit_fields:
            payload["scan_id"] = record.get("scan_id")
    payload["run_scanners"] = bool(payload.get("scan_id")) or bool(payload.get("run_scanners", True))
    return payload, record


__all__ = [
    "MID_ASSESSMENT_WORKFLOW",
    "MID_REQUEST_FIELDS",
    "explicit_model_fields",
    "persistence_metadata",
    "persist_mid_assessment_run",
    "load_mid_assessment_run",
    "build_mid_status_payload",
]
