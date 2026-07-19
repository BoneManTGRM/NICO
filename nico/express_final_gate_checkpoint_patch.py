from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_final_gate_checkpoint.v3"
_FINALIZE_MARKER = "_nico_express_checkpoint_finalize_v1"
_STAGE_MARKER = "_nico_express_checkpoint_stage_v2"
_RELEASE_MARKER = "_nico_express_checkpoint_release_v1"
_CHECKPOINTS: dict[str, dict[str, Any]] = {}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _usable_reports(result: dict[str, Any]) -> bool:
    reports = _record(result.get("reports"))
    return all(bool(str(reports.get(name) or "").strip()) for name in ("markdown", "html", "pdf_base64"))


def _discard_checkpoint(run_id: str) -> None:
    _CHECKPOINTS.pop(str(run_id or "").strip(), None)


def _stored_response(express_async_api: Any, run_id: str) -> dict[str, Any]:
    record = express_async_api.STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict):
        return {}
    value = record.get("response") if isinstance(record.get("response"), dict) else record.get("payload")
    return deepcopy(value) if isinstance(value, dict) else {}


def _stored_request(express_async_api: Any, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
    record = express_async_api.STORE.get("assessment_runs", run_id)
    if isinstance(record, dict) and isinstance(record.get("request"), dict):
        return deepcopy(record["request"])
    return {
        "repository": str(result.get("repository") or ""),
        "customer_id": str(result.get("customer_id") or "default_customer"),
        "project_id": str(result.get("project_id") or "default_project"),
        "authorized": True,
        "authorization_confirmed": True,
    }


def _persist_post_render_checkpoint(express_async_api: Any, run_id: str, output: dict[str, Any]) -> None:
    """Write rich report truth before entering any slower final-gate operation.

    The final gate may be interrupted by a worker restart, deployment, or storage
    adapter failure. Persisting the post-render result immediately prevents the
    authoritative exact-run record from remaining a bare 96% stage projection
    with report_ready=false after Markdown, HTML, and PDF were already generated.
    """

    request_payload = _stored_request(express_async_api, run_id, output)
    checkpoint = deepcopy(output)
    checkpoint["status"] = "running"
    checkpoint["run_id"] = run_id
    checkpoint["assessment_type"] = "express"
    checkpoint["service_tier"] = "express"
    checkpoint["repository"] = str(request_payload.get("repository") or checkpoint.get("repository") or "")
    checkpoint["customer_id"] = str(request_payload.get("customer_id") or "default_customer")
    checkpoint["project_id"] = str(request_payload.get("project_id") or "default_project")
    checkpoint["current_stage"] = "report_generation"
    checkpoint["progress_percent"] = max(94, int(checkpoint.get("progress_percent") or 94))
    checkpoint["human_review_required"] = True
    checkpoint["client_ready"] = False
    checkpoint["client_delivery_allowed"] = False
    checkpoint["persistence"] = express_async_api._persistence()
    checkpoint["post_render_checkpoint"] = {
        "version": PATCH_VERSION,
        "durably_written_before_final_gate": True,
        "usable_report_artifacts": _usable_reports(checkpoint),
        "score_present": checkpoint.get("technical_score") is not None or bool(_record(checkpoint.get("maturity_signal"))),
        "sections_present": bool(checkpoint.get("sections")),
    }
    checkpoint["updated_at"] = express_async_api.utc_now()
    express_async_api._record(run_id, request_payload, checkpoint)


def install_express_final_gate_checkpoint_patch() -> dict[str, Any]:
    """Persist generated reports and scores before slower final review gates."""

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
                    _persist_post_render_checkpoint(express_async_api, run_id, output)
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

            checkpoint = deepcopy(_CHECKPOINTS.pop(run_id, None) or {})
            if not checkpoint:
                checkpoint = _stored_response(express_async_api, run_id)
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
            checkpoint["client_delivery_allowed"] = False
            checkpoint["persistence"] = express_async_api._persistence()
            checkpoint["progress"] = express_async_api._stage_progress(
                "truth_and_review_gates",
                "running",
                message,
                evidence={
                    **deepcopy(evidence or {}),
                    "rich_report_checkpoint_persisted": True,
                    "durable_checkpoint_recovered": bool(checkpoint.get("post_render_checkpoint")),
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

    current_release = express_async_api._release_active
    if not getattr(current_release, _RELEASE_MARKER, False):
        @wraps(current_release)
        def release_with_checkpoint_cleanup(run_id: str, request_payload: dict[str, Any]) -> None:
            try:
                current_release(run_id, request_payload)
            finally:
                _discard_checkpoint(run_id)

        setattr(release_with_checkpoint_cleanup, _RELEASE_MARKER, True)
        setattr(release_with_checkpoint_cleanup, "_nico_previous", current_release)
        express_async_api._release_active = release_with_checkpoint_cleanup

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "rich_report_checkpoint": True,
        "preserves_exact_run": True,
        "browser_terminalization_required": False,
        "checkpoint_consumed_once": True,
        "terminal_checkpoint_cleanup": True,
        "post_render_checkpoint_persisted_before_final_gate": True,
        "durable_checkpoint_recovery": True,
    }


__all__ = ["PATCH_VERSION", "install_express_final_gate_checkpoint_patch"]
