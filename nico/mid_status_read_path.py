from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico.mid_assessment_runs import build_mid_status_payload, explicit_model_fields
from nico.mid_live_progress_patch import attach_mid_live_progress
from nico.scanner_worker import get_scan

MID_STATUS_READ_PATH_VERSION = "nico.mid_status_read_path.v3"
_PATCH_MARKER = "_nico_mid_status_read_path_v3"
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
        "heartbeat_at",
        "heartbeat_sequence",
        "heartbeat_process_id",
        "heartbeat_thread",
        "heartbeat_persistence_status",
        "heartbeat_failure_type",
        "tool_elapsed_seconds",
        "tool_timeout_seconds",
        "tool_timeout_remaining_seconds",
        "tool_watchdog_policy",
        "created_at",
        "updated_at",
        "completed_at",
        "recovery",
    )
    return {key: deepcopy(scan.get(key)) for key in keys if key in scan}


def _display_progress(scan_summary: dict[str, Any]) -> int:
    base_progress = max(0, min(100, int(scan_summary.get("progress_percent") or 0)))
    requested = [str(item) for item in (scan_summary.get("tools_requested") or []) if str(item)]
    active_tool = str(scan_summary.get("active_tool") or "")
    try:
        elapsed = max(0.0, float(scan_summary.get("tool_elapsed_seconds") or 0))
        timeout = max(0.0, float(scan_summary.get("tool_timeout_seconds") or 0))
    except (TypeError, ValueError):
        return base_progress
    if not requested or active_tool not in requested or timeout <= 0:
        return base_progress
    index = requested.index(active_tool)
    span = 70.0 / max(1, len(requested))
    tool_start = 20.0 + index * span
    fraction = min(0.95, elapsed / timeout)
    interpolated = round(tool_start + span * fraction)
    return max(base_progress, min(89, interpolated))


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
    raw_progress_percent = max(0, min(100, int(scan_summary.get("progress_percent") or 0)))
    progress_percent = _display_progress(scan_summary)
    scan_summary["record_progress_percent"] = raw_progress_percent
    scan_summary["progress_percent"] = progress_percent
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
        elapsed = scan_summary.get("tool_elapsed_seconds")
        remaining = scan_summary.get("tool_timeout_remaining_seconds")
        timeout = scan_summary.get("tool_timeout_seconds")
        if elapsed is not None and remaining is not None and timeout:
            message = (
                f"Snapshot-bound scanner is running {active_tool}: "
                f"{float(elapsed):.0f}s elapsed, {float(remaining):.0f}s remaining before the safe timeout."
            )
        else:
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
        "scanner_record_progress_percent": raw_progress_percent,
        "active_tool": scan_summary.get("active_tool") or "",
        "heartbeat_at": scan_summary.get("heartbeat_at") or "",
        "heartbeat_sequence": scan_summary.get("heartbeat_sequence") or 0,
        "heartbeat_persistence_status": scan_summary.get("heartbeat_persistence_status") or "active",
        "tool_elapsed_seconds": scan_summary.get("tool_elapsed_seconds"),
        "tool_timeout_seconds": scan_summary.get("tool_timeout_seconds"),
        "tool_timeout_remaining_seconds": scan_summary.get("tool_timeout_remaining_seconds"),
        "tool_watchdog_policy": scan_summary.get("tool_watchdog_policy") or "hard_timeout_then_continue",
        "tools_requested": scan_summary.get("tools_requested") or [],
        "tools_run": scan_summary.get("tools_run") or [],
    }

    result["status"] = "running"
    result["status_refresh"] = True
    result["current_stage"] = "scanner_worker"
    result["progress_percent"] = max(int(result.get("progress_percent") or 0), progress_percent)
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
    from nico import mid_assessment_api

    current: Callable[..., dict[str, Any]] = mid_assessment_api.continue_mid_assessment
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_STATUS_READ_PATH_VERSION}

    @wraps(current)
    def continuation_with_status_read(model: Any) -> dict[str, Any]:
        payload = _payload(model)
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            return current(model)
        record = mid_assessment_api.STORE.get("assessment_runs", run_id)
        if not isinstance(record, dict):
            return current(model)
        explicit = explicit_model_fields(model)
        if not _identity_matches(record, payload, explicit):
            return current(model)
        retained = _retained_response(record)
        if _final_mid_ready(retained):
            return _retained_final_response(record)
        scan_id = str(record.get("scan_id") or _record(retained.get("scanner")).get("scan_id") or "")
        if scan_id:
            scan = get_scan(scan_id)
            if isinstance(scan, dict) and str(scan.get("status") or "") in _ACTIVE_SCAN_STATUSES:
                return _active_status_response(record, scan)
        return current(model)

    setattr(continuation_with_status_read, _PATCH_MARKER, True)
    setattr(continuation_with_status_read, "_nico_previous", current)
    mid_assessment_api.continue_mid_assessment = continuation_with_status_read
    return {
        "status": "installed",
        "version": MID_STATUS_READ_PATH_VERSION,
        "durable_scanner_read": True,
        "scanner_watchdog_visible": True,
        "intra_tool_progress_visible": True,
        "orchestrator_reentered_for_active_scan": False,
        "repository_recaptured_for_status": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_STATUS_READ_PATH_VERSION",
    "_active_status_response",
    "_final_mid_ready",
    "_retained_final_response",
    "_retained_response",
    "install_mid_status_read_path",
]
