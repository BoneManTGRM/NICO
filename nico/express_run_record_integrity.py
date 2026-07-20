from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico.express_production_certification_v25 import build_express_production_certification

PATCH_VERSION = "nico.express_run_record_integrity.v6"
_PATCH_MARKER = "_nico_express_run_record_integrity_v1"
_TERMINAL_SUCCESS = {"complete", "completed"}
_TERMINAL_FAILURE = {"blocked", "failed", "error", "interrupted", "rejected"}
_RICH_FIELDS = (
    "repository",
    "repository_full_name",
    "commit_sha",
    "snapshot_sha",
    "assessed_commit_sha",
    "run_id",
    "assessment_run_id",
    "reports",
    "sections",
    "maturity_signal",
    "technical_score",
    "assessment_completion",
    "express_completion",
    "express_cross_format_contract",
    "express_pdf_renderer_truth",
    "express_pdf_bar_geometry",
    "express_pdf_page_layout",
    "express_visual_qa",
    "express_pdf_pagination",
    "express_artifact_manifest",
    "express_production_certification",
    "same_sha_verification_runs",
    "express_locale_parity",
    "restart_retrieval_proof",
    "production_restart_proof",
    "production_deployment",
    "production_release_provider_evidence",
    "evidence_artifact_bundle",
    "evidence_ledger",
    "client_acceptance",
    "persistence_truth",
    "storage_truth",
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


def _status_is(value: Any, allowed: set[str]) -> bool:
    return str(value or "").strip().casefold() in allowed


def _terminal_contract(output: dict[str, Any]) -> dict[str, Any]:
    reports = output.get("reports") if isinstance(output.get("reports"), dict) else {}
    cross_format = output.get("express_cross_format_contract") if isinstance(output.get("express_cross_format_contract"), dict) else {}
    renderer = output.get("express_pdf_renderer_truth") if isinstance(output.get("express_pdf_renderer_truth"), dict) else {}
    geometry = output.get("express_pdf_bar_geometry") if isinstance(output.get("express_pdf_bar_geometry"), dict) else {}
    layout = output.get("express_pdf_page_layout") if isinstance(output.get("express_pdf_page_layout"), dict) else {}
    visual_qa = output.get("express_visual_qa") if isinstance(output.get("express_visual_qa"), dict) else {}
    pagination = output.get("express_pdf_pagination") if isinstance(output.get("express_pdf_pagination"), dict) else {}

    required = {
        "progress_100": int(output.get("progress_percent") or 0) == 100,
        "stage_complete": _status_is(output.get("current_stage"), {"complete"}),
        "report_generation_complete": _status_is(output.get("report_generation_status"), {"complete"}),
        "pdf_present": _nonempty(reports.get("pdf_base64")),
        "markdown_present": _nonempty(reports.get("markdown")),
        "html_present": _nonempty(reports.get("html")),
        "cross_format_contract_present": bool(cross_format),
        "cross_format_complete": _status_is(cross_format.get("status"), {"complete"}),
        "renderer_contract_present": bool(renderer),
        "renderer_complete": _status_is(renderer.get("status"), {"complete"}),
        "vector_geometry_present": bool(geometry),
        "vector_geometry_verified": geometry.get("render_mode") == "reportlab_vector_geometry" and bool(geometry.get("verification_samples")),
        "page_layout_present": bool(layout),
        "page_layout_complete": _status_is(layout.get("status"), {"complete"}),
        "visual_qa_present": bool(visual_qa),
        "visual_qa_passed": _status_is(visual_qa.get("status"), {"pass", "complete"}),
        "pagination_present": bool(pagination),
        "pagination_complete": _status_is(pagination.get("status"), {"complete"}),
    }
    missing = [name for name, passed in required.items() if not passed]
    return {
        "status": "complete" if not missing else "degraded",
        "version": PATCH_VERSION,
        "checks": required,
        "missing_requirements": missing,
        "fail_closed": True,
        "durable_terminal_record_required": True,
        "restart_retrieval_required": True,
        "production_deployment_sha_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def reconcile_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
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
            "client_delivery_block_reason",
            "express_terminal_contract",
            "express_production_certification",
        ):
            if field in prior:
                output[field] = deepcopy(prior[field])
        output["status_regression_prevented"] = True

    status = str(output.get("status") or incoming_status or prior_status).lower()
    if status in _TERMINAL_SUCCESS:
        output["status"] = "complete"
        output["current_stage"] = "complete"
        output["progress_percent"] = 100
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False
        output["delivery_status"] = "blocked_pending_human_review"
        output["express_terminal_contract"] = _terminal_contract(output)
        certification = build_express_production_certification(output)
        if output["express_terminal_contract"]["status"] != "complete" or certification["status"] != "complete":
            output["client_delivery_block_reason"] = (
                "Express production proof is incomplete; terminal artifacts, deployment identity, durable restart retrieval, "
                "same-SHA repeatability, English/Spanish parity, or artifact-manifest integrity remain unverified."
            )
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
        "immutable_run_identity_preserved": True,
        "failed_complete_stage_contradictions_repaired": True,
        "terminal_artifact_contract_recorded": True,
        "production_certification_recorded": True,
        "five_production_gates_required": True,
        "missing_terminal_proof_fails_closed": True,
        "restart_retrieval_required": True,
        "production_deployment_sha_required": True,
        "human_review_boundary_preserved": True,
    }


__all__ = ["PATCH_VERSION", "install_express_run_record_integrity", "reconcile_record"]
