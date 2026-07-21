from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_terminal_projection_truth.v1"
_PATCH_MARKER = "_nico_express_terminal_projection_truth_v1"
_ACTIVE = {"queued", "running", "starting", "pending"}
_TERMINAL_SUCCESS = {"complete", "completed"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _reports_ready(response: dict[str, Any]) -> bool:
    reports = _dict(response.get("reports"))
    return bool(
        str(reports.get("markdown") or "").strip()
        and str(reports.get("html") or "").strip()
        and str(reports.get("pdf_base64") or reports.get("pdf") or "").strip()
    )


def _scanner_complete(response: dict[str, Any]) -> bool:
    scanner = _dict(response.get("scanner"))
    status = str(
        scanner.get("status")
        or _dict(response.get("scanner_evidence")).get("scanner_status")
        or _dict(response.get("scanner_evidence")).get("status")
        or ""
    ).lower()
    return status in _TERMINAL_SUCCESS


def _complete_step_present(response: dict[str, Any]) -> bool:
    for item in response.get("progress") or []:
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or "").lower()
        status = str(item.get("status") or "").lower()
        if step in {"complete", "completed", "automated_complete"} and status in {
            "complete",
            "completed",
            "success",
            "passed",
        }:
            return True
    return False


def normalize_terminal_express_projection(response: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(response)
    status = str(projected.get("status") or "").lower()
    explicit_terminal = status in _TERMINAL_SUCCESS
    artifact_terminal = (
        status in _ACTIVE
        and _reports_ready(projected)
        and _scanner_complete(projected)
        and _complete_step_present(projected)
    )
    if not (explicit_terminal or artifact_terminal):
        return projected

    from nico import express_async_api as express

    projected["status"] = "complete"
    projected["current_stage"] = "complete"
    projected["progress_percent"] = 100
    projected["progress"] = express._stage_progress(
        "complete",
        "complete",
        "Express automated assessment stages and draft report artifacts are complete. Required human review is pending.",
        evidence={
            "terminal_projection_normalized": True,
            "report_formats_ready": _reports_ready(projected),
            "scanner_complete": _scanner_complete(projected),
        },
    )
    projected["terminal_state"] = "human_review_pending"
    projected["automated_stages_complete"] = True
    projected["human_review_status"] = "pending"
    projected["human_review_required"] = True
    projected["client_ready"] = False
    projected["client_delivery_allowed"] = False
    projected["status_truth"] = "terminal_artifact_projection"
    projected["express_terminal_projection_truth"] = {
        "status": "complete",
        "version": VERSION,
        "explicit_terminal": explicit_terminal,
        "artifact_terminal_recovered": artifact_terminal,
        "running_and_complete_steps_can_coexist": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return projected


def install_express_terminal_projection_truth_v1() -> dict[str, Any]:
    from nico import lifecycle_status_hardening as target

    current: Callable[[dict[str, Any]], dict[str, Any]] = target._safe_retained_response
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def safe_retained_response(record: dict[str, Any]) -> dict[str, Any]:
        return normalize_terminal_express_projection(current(record))

    setattr(safe_retained_response, _PATCH_MARKER, True)
    setattr(safe_retained_response, "_nico_previous", current)
    target._safe_retained_response = safe_retained_response
    return {
        "status": "installed",
        "version": VERSION,
        "terminal_status_read_normalized": True,
        "artifact_terminal_race_recovered": True,
        "running_and_complete_steps_can_coexist": False,
        "human_review_required": True,
    }


__all__ = [
    "VERSION",
    "install_express_terminal_projection_truth_v1",
    "normalize_terminal_express_projection",
]
