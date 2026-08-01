from __future__ import annotations

from typing import Any, Callable

import nico.express_async_api as express
import nico.express_backend_diagnostics as diagnostics

VERSION = "nico.express_failure_stage_truth.v1"
_PATCH_MARKER = "_nico_express_failure_stage_truth_v1"

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


def failure_ui_stage(backend_stage: str) -> str:
    """Return the last meaningful customer-visible stage for a backend failure."""

    return _BACKEND_TO_UI_STAGE.get(str(backend_stage or ""), "repository_evidence")


def install_express_failure_stage_truth_v1() -> dict[str, Any]:
    """Keep terminal status separate from the workflow stage that actually failed."""

    current: Callable[[str, dict[str, Any], str, BaseException], dict[str, Any]] = (
        diagnostics._diagnostic_failure
    )
    if bool(getattr(current, _PATCH_MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "terminal_status_preserved": True,
            "failure_ui_stage_preserved": True,
            "backend_failure_stage_preserved": True,
        }

    def diagnostic_failure(
        run_id: str,
        request_payload: dict[str, Any],
        stage: str,
        exc: BaseException,
    ) -> dict[str, Any]:
        failure = current(run_id, request_payload, stage, exc)
        backend_stage = str(failure.get("failure_stage") or diagnostics._safe_stage(stage))
        ui_stage = failure_ui_stage(backend_stage)
        message = (
            f"Express assessment execution failed during {backend_stage}. "
            f"Diagnostic ID {failure.get('diagnostic_id') or 'unavailable'}; "
            f"exception class {failure.get('exception_class') or 'BackendException'}. "
            "Internal exception text remains redacted. Review authorized backend logs before retrying."
        )
        evidence = {
            "failure_stage": backend_stage,
            "failure_ui_stage": ui_stage,
            "diagnostic_id": str(failure.get("diagnostic_id") or ""),
            "exception_class": str(failure.get("exception_class") or "BackendException"),
            "diagnostic_recorded_at": str(failure.get("diagnostic_recorded_at") or ""),
            "diagnostic_run_id": str(failure.get("diagnostic_run_id") or run_id),
        }
        failure["status"] = "failed"
        failure["current_stage"] = ui_stage
        failure["failure_stage"] = backend_stage
        failure["failure_ui_stage"] = ui_stage
        failure["progress_percent"] = 100
        failure["progress"] = express._stage_progress(
            ui_stage,
            "failed",
            message,
            evidence=evidence,
        )
        return diagnostics._attach_failure_stage(failure, backend_stage)

    setattr(diagnostic_failure, _PATCH_MARKER, True)
    setattr(diagnostic_failure, "_nico_previous", current)
    diagnostics._diagnostic_failure = diagnostic_failure
    return {
        "status": "installed",
        "version": VERSION,
        "terminal_status_preserved": True,
        "failure_ui_stage_preserved": True,
        "backend_failure_stage_preserved": True,
        "private_exception_text_exposed": False,
        "replacement_run_allowed": False,
    }


__all__ = [
    "VERSION",
    "failure_ui_stage",
    "install_express_failure_stage_truth_v1",
]
