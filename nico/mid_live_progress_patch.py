from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

MID_LIVE_PROGRESS_VERSION = "nico.mid_live_progress.v1"
_START_MARKER = "_nico_mid_live_progress_start_v1"
_STATUS_MARKER = "_nico_mid_live_progress_status_v1"

_STAGE_PROGRESS = {
    "authorization": 4,
    "repo_evidence": 18,
    "scanner_worker": 18,
    "evidence_attachment": 62,
    "scoring": 74,
    "reports": 86,
    "approval_request": 94,
}
_ACTIVE = {"queued", "running", "pending", "planned", "starting"}


def _progress_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in result.get("progress") or [] if isinstance(item, dict)]


def _active_item(result: dict[str, Any]) -> dict[str, Any]:
    items = _progress_items(result)
    for item in items:
        if str(item.get("status") or "").lower() in _ACTIVE:
            return item
    return items[-1] if items else {}


def _bounded_percent(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, round(number)))


def _scanner_percent(result: dict[str, Any], active: dict[str, Any]) -> int | None:
    scanner = result.get("scanner") if isinstance(result.get("scanner"), dict) else {}
    scanner_evidence = result.get("scanner_evidence") if isinstance(result.get("scanner_evidence"), dict) else {}
    evidence = active.get("evidence") if isinstance(active.get("evidence"), dict) else {}
    for value in (
        scanner.get("progress_percent"),
        scanner_evidence.get("scanner_progress_percent"),
        evidence.get("scanner_progress_percent"),
        evidence.get("progress_percent"),
    ):
        percent = _bounded_percent(value)
        if percent is not None:
            return percent

    requested = scanner.get("tools_requested") or evidence.get("tools_requested") or []
    completed = scanner.get("tools_run") or evidence.get("tools_run") or []
    active_tool = str(scanner.get("active_tool") or evidence.get("active_tool") or "")
    if not isinstance(requested, list) or not requested:
        return None
    names = [str(item) for item in requested]
    active_index = names.index(active_tool) if active_tool in names else -1
    fraction = ((active_index + 0.35) / len(names)) if active_index >= 0 else (len(completed) / len(names))
    return max(0, min(100, round(fraction * 100)))


def attach_mid_live_progress(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    status = str(output.get("status") or "").lower()
    report_status = str(output.get("report_generation_status") or "").lower()
    approval = output.get("approval_request") if isinstance(output.get("approval_request"), dict) else {}
    if status == "complete" and report_status == "complete" and approval.get("approval_id"):
        output["current_stage"] = "complete"
        output["progress_percent"] = 100
        output["scanner_progress_percent"] = 100
        return output

    active = _active_item(output)
    step = str(active.get("step") or output.get("current_stage") or "")
    scanner = output.get("scanner") if isinstance(output.get("scanner"), dict) else {}
    scanner_status = str(scanner.get("status") or "").lower()
    if step == "scanner_worker" or scanner_status in {"queued", "running"}:
        scan_percent = _scanner_percent(output, active)
        output["current_stage"] = "scanner_worker"
        if scan_percent is None:
            output["progress_percent"] = 18
        else:
            output["scanner_progress_percent"] = scan_percent
            output["progress_percent"] = max(18, min(61, round(18 + scan_percent * 0.43)))
        return output

    stage_percent = _STAGE_PROGRESS.get(step)
    existing = _bounded_percent(output.get("progress_percent"))
    if stage_percent is not None:
        output["progress_percent"] = max(stage_percent, existing or 0)
        output["current_stage"] = step
    return output


def install_mid_live_progress() -> dict[str, Any]:
    from nico import mid_assessment_api as api

    current_start: Callable[..., dict[str, Any]] = api.mid_assessment_response
    if not getattr(current_start, _START_MARKER, False):
        def start_with_live_progress(req: Any) -> dict[str, Any]:
            return attach_mid_live_progress(current_start(req))

        setattr(start_with_live_progress, _START_MARKER, True)
        setattr(start_with_live_progress, "_nico_previous", current_start)
        api.mid_assessment_response = start_with_live_progress

    current_status: Callable[..., dict[str, Any]] = api.mid_assessment_status_response
    if not getattr(current_status, _STATUS_MARKER, False):
        def status_with_live_progress(run_id: str, req: Any) -> dict[str, Any]:
            return attach_mid_live_progress(current_status(run_id, req))

        setattr(status_with_live_progress, _STATUS_MARKER, True)
        setattr(status_with_live_progress, "_nico_previous", current_status)
        api.mid_assessment_status_response = status_with_live_progress

    return {
        "status": "installed",
        "version": MID_LIVE_PROGRESS_VERSION,
        "scanner_progress_is_dynamic": True,
        "scanner_window_start": 18,
        "scanner_window_end": 61,
        "evidence_attachment_start": 62,
        "terminal_success_percent": 100,
        "human_review_required": True,
        "client_ready": False,
    }


__all__ = [
    "MID_LIVE_PROGRESS_VERSION",
    "attach_mid_live_progress",
    "install_mid_live_progress",
]
