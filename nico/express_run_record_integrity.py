from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_run_record_integrity.v3"
_PATCH_MARKER = "_nico_express_run_record_integrity_v1"
_TERMINAL_SUCCESS = {"complete", "completed"}
_TERMINAL_FAILURE = {"blocked", "failed", "error", "interrupted", "rejected"}
_RICH_FIELDS = (
    "reports",
    "sections",
    "maturity_signal",
    "technical_score",
    "assessment_completion",
    "express_completion",
    "express_cross_format_contract",
    "express_pdf_renderer_truth",
    "express_visual_qa",
    "evidence_artifact_bundle",
    "evidence_ledger",
    "client_acceptance",
)


def _response(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    value = record.get("response") if isinstance(record.get("response"), dict) else record.get("payload")
    return deepcopy(value) if isinstance(value, dict) else {}


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return value is not None


def _terminal_contract(output: dict[str, Any]) -> dict[str, Any]:
    reports = output.get("reports") if isinstance(output.get("reports"), dict) else {}
    cross_format = output.get("express_cross_format_contract") if isinstance(output.get("express_cross_format_contract"), dict) else {}
    renderer = output.get("express_pdf_renderer_truth") if isinstance(output.get("express_pdf_renderer_truth"), dict) else {}
    visual_qa = output.get("express_visual_qa") if isinstance(output.get("express_visual_qa"), dict) else {}
    required = {
        "progress_100": int(output.get("progress_percent") or 0) == 100,
        "stage_complete": str(output.get("current_stage") or "").lower() == "complete",
        "report_generation_complete": str(output.get("report_generation_status") or "complete").lower() == "complete",
        "pdf_present": _nonempty(reports.get("pdf_base64")),
        "markdown_present": _nonempty(reports.get("markdown")),
        "html_present": _nonempty(reports.get("html")),
        "cross_format_not_degraded": not cross_format or cross_format.get("status") == "complete",
        "renderer_not_degraded": not renderer or renderer.get("status") == "complete",
        "visual_qa_not_failed": not visual_qa or visual_qa.get("status") in {"pass", "complete"},
    }
    missing = [name for name, passed in required.items() if not passed]
    return {
        "status": "complete" if not missing else "degraded",
        "version": PATCH_VERSION,
        "checks": required,
        "missing_requirements": missing,
        "durable_terminal_record_required": True,
        "restart_retrieval_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def reconcile_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Preserve exact-run terminal truth and rich completion evidence.

    Heartbeats, stage projections, and late compatibility wrappers may arrive
    after a richer record. They may add evidence, but cannot revive a terminal
    run, erase generated artifacts, or claim a complete stage for a failed run.
    """

    output = deepcopy(incoming)
    prior = _response(existing)
    prior_status = str(prior.get("status") or existing.get("status") or "").lower()
    incoming_status = str(output.get("status") or "").lower()

    for field in _RICH_FIELDS:
        if not _nonempty(output.get(field)) and _nonempty(prior.get(field)):
            output[field] = deepcopy(prior[field])

    if prior_status in _TERMINAL_SUCCESS and incoming_status not in _TERMINAL_SUCCESS:
        for field in (
            "status",
            "current_stage",
            "progress_percent",
            "report_generation_status",
            "human_review_required",
            "client_ready",
            "client_delivery_allowed",
            "delivery_status",
        ):
            if field in prior:
                output[field] = deepcopy(prior[field])
        output["status_regression_prevented"] = True

    status = str(output.get("status") or incoming_status or prior_status).lower()
    if status in _TERMINAL_SUCCESS:
        output["status"] = "complete"
        output["current_stage"] = "complete"
        output["progress_percent"] = 100
        output["report_generation_status"] = "complete"
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False
        output["delivery_status"] = "blocked_pending_human_review"
        output["express_terminal_contract"] = _terminal_contract(output)
        if output["express_terminal_contract"]["status"] != "complete":
            output["client_delivery_block_reason"] = "Express terminal evidence contract is incomplete; exact-run artifacts or cross-format validation are missing."
    elif status in _TERMINAL_FAILURE:
        if str(output.get("current_stage") or "").lower() == "complete":
            output["current_stage"] = status if status in {"blocked", "failed", "interrupted"} else "failed"
            output["terminal_stage_contradiction_repaired"] = True
        output["progress_percent"] = 100
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False

    return output


def install_express_run_record_integrity() -> dict[str, Any]:
    from nico import express_async_api
    from nico.express_final_gate_heartbeat import install_express_final_gate_heartbeat
    from nico.storage import STORE

    current: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]] = express_async_api._record
    record_status = "already_installed"
    if not getattr(current, _PATCH_MARKER, False):
        @wraps(current)
        def integrity_record(run_id: str, request_payload: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
            existing = STORE.get("assessment_runs", run_id) or {}
            reconciled = reconcile_record(existing if isinstance(existing, dict) else {}, response)
            return current(run_id, request_payload, reconciled)

        setattr(integrity_record, _PATCH_MARKER, True)
        setattr(integrity_record, "_nico_previous", current)
        express_async_api._record = integrity_record
        record_status = "installed"

    final_gate_heartbeat = install_express_final_gate_heartbeat()
    return {
        "status": "installed" if record_status == "installed" or final_gate_heartbeat.get("status") == "installed" else "already_installed",
        "version": PATCH_VERSION,
        "record_integrity": record_status,
        "final_gate_heartbeat": final_gate_heartbeat,
        "terminal_status_regression_prevented": True,
        "rich_completion_fields_preserved": True,
        "failed_complete_stage_contradictions_repaired": True,
        "terminal_artifact_contract_recorded": True,
        "restart_retrieval_required": True,
        "human_review_boundary_preserved": True,
    }


__all__ = ["PATCH_VERSION", "install_express_run_record_integrity", "reconcile_record"]
