from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from nico.admin_security import internal_admin_token
from nico.full_assessment_continuation import apply_full_assessment_continuation, plan_full_assessment_continuation
from nico.full_assessment_orchestrator import run_full_assessment_orchestration
from nico.mid_assessment_approval import request_mid_approval
from nico.mid_assessment_handlers import mid_assessment_handlers
from nico.mid_assessment_report import generate_mid_draft_report
from nico.mid_assessment_runs import (
    build_mid_status_payload,
    explicit_model_fields,
    persist_mid_assessment_run,
    persistence_metadata,
)
from nico.storage import STORE, new_id, utc_now

MID_ASSESSMENT_TYPE = "mid"
MID_REPORT_STATUS = "mid_report_generation_pending"


class MidAssessmentRunRequest(BaseModel):
    repository: str = ""
    target: str = ""
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    client_name: str = ""
    project_name: str = ""
    authorized_by: str = "requester_confirmation"
    authorization_scope: str = "repository assessment only"
    authorization_confirmed: bool = False
    authorized: bool = False
    timeframe_days: int = 180
    run_scanners: bool = True
    refresh_full_evidence: bool = True
    auto_continue: bool = True
    tools: list[str] = Field(default_factory=list)


class MidAssessmentStatusRequest(BaseModel):
    repository: str = ""
    target: str = ""
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    client_name: str = ""
    project_name: str = ""
    authorized_by: str = "mid_status_refresh"
    authorization_scope: str = "repository assessment only"
    authorization_confirmed: bool = True
    authorized: bool = True
    timeframe_days: int = 180
    run_scanners: bool = True
    refresh_full_evidence: bool = True
    auto_continue: bool = True
    tools: list[str] = Field(default_factory=list)


def _payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


def _evidence_from_progress(result: dict[str, Any]) -> dict[str, Any]:
    for item in result.get("progress") or []:
        if not isinstance(item, dict) or item.get("step") != "repo_evidence":
            continue
        return item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    return {}


def _attach_mid_evidence(result: dict[str, Any]) -> dict[str, Any]:
    evidence = _evidence_from_progress(result)
    for response_key, id_key in (
        ("repository_snapshot", "snapshot_id"),
        ("repository_evidence", "repository_evidence_id"),
        ("complexity_evidence", "complexity_evidence_id"),
    ):
        item_id = str(evidence.get(id_key) or "")
        record = STORE.get("evidence_items", item_id) if item_id else None
        value = record.get("evidence") if isinstance(record, dict) and isinstance(record.get("evidence"), dict) else {}
        result[response_key] = value
    return result


def _progress_status(result: dict[str, Any], step: str) -> str:
    for item in result.get("progress") or []:
        if isinstance(item, dict) and item.get("step") == step:
            return str(item.get("status") or "unknown")
    return "not_started"


def _set_progress_step(
    result: dict[str, Any],
    step: str,
    status: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    progress = [deepcopy(item) for item in result.get("progress") or [] if isinstance(item, dict)]
    replacement = {
        "step": step,
        "status": status,
        "message": message,
        "evidence": evidence or {},
    }
    for index, item in enumerate(progress):
        if item.get("step") == step:
            progress[index] = replacement
            result["progress"] = progress
            return
    progress.append(replacement)
    result["progress"] = progress


def _attach_mid_contract(result: dict[str, Any]) -> dict[str, Any]:
    result["assessment_type"] = MID_ASSESSMENT_TYPE
    result["service_tier"] = MID_ASSESSMENT_TYPE
    result["mode"] = MID_ASSESSMENT_TYPE
    result["unified_run"] = True
    result["express_report_generated"] = False
    result["full_report_generated"] = False
    result["report_generation_status"] = MID_REPORT_STATUS
    result["report_generation_note"] = (
        "This Mid run executes snapshot-bound collection, scanners, evidence attachment, and evidence-bound scoring in one run. "
        "After the core run is persisted, NICO automatically generates the dedicated Mid draft and creates its human-review request without generating or relabeling an Express or Full report."
    )
    result["execution_stages"] = [
        {
            "stage": 1,
            "id": "express_style_repository_mapping",
            "status": _progress_status(result, "repo_evidence"),
            "report_generated": False,
        },
        {
            "stage": 2,
            "id": "snapshot_bound_scanner_suite",
            "status": _progress_status(result, "scanner_worker"),
            "separate_run_created": False,
        },
        {
            "stage": 3,
            "id": "same_run_evidence_attachment_and_scoring",
            "status": _progress_status(result, "scoring"),
        },
        {
            "stage": 4,
            "id": "dedicated_mid_draft_and_review_request",
            "status": MID_REPORT_STATUS,
            "separate_report_path": "mid_run",
        },
    ]
    result["human_review_required"] = True
    result["client_ready"] = False

    assessment = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
    if assessment:
        assessment["assessment_type"] = MID_ASSESSMENT_TYPE
        assessment["service_tier"] = MID_ASSESSMENT_TYPE
        assessment["human_review_required"] = True
        assessment["client_ready"] = False
        result["assessment"] = assessment
        ledger = assessment.get("evidence_ledger") if isinstance(assessment.get("evidence_ledger"), dict) else {}
        truth_display = assessment.get("trust_report_display") if isinstance(assessment.get("trust_report_display"), dict) else {}
        export_gate = assessment.get("export_truth_gate") if isinstance(assessment.get("export_truth_gate"), dict) else {}
        result["evidence_ledger"] = ledger
        result["evidence_ledger_count"] = 1 if ledger else 0
        result["trust_level"] = assessment.get("trust_level") or truth_display.get("trust_level") or "Review-limited"
        result["client_delivery_status"] = assessment.get("client_delivery_status") or truth_display.get("client_delivery_status") or "Human Review Required"
        result["export_truth_gate"] = export_gate
    else:
        result["evidence_ledger"] = {}
        result["evidence_ledger_count"] = 0
    return result


def _record(result: dict[str, Any], payload: dict[str, Any], *, restored: bool) -> dict[str, Any]:
    metadata = persistence_metadata(restored=restored)
    result["persistence"] = metadata
    try:
        record = persist_mid_assessment_run(result, payload)
    except Exception:
        result["persistence"] = {
            "recorded": False,
            "durable": False,
            "adapter": metadata.get("adapter") or "unknown",
            "restored": restored,
            "note": "Mid-run state could not be recorded and must not be treated as restart-resumable.",
        }
        return result
    result["persistence"].update(
        {
            "record_id": record.get("run_id") or result.get("run_id"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }
    )
    return result


def _has_blocked_progress(result: dict[str, Any]) -> bool:
    return any(
        isinstance(item, dict) and item.get("status") == "blocked"
        for item in result.get("progress") or []
    )


def _blocked_detail(result: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "code": str(result.get("error") or "blocked")[:80],
        "message": message,
        "run_id": result.get("run_id") or "",
        "assessment_type": MID_ASSESSMENT_TYPE,
        "progress": result.get("progress") or [],
        "persistence": result.get("persistence") or {},
    }


def _server_admin_token() -> str:
    return internal_admin_token()


def _persist_artifact_summary(result: dict[str, Any]) -> None:
    run_id = str(result.get("run_id") or "")
    if not run_id:
        return
    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict):
        return
    updated = deepcopy(record)
    response = deepcopy(updated.get("response") if isinstance(updated.get("response"), dict) else {})
    for key in (
        "report_generation_status",
        "report_generation_note",
        "report_generation_error",
        "mid_report",
        "approval_request",
        "approval_request_status",
        "progress",
    ):
        if key in result:
            response[key] = deepcopy(result[key])
    updated["response"] = response
    updated["report_id"] = str(result.get("mid_report", {}).get("report_id") or updated.get("report_id") or "")
    updated["approval_id"] = str(result.get("approval_request", {}).get("approval_id") or updated.get("approval_id") or "")
    updated["updated_at"] = utc_now()
    STORE.put("assessment_runs", run_id, updated)


def _attach_automatic_mid_artifacts(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    run_id = str(result.get("run_id") or payload.get("run_id") or "")
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")
    admin_token = _server_admin_token()

    report = generate_mid_draft_report(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=admin_token,
    )
    if report.get("status") != "complete":
        message = str(report.get("error") or "Dedicated Mid draft generation was blocked.")
        result["report_generation_status"] = "blocked"
        result["report_generation_note"] = message
        result["report_generation_error"] = message
        _set_progress_step(result, "reports", "blocked", message)
        _set_progress_step(result, "approval_request", "not_started", "Human review request was not created because the Mid draft is unavailable.")
        _persist_artifact_summary(result)
        return result

    formats = report.get("formats") if isinstance(report.get("formats"), dict) else {}
    result["reports"] = {
        "markdown": str(formats.get("markdown") or ""),
        "html": str(formats.get("html") or ""),
        "pdf_base64": str(formats.get("pdf") or ""),
        "pdf_filename": str(report.get("pdf_filename") or "nico-mid-assessment-DRAFT.pdf"),
        "pdf_sha256": str(report.get("pdf_sha256") or ""),
    }
    result["mid_report"] = {
        "status": "complete",
        "draft_status": report.get("draft_status") or "human_review_required",
        "report_id": report.get("report_id") or "",
        "report_path": report.get("report_path") or "mid_run",
        "report_version": report.get("report_version") or "",
        "pdf_sha256": report.get("pdf_sha256") or "",
        "pdf_filename": report.get("pdf_filename") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    result["report_generation_status"] = "complete"
    result["report_generation_note"] = (
        "A professional snapshot-bound Mid draft report was generated automatically from this same run. "
        "It remains human-review-required and is not approved for client delivery."
    )
    result.pop("report_generation_error", None)
    _set_progress_step(
        result,
        "reports",
        "complete",
        "Dedicated Mid draft report generated automatically from the same run, snapshot, evidence ledger, and review packet.",
        {
            "report_id": report.get("report_id") or "",
            "report_path": report.get("report_path") or "mid_run",
            "pdf_sha256": report.get("pdf_sha256") or "",
            "pdf_filename": report.get("pdf_filename") or "",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )

    approval_result = request_mid_approval(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=admin_token,
    )
    approval = approval_result.get("approval") if isinstance(approval_result.get("approval"), dict) else {}
    if approval_result.get("status") == "requested" and approval:
        result["approval_request"] = approval
        result["approval_request_status"] = "pending"
        _set_progress_step(
            result,
            "approval_request",
            "complete",
            "Exact-state Mid human-review request created automatically; reviewer decision remains mandatory.",
            {
                "approval_id": approval.get("approval_id") or "",
                "status": approval.get("status") or "pending",
                "exception_item_count": approval.get("exception_item_count") or 0,
                "draft_report_id": approval.get("draft_report_id") or "",
                "human_approval_required": True,
                "client_delivery_allowed": False,
            },
        )
    else:
        message = str(approval_result.get("error") or "Mid human-review request could not be created.")
        result["approval_request"] = {}
        result["approval_request_status"] = "blocked"
        _set_progress_step(result, "approval_request", "blocked", message)

    for stage in result.get("execution_stages") or []:
        if isinstance(stage, dict) and stage.get("id") == "dedicated_mid_draft_and_review_request":
            stage["status"] = "complete"
            stage["report_id"] = result["mid_report"]["report_id"]
            stage["approval_id"] = result.get("approval_request", {}).get("approval_id") or ""
    _persist_artifact_summary(result)
    return result


def mid_assessment_response(req: MidAssessmentRunRequest) -> dict[str, Any]:
    payload = _payload(req)
    payload.update(
        {
            "run_id": new_id("midrun"),
            "mode": MID_ASSESSMENT_TYPE,
            "build_reports": False,
            "create_final_review_request": False,
        }
    )
    handlers = mid_assessment_handlers(int(payload.get("timeframe_days") or 180))
    result = run_full_assessment_orchestration(payload, handlers=handlers)
    result = _attach_mid_evidence(result)
    result = _attach_mid_contract(result)
    result = _record(result, payload, restored=False)
    if result.get("status") == "blocked" or _has_blocked_progress(result):
        raise HTTPException(status_code=400, detail=_blocked_detail(result, "Mid Assessment was blocked by authorization, repository access, or snapshot validation."))
    result = _attach_automatic_mid_artifacts(result, payload)
    return result


def mid_assessment_status_response(run_id: str, req: MidAssessmentStatusRequest) -> dict[str, Any]:
    if not str(run_id or "").startswith("midrun_"):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found."})
    request_payload = _payload(req)
    explicit = explicit_model_fields(req)
    payload, record = build_mid_status_payload(run_id, request_payload, explicit)
    if not record:
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found."})
    saved_request = dict(record.get("request") or {})
    auto_continue = bool(request_payload.get("auto_continue")) if "auto_continue" in explicit else bool(saved_request.get("auto_continue", True))
    plan = plan_full_assessment_continuation(payload, record, auto_continue=auto_continue)
    continuation = plan["payload"]
    continuation["mode"] = MID_ASSESSMENT_TYPE
    continuation["build_reports"] = False
    continuation["create_final_review_request"] = False
    handlers = mid_assessment_handlers(int(continuation.get("timeframe_days") or 180))
    result = run_full_assessment_orchestration(continuation, handlers=handlers)
    result = apply_full_assessment_continuation(result, plan)
    result["status_refresh"] = True
    result = _attach_mid_evidence(result)
    result = _attach_mid_contract(result)
    result = _record(result, continuation, restored=True)
    if result.get("status") == "blocked" or _has_blocked_progress(result):
        raise HTTPException(status_code=400, detail=_blocked_detail(result, "Mid Assessment status refresh was blocked by run or snapshot identity validation."))
    result = _attach_automatic_mid_artifacts(result, continuation)
    return result


def register_mid_assessment_routes(app: FastAPI) -> None:
    app.post("/assessment/mid-run")(mid_assessment_response)
    app.post("/assessment/mid-run/{run_id}/status")(mid_assessment_status_response)


__all__ = [
    "MID_ASSESSMENT_TYPE",
    "MID_REPORT_STATUS",
    "MidAssessmentRunRequest",
    "MidAssessmentStatusRequest",
    "mid_assessment_response",
    "mid_assessment_status_response",
    "register_mid_assessment_routes",
]
