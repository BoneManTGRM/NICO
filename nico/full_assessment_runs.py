from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.storage import STORE, StorageAdapter, utc_now

FULL_ASSESSMENT_WORKFLOW = "full_assessment"
REQUEST_FIELDS = {
    "target",
    "repository",
    "scan_id",
    "customer_id",
    "project_id",
    "client_name",
    "project_name",
    "authorized_by",
    "authorization_confirmed",
    "authorized",
    "mode",
    "run_scanners",
    "refresh_full_evidence",
    "build_reports",
    "create_final_review_request",
    "tools",
}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _request_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(payload[key]) for key in REQUEST_FIELDS if key in payload}


def _retained_response(result: dict[str, Any]) -> dict[str, Any]:
    retained = deepcopy(result)
    reports = retained.get("reports")
    if isinstance(reports, dict) and reports.get("pdf_base64"):
        reports["pdf_base64"] = ""
        reports["pdf_retention_note"] = "PDF bytes are not duplicated inside the full-run state record; use the report record or regenerated export."
    return retained


def _scan_id(result: dict[str, Any]) -> str:
    scanner = result.get("scanner") if isinstance(result.get("scanner"), dict) else {}
    evidence = result.get("scanner_evidence") if isinstance(result.get("scanner_evidence"), dict) else {}
    return str(scanner.get("scan_id") or evidence.get("scan_id") or "")


def _report_id(result: dict[str, Any]) -> str:
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    approval = result.get("approval") if isinstance(result.get("approval"), dict) else {}
    return str(reports.get("report_id") or approval.get("report_id") or "")


def _approval_id(result: dict[str, Any]) -> str:
    approval = result.get("approval") if isinstance(result.get("approval"), dict) else {}
    return str(approval.get("approval_id") or "")


def persistence_metadata(store: StorageAdapter | None = None, *, restored: bool = False) -> dict[str, Any]:
    active = _store(store)
    status = active.status()
    return {
        "recorded": True,
        "durable": bool(status.get("persistence_available")),
        "adapter": status.get("adapter") or status.get("mode") or "unknown",
        "restored": restored,
        "note": status.get("persistence_note") or "Full-run state was recorded through the configured storage adapter.",
    }


def persist_full_assessment_run(
    result: dict[str, Any],
    request_payload: dict[str, Any],
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _store(store)
    run_id = str(result.get("run_id") or request_payload.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("full assessment run_id is required for persistence")

    existing = active.get("assessment_runs", run_id) or {}
    request = dict(existing.get("request") or {})
    request.update(_request_snapshot(request_payload))
    repository = str(result.get("repository") or request.get("repository") or request.get("target") or existing.get("repository") or "")
    customer_id = str(result.get("customer_id") or request.get("customer_id") or existing.get("customer_id") or "default_customer")
    project_id = str(result.get("project_id") or request.get("project_id") or existing.get("project_id") or "default_project")
    now = utc_now()

    record = {
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "workflow": FULL_ASSESSMENT_WORKFLOW,
        "status": str(result.get("status") or existing.get("status") or "unknown"),
        "repository": repository,
        "request": request,
        "response": _retained_response(result),
        "scan_id": _scan_id(result) or str(existing.get("scan_id") or request.get("scan_id") or ""),
        "report_id": _report_id(result) or str(existing.get("report_id") or ""),
        "approval_id": _approval_id(result) or str(existing.get("approval_id") or ""),
        "created_at": existing.get("created_at") or result.get("generated_at") or now,
        "updated_at": now,
    }
    return active.put("assessment_runs", run_id, record)


def load_full_assessment_run(run_id: str, store: StorageAdapter | None = None) -> dict[str, Any] | None:
    record = _store(store).get("assessment_runs", run_id)
    if not record or record.get("workflow") != FULL_ASSESSMENT_WORKFLOW:
        return None
    return record


def explicit_model_fields(model: Any) -> set[str]:
    fields = getattr(model, "model_fields_set", None)
    if fields is None:
        fields = getattr(model, "__fields_set__", set())
    return {str(item) for item in fields or set()}


def build_status_payload(
    run_id: str,
    request_payload: dict[str, Any],
    explicit_fields: set[str],
    store: StorageAdapter | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    record = load_full_assessment_run(run_id, store=store)
    payload: dict[str, Any] = dict(record.get("request") or {}) if record else {}
    for key in explicit_fields:
        if key in request_payload:
            payload[key] = deepcopy(request_payload[key])

    payload["run_id"] = run_id
    if record:
        payload.setdefault("repository", record.get("repository") or "")
        payload.setdefault("customer_id", record.get("customer_id") or "default_customer")
        payload.setdefault("project_id", record.get("project_id") or "default_project")
        if record.get("scan_id") and "scan_id" not in explicit_fields:
            payload["scan_id"] = record.get("scan_id")

    payload["run_scanners"] = bool(payload.get("scan_id"))
    payload["build_reports"] = bool(request_payload.get("build_reports")) if "build_reports" in explicit_fields else False
    payload["create_final_review_request"] = bool(request_payload.get("create_final_review_request")) if "create_final_review_request" in explicit_fields else False
    return payload, record
