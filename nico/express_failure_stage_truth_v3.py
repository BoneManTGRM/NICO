from __future__ import annotations

from functools import wraps
from threading import Lock
from typing import Any, Callable

from nico import express_async_api as express

VERSION = "nico.express_failure_stage_truth.v4"
_PATCH_MARKER = "_nico_express_failure_stage_truth_v4"
_TERMINAL_FAILURES = {"blocked", "failed", "error", "interrupted", "rejected"}
_SYNTHETIC_STAGE_NAMES = {"blocked", "failed", "error", "interrupted", "rejected"}
_STAGE_LOCK = Lock()
_LAST_STAGE_BY_RUN: dict[str, str] = {}

_BACKEND_TO_UI_STAGE = {
    "record_running": "repository_evidence",
    "import_api": "repository_evidence",
    "validate_request": "repository_evidence",
    "start_snapshot_scanner": "repository_evidence",
    "collect_assessment": "repository_evidence",
    "classify_blocked_result": "repository_evidence",
    "wait_snapshot_scanner": "scanner_reconciliation",
    "attach_exact_scanner_evidence": "scanner_reconciliation",
    "enrich_scanner_evidence": "scanner_reconciliation",
    "apply_report_accuracy": "accuracy_review",
    "attach_review_target": "accuracy_review",
    "polish_result": "score_reconciliation",
    "finalize_consistency": "report_generation",
    "reattach_review_target": "report_generation",
    "attach_evidence_bundle": "truth_and_review_gates",
    "attach_client_acceptance": "truth_and_review_gates",
    "sanitize_response": "truth_and_review_gates",
    "validate_final_artifacts": "truth_and_review_gates",
    "persist_final_response": "truth_and_review_gates",
}
_UI_STAGES = {step for step, _label in express._EXPRESS_STAGE_DEFINITIONS}


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


def _stage_text(value: Any) -> str:
    return str(value or "").strip()


def _backend_stage(evidence: dict[str, Any] | None, remembered: str, supplied: str) -> str:
    evidence = evidence if isinstance(evidence, dict) else {}
    candidate = _stage_text(evidence.get("failure_stage") or evidence.get("backend_stage") or remembered)
    if candidate and candidate not in _SYNTHETIC_STAGE_NAMES:
        return candidate
    return supplied


def _ui_stage(backend_stage: str, supplied: str, remembered: str) -> str:
    for candidate in (backend_stage, remembered, supplied):
        if candidate in _UI_STAGES:
            return candidate
        mapped = _BACKEND_TO_UI_STAGE.get(candidate)
        if mapped:
            return mapped
    return "request_accepted"


def _decorate_terminal_progress(
    response: dict[str, Any],
    *,
    status: str,
    code: str,
    backend_stage: str,
    ui_stage: str,
    message: str,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if status not in _TERMINAL_FAILURES:
        return response

    failure_code = str(code or response.get("code") or "express_terminal_failure")[:80]
    safe_backend_stage = backend_stage or ui_stage
    terminal_evidence = dict(evidence or {})
    terminal_evidence.update(
        {
            "failure_stage": safe_backend_stage,
            "failure_ui_stage": ui_stage,
            "failure_code": failure_code,
            "terminal_status": status,
            "same_run_continuation": True,
        }
    )

    response["failure_stage"] = safe_backend_stage
    response["failure_ui_stage"] = ui_stage
    response["failure_code"] = failure_code
    response["current_stage"] = ui_stage
    response["progress"] = express._stage_progress(
        ui_stage,
        status,
        message,
        evidence=terminal_evidence,
    )
    return response


def install_express_failure_stage_truth_v3() -> dict[str, Any]:
    if getattr(express._response, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "actual_failure_stage_preserved": True,
            "backend_stage_mapped_to_ui_stage": True,
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
        normalized_status = _stage_text(status).lower()
        supplied_stage = _stage_text(stage)
        remembered = _last_stage(run_id)
        backend_stage = _backend_stage(evidence, remembered, supplied_stage)
        ui_stage = _ui_stage(backend_stage, supplied_stage, remembered)
        response_stage = ui_stage if normalized_status in _TERMINAL_FAILURES else supplied_stage

        result = original_response(
            run_id,
            payload,
            status,
            message,
            code=code,
            stage=response_stage,
            progress_percent=progress_percent,
            evidence=evidence,
        )
        return _decorate_terminal_progress(
            result,
            status=normalized_status,
            code=code,
            backend_stage=backend_stage,
            ui_stage=ui_stage,
            message=message,
            evidence=evidence,
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
        "backend_stage_mapped_to_ui_stage": True,
        "later_pending_stages_remain_pending": True,
        "safe_failure_code_exposed": True,
        "raw_exception_exposed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_BACKEND_TO_UI_STAGE",
    "_ui_stage",
    "install_express_failure_stage_truth_v3",
]
