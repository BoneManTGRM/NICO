from __future__ import annotations

from functools import wraps
from threading import Lock
from typing import Any, Callable

from nico import express_async_api as express

VERSION = "nico.express_failure_stage_truth.v3"
_PATCH_MARKER = "_nico_express_failure_stage_truth_v3"
_TERMINAL_FAILURES = {"blocked", "failed", "error", "interrupted", "rejected"}
_SYNTHETIC_STAGE_NAMES = {"blocked", "failed", "error", "interrupted", "rejected"}
_STAGE_LOCK = Lock()
_LAST_STAGE_BY_RUN: dict[str, str] = {}


def _remember(run_id: str, stage: str) -> None:
    normalized_run = str(run_id or "").strip()
    normalized_stage = str(stage or "").strip()
    if not normalized_run or not normalized_stage:
        return
    with _STAGE_LOCK:
        _LAST_STAGE_BY_RUN[normalized_run] = normalized_stage


def _last_stage(run_id: str) -> str:
    with _STAGE_LOCK:
        return _LAST_STAGE_BY_RUN.get(str(run_id or "").strip(), "")


def _forget(run_id: str) -> None:
    with _STAGE_LOCK:
        _LAST_STAGE_BY_RUN.pop(str(run_id or "").strip(), None)


def _decorate_terminal_progress(
    response: dict[str, Any],
    *,
    status: str,
    code: str,
    failure_stage: str,
) -> dict[str, Any]:
    if status not in _TERMINAL_FAILURES or not failure_stage:
        return response

    response["failure_stage"] = failure_stage
    response["failure_code"] = str(code or response.get("code") or "express_terminal_failure")[:80]
    response["current_stage"] = failure_stage

    progress = response.get("progress")
    if not isinstance(progress, list):
        return response

    for item in progress:
        if not isinstance(item, dict) or str(item.get("step") or "") != failure_stage:
            continue
        item["status"] = status
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        evidence.update(
            {
                "failure_stage": failure_stage,
                "failure_code": response["failure_code"],
                "terminal_status": status,
                "same_run_continuation": True,
            }
        )
        item["evidence"] = evidence
        break
    return response


def install_express_failure_stage_truth_v3() -> dict[str, Any]:
    if getattr(express._response, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "actual_failure_stage_preserved": True,
            "later_pending_stages_remain_pending": True,
            "safe_failure_code_exposed": True,
            "raw_exception_exposed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    original_record_stage: Callable[..., dict[str, Any]] = express._record_stage
    original_response: Callable[..., dict[str, Any]] = express._response
    original_release_active: Callable[..., None] = express._release_active

    @wraps(original_record_stage)
    def record_stage(run_id: str, request_payload: dict[str, Any], stage: str, message: str, **kwargs: Any) -> dict[str, Any]:
        _remember(run_id, stage)
        return original_record_stage(run_id, request_payload, stage, message, **kwargs)

    @wraps(original_response)
    def response(
        run_id: str,
        payload: dict[str, Any],
        status: str,
        message: str,
        *,
        code: str = "",
        stage: str = "request_accepted",
        progress_percent: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        normalized_stage = str(stage or "").strip()
        remembered = _last_stage(run_id)
        failure_stage = (
            remembered
            if normalized_status in _TERMINAL_FAILURES
            and normalized_stage in _SYNTHETIC_STAGE_NAMES
            and remembered
            else normalized_stage
        )

        result = original_response(
            run_id,
            payload,
            status,
            message,
            code=code,
            stage=failure_stage,
            progress_percent=progress_percent,
            evidence=evidence,
        )
        return _decorate_terminal_progress(
            result,
            status=normalized_status,
            code=code,
            failure_stage=failure_stage if normalized_status in _TERMINAL_FAILURES else "",
        )

    @wraps(original_release_active)
    def release_active(run_id: str, request_payload: dict[str, Any]) -> None:
        try:
            original_release_active(run_id, request_payload)
        finally:
            _forget(run_id)

    setattr(record_stage, _PATCH_MARKER, True)
    setattr(response, _PATCH_MARKER, True)
    setattr(release_active, _PATCH_MARKER, True)
    express._record_stage = record_stage
    express._response = response
    express._release_active = release_active

    return {
        "status": "installed",
        "version": VERSION,
        "actual_failure_stage_preserved": True,
        "later_pending_stages_remain_pending": True,
        "safe_failure_code_exposed": True,
        "raw_exception_exposed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_failure_stage_truth_v3"]
