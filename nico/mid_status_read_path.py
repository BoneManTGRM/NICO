from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico.mid_assessment_runs import build_mid_status_payload, explicit_model_fields
from nico.mid_live_progress_patch import attach_mid_live_progress
from nico.scanner_worker import get_scan

MID_STATUS_READ_PATH_VERSION = "nico.mid_status_read_path.v1"
_PATCH_MARKER = "_nico_mid_status_read_path_v1"
_ACTIVE_SCAN_STATUSES = {"queued", "running"}
_IDENTITY_FIELDS = {"repository", "customer_id", "project_id", "scan_id"}


def _payload(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model or {})


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _retained_response(record: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(record.get("response") if isinstance(record.get("response"), dict) else {})
    result.setdefault("run_id", record.get("run_id") or "")
    result.setdefault("repository", record.get("repository") or "")
    result.setdefault("customer_id", record.get("customer_id") or "default_customer")
    result.setdefault("project_id", record.get("project_id") or "default_project")
    result.setdefault("assessment_type", "mid")
    result.setdefault("service_tier", "mid")
    result.setdefault("mode", "mid")
    result.setdefault("human_review_required", True)
    result.setdefault("client_ready", False)
    return result


def _final_mid_ready(result: dict[str, Any]) -> bool:
    approval = _record(result.get("approval_request"))
    return (
        str(result.get("status") or "").lower() in {"complete", "completed"}
        and str(result.get("report_generation_status") or "").lower() == "complete"
        and bool(approval.get("approval_id"))
    )


def _identity_matches(
    record: dict[str, Any],
    request_payload: dict[str, Any],
    explicit_fields: set[str],
) -> bool:
    saved_request = _record(record.get("request"))
    for field in _IDENTITY_FIELDS & explicit_fields:
        supplied = str(request_payload.get(field) or "")
        retained = str(
            record.get(field)
            or saved_request.get(field)
            or (record.get("repository") if field == "repository" else "")
            or ""
        )
        if supplied and retained and supplied != retained:
            return False
    if "authorization_confirmed" in explicit_fields and not bool(request_payload.get("authorization_confirmed")):
        return False
    if "authorized" in explicit_fields and not bool(request_payload.get("authorized")):
        return False
    return True


def _scan_summary(scan: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "scan_id",
        "run_id",
        "repository",
        "customer_id",
        "project_id",
        "status",
        "current_stage",
        "progress_percent",
        "active_tool",
        "tools_requested",
        "tools_run",
        "unavailable_tools",
        "failed_tools",
        "timed_out_tools",
        "snapshot_id",
        "snapshot_commit_sha",
        "actual_commit_sha",
        "snapshot_match",
        "created_at",
        "updated_at",
        "completed_at",
        "recovery",
    )
    return {key: deepcopy(scan.get(key)) for key in keys if key in scan}


def _set_progress(
    result: dict[str, Any],
    step: str,
    status: str,
    message: str,
    evidence: dict[str, Any],
) -> None:
    progress = [deepcopy(item) for item in result.get("progress") or [] if isinstance(item, dict)]
    replacement = {
        "step": step,
        "status": status,
        "message": message,
        "evidence": evidence,
    }
    for index, item in enumerate(progress):
        if item.get("step") == step:
            progress[index] = replacement
            result["progress"] = progress
            return
    progress.append(replacement)
    result["progress"] = progress


def _active_status_response(record: dict[str, Any], scan: dict[str, Any]) -> dict[str, Any]:
    result = _retained_response(record)
    scan_summary = _scan_summary(scan)
    scan_status = str(scan_summary.get("status") or "unknown")
    active_tool = str(scan_summary.get("active_tool") or "").replace("-", " ")
    progress_percent = max(0, min(100, int(scan_summary.get("progress_percent") or 0)))
    run_id = str(record.get("run_id") or result.get("run_id") or "")
    scan_id = str(scan_summary.get("scan_id") or record.get("scan_id") or "")
    snapshot_id = str(scan_summary.get("snapshot_id") or record.get("snapshot_id") or "")
    snapshot_commit_sha = str(
        scan_summary.get("snapshot_commit_sha")
        or record.get("snapshot_commit_sha")
        or ""
    )

    if scan_status == "queued":
        message = "Snapshot-bound scanner is queued and the exact run remains active."
    elif active_tool:
        message = f"Snapshot-bound scanner is running {active_tool}."
    else:
        message = "Snapshot-bound scanner is running."

    evidence = {
        "run_id": run_id,
        "scan_id": scan_id,
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": snapshot_commit_sha,
        "scanner_status": scan_status,
        "scanner_stage": scan_summary.get("current_stage") or "scanner_suite",
        "scanner_progress_percent": progress_percent,
        "active_tool": scan_summary.get("active_tool") or "",
        "tools_requested": scan_summary.get("tools_requested") or [],
        "tools_run": scan_summary.get("tools_run") or [],
    }

    result["status"] = "running"
    result["status_refresh"] = True
    result["current_stage"] = "scanner_worker"
    result["scanner"] = scan_summary
    result["scanner_evidence"] = {
        "status": "pending",
        "run_id": run_id,
        "scan_id": scan_id,
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": snapshot_commit_sha,
        **evidence,
    }
    result["auto_continuation"] = {
        "enabled": True,
        "continued": False,
        "scan_id": scan_id,
        "scanner_status": scan_status,
        "same_run": str(scan_summary.get("run_id") or "") == run_id,
        "reason": "Scanner is still active; the status endpoint returned retained run evidence plus the durable scanner record without re-running repository collection or orchestration.",
    }
    result["status_read_path"] = {
        "version": MID_STATUS_READ_PATH_VERSION,
        "mode": "durable_scanner_read",
        "orchestrator_reentered": False,
        "repository_recaptured": False,
        "assessment_run_rewritten": False,
        "read_only": True,
    }
    _set_progress(result, "scanner_worker", scan_status, message, evidence)
    _set_progress(
        result,
        "evidence_attachment",
        "pending",
        "Snapshot-bound scanner execution is still running; evidence attachment remains pending.",
        evidence,
    )
    return attach_mid_live_progress(result)


def _retained_final_response(record: dict[str, Any]) -> dict[str, Any]:
    result = _retained_response(record)
    result["status_refresh"] = True
    result["status_read_path"] = {
        "version": MID_STATUS_READ_PATH_VERSION,
        "mode": "retained_final",
        "orchestrator_reentered": False,
        "repository_recaptured": False,
        "assessment_run_rewritten": False,
        "read_only": True,
    }
    return attach_mid_live_progress(result)


def install_mid_status_read_path() -> dict[str, Any]:
    from nico import mid_assessment_api as api

    current: Callable[..., dict[str, Any]] = api.mid_assessment_status_response
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": MID_STATUS_READ_PATH_VERSION,
        }

    @wraps(current)
    def status_with_fast_read(run_id: str, req: Any) -> dict[str, Any]:
        request_payload = _payload(req)
        explicit = explicit_model_fields(req)
        payload, record = build_mid_status_payload(run_id, request_payload, explicit)
        if not isinstance(record, dict) or not _identity_matches(record, request_payload, explicit):
            return current(run_id, req)

        retained = _retained_response(record)
        if _final_mid_ready(retained):
            return _retained_final_response(record)

        scan_id = str(payload.get("scan_id") or record.get("scan_id") or "")
        scan = get_scan(scan_id) if scan_id else {"status": "not_started", "scan_id": ""}
        if str(scan.get("status") or "") in _ACTIVE_SCAN_STATUSES:
            return _active_status_response(record, scan)

        # Terminal scanners still pass through the canonical continuation path
        # so scoring, report generation, review creation, and exact-run failure
        # evidence remain governed by the existing truth and approval gates.
        return current(run_id, req)

    setattr(status_with_fast_read, _PATCH_MARKER, True)
    setattr(status_with_fast_read, "_nico_previous", current)
    api.mid_assessment_status_response = status_with_fast_read
    return {
        "status": "installed",
        "version": MID_STATUS_READ_PATH_VERSION,
        "active_scanner_status_is_read_only": True,
        "repository_recapture_during_polling": False,
        "orchestrator_reentry_during_polling": False,
        "terminal_continuation_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_STATUS_READ_PATH_VERSION",
    "install_mid_status_read_path",
]
