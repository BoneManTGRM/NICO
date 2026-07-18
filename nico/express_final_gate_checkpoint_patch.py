from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_final_gate_checkpoint.v1"
_FINALIZE_MARKER = "_nico_express_checkpoint_finalize_v1"
_STAGE_MARKER = "_nico_express_checkpoint_stage_v1"
_CHECKPOINTS: dict[str, dict[str, Any]] = {}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _usable_reports(result: dict[str, Any]) -> bool:
    reports = _record(result.get("reports"))
    return all(bool(str(reports.get(name) or "").strip()) for name in ("markdown", "html", "pdf_base64"))


def install_express_final_gate_checkpoint_patch() -> dict[str, Any]:
    """Persist generated reports and scores before slower final review gates.

    The async runner previously replaced the rich post-render result with a bare
    stage-only payload when entering ``truth_and_review_gates``. Status polling
    therefore saw ``report_ready=false`` and no score even though rendering had
    completed. This patch caches the exact-run post-render result and records it
    as the final-gate checkpoint without changing the backend terminal state.
    """

    from nico.api import main as api_main
    from nico import express_async_api

    current_finalize: Callable[[dict[str, Any]], dict[str, Any]] = api_main.finalize_express_result_consistency
    if not getattr(current_finalize, _FINALIZE_MARKER, False):
        @wraps(current_finalize)
        def finalize_with_checkpoint(result: dict[str, Any]) -> dict[str, Any]:
            output = current_finalize(result)
            if isinstance(output, dict):
                run_id = str(output.get("run_id") or result.get("run_id") or "").strip()
                if run_id:
                    _CHECKPOINTS[run_id] = deepcopy(output)
            return output

        setattr(finalize_with_checkpoint, _FINALIZE_MARKER, True)
        setattr(finalize_with_checkpoint, "_nico_previous", current_finalize)
        api_main.finalize_express_result_consistency = finalize_with_checkpoint

    current_stage = express_async_api._record_stage
    if not getattr(current_stage, _STAGE_MARKER, False):
        @wraps(current_stage)
        def record_stage_with_checkpoint(
            run_id: str,
            request_payload: dict[str, Any],
            stage: str,
            message: str,
            *,
            progress_percent: int | None = None,
            evidence: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            if stage != "truth_and_review_gates":
                return current_stage(
                    run_id,
                    request_payload,
                    stage,
                    message,
                    progress_percent=progress_percent,
                    evidence=evidence,
                )

            checkpoint = deepcopy(_CHECKPOINTS.get(run_id) or {})
            if not checkpoint:
                return current_stage(
                    run_id,
                    request_payload,
                    stage,
                    message,
                    progress_percent=progress_percent,
                    evidence=evidence,
                )

            checkpoint["status"] = "running"
            checkpoint["run_id"] = run_id
            checkpoint["assessment_type"] = "express"
            checkpoint["service_tier"] = "express"
            checkpoint["repository"] = str(request_payload.get("repository") or checkpoint.get("repository") or "")
            checkpoint["customer_id"] = str(request_payload.get("customer_id") or "default_customer")
            checkpoint["project_id"] = str(request_payload.get("project_id") or "default_project")
            checkpoint["current_stage"] = "truth_and_review_gates"
            checkpoint["progress_percent"] = max(94, int(progress_percent or 94))
            checkpoint["human_review_required"] = True
            checkpoint["client_ready"] = False
            checkpoint["persistence"] = express_async_api._persistence()
            checkpoint["progress"] = express_async_api._stage_progress(
                "truth_and_review_gates",
                "running",
                message,
                evidence={
                    **deepcopy(evidence or {}),
                    "rich_report_checkpoint_persisted": True,
                    "usable_report_artifacts": _usable_reports(checkpoint),
                    "same_run_continuation": True,
                },
            )
            checkpoint["updated_at"] = express_async_api.utc_now()
            express_async_api._record(run_id, request_payload, checkpoint)
            return checkpoint

        setattr(record_stage_with_checkpoint, _STAGE_MARKER, True)
        setattr(record_stage_with_checkpoint, "_nico_previous", current_stage)
        express_async_api._record_stage = record_stage_with_checkpoint

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "rich_report_checkpoint": True,
        "preserves_exact_run": True,
        "browser_terminalization_required": False,
    }


__all__ = ["PATCH_VERSION", "install_express_final_gate_checkpoint_patch"]
