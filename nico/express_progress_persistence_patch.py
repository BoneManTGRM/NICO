from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from fastapi import HTTPException

EXPRESS_PROGRESS_PERSISTENCE_VERSION = "nico.express_progress_persistence.v1"
_RECORD_MARKER = "_nico_express_progress_record_v1"
_STATUS_MARKER = "_nico_express_progress_status_v1"
_PROGRESS_COLLECTION = "express_run_progress"
_STAGE_ORDER = {
    "request_accepted": 0,
    "repository_evidence": 1,
    "scanner_reconciliation": 2,
    "accuracy_review": 3,
    "score_reconciliation": 4,
    "report_generation": 5,
    "truth_and_review_gates": 6,
    "complete": 7,
    "blocked": 7,
    "failed": 7,
    "interrupted": 7,
}
_TERMINAL_SUCCESS = {"complete", "completed"}
_TERMINAL_FAILURE = {"blocked", "failed", "error", "interrupted", "rejected"}


def _progress_identity(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(response.get("run_id") or ""),
        "status": str(response.get("status") or "unknown"),
        "current_stage": str(response.get("current_stage") or "request_accepted"),
        "progress_percent": max(0, min(100, int(response.get("progress_percent") or 0))),
        "progress": deepcopy(response.get("progress") or []),
        "updated_at": response.get("updated_at"),
        "human_review_required": True,
        "client_ready": False,
    }


def _overlay_progress(api: Any, run_id: str, response: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(response)
    status = str(output.get("status") or "unknown").lower()
    if status in _TERMINAL_SUCCESS:
        output["current_stage"] = "complete"
        output["progress_percent"] = 100
        output["progress"] = api._stage_progress(
            "complete",
            "complete",
            "Express assessment completed. Draft report artifacts are ready for required human review.",
            evidence={"report_formats_ready": bool((output.get("reports") or {}).get("pdf_base64"))},
        )
        output["human_review_required"] = True
        output["client_ready"] = False
        return output

    progress_record = api.STORE.get(_PROGRESS_COLLECTION, run_id)
    if not isinstance(progress_record, dict):
        return output
    stored_status = str(progress_record.get("status") or "unknown").lower()
    response_stage = str(output.get("current_stage") or "request_accepted")
    stored_stage = str(progress_record.get("current_stage") or "request_accepted")
    use_stored = (
        stored_status in {"queued", "running"}
        and _STAGE_ORDER.get(stored_stage, -1) >= _STAGE_ORDER.get(response_stage, -1)
    ) or stored_status in _TERMINAL_FAILURE
    if not use_stored:
        return output
    for key in ("status", "current_stage", "progress_percent", "progress", "updated_at"):
        if key in progress_record:
            output[key] = deepcopy(progress_record[key])
    output["human_review_required"] = True
    output["client_ready"] = False
    return output


def install_express_progress_persistence() -> dict[str, Any]:
    from nico import express_async_api as api

    current_record: Callable[..., dict[str, Any]] = api._record
    if not getattr(current_record, _RECORD_MARKER, False):
        def record_with_independent_progress(
            run_id: str,
            request_payload: dict[str, Any],
            response: dict[str, Any],
        ) -> dict[str, Any]:
            persisted = current_record(run_id, request_payload, response)
            api.STORE.put(_PROGRESS_COLLECTION, run_id, _progress_identity(response))
            return persisted

        setattr(record_with_independent_progress, _RECORD_MARKER, True)
        setattr(record_with_independent_progress, "_nico_previous", current_record)
        api._record = record_with_independent_progress

    current_status: Callable[..., dict[str, Any]] = api.express_assessment_status
    if not getattr(current_status, _STATUS_MARKER, False):
        def status_with_independent_progress(run_id: str, req: Any) -> dict[str, Any]:
            try:
                result = current_status(run_id, req)
            except HTTPException as exc:
                if isinstance(exc.detail, dict):
                    exc.detail = _overlay_progress(api, run_id, exc.detail)
                raise
            return _overlay_progress(api, run_id, result)

        setattr(status_with_independent_progress, _STATUS_MARKER, True)
        setattr(status_with_independent_progress, "_nico_previous", current_status)
        api.express_assessment_status = status_with_independent_progress

    return {
        "status": "installed",
        "version": EXPRESS_PROGRESS_PERSISTENCE_VERSION,
        "collection": _PROGRESS_COLLECTION,
        "report_record_overwrite_can_reset_progress": False,
        "terminal_success_forces_100_percent": True,
        "human_review_required": True,
        "client_ready": False,
    }


__all__ = [
    "EXPRESS_PROGRESS_PERSISTENCE_VERSION",
    "install_express_progress_persistence",
]
