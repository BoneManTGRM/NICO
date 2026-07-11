from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nico.full_assessment_continuation import (
    apply_full_assessment_continuation,
    plan_full_assessment_continuation,
)
from nico.full_assessment_orchestrator import default_full_assessment_handlers, run_full_assessment_orchestration
from nico.full_assessment_runs import (
    build_status_payload,
    explicit_model_fields,
    persist_full_assessment_run,
    persistence_metadata,
)
from nico.report_path_truth import apply_report_path_truth

FULL_RUN_REPORT_PATH = "full_run"
FULL_RUN_REPORT_LABEL = "Full Assessment"


class FullAssessmentRequest(BaseModel):
    target: str = ""
    repository: str = ""
    scan_id: str = ""
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    client_name: str = ""
    project_name: str = ""
    authorized_by: str = "unspecified"
    authorization_confirmed: bool = False
    authorized: bool = False
    mode: str = "express"
    run_scanners: bool = True
    refresh_full_evidence: bool = True
    build_reports: bool = True
    create_final_review_request: bool = True
    auto_continue: bool = True
    tools: list[str] = []


class FullAssessmentStatusRequest(BaseModel):
    repository: str = ""
    target: str = ""
    scan_id: str = ""
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    client_name: str = ""
    project_name: str = ""
    authorized_by: str = "frontend_reviewer"
    authorization_confirmed: bool = True
    authorized: bool = True
    mode: str = "express"
    build_reports: bool = False
    create_final_review_request: bool = False
    auto_continue: bool = True


def _model_payload(req: BaseModel) -> dict[str, Any]:
    if hasattr(req, "model_dump"):
        return req.model_dump()  # type: ignore[attr-defined]
    return req.dict()


def _with_report_path(result: dict[str, Any]) -> dict[str, Any]:
    """Mark this response as the full-run path so it cannot be confused with Express output."""

    return apply_report_path_truth(result, FULL_RUN_REPORT_PATH)


def _record_result(result: dict[str, Any], payload: dict[str, Any], *, restored: bool) -> dict[str, Any]:
    metadata = persistence_metadata(restored=restored)
    result["persistence"] = metadata
    try:
        record = persist_full_assessment_run(result, payload)
    except Exception:  # pragma: no cover - defensive storage boundary
        result["persistence"] = {
            "recorded": False,
            "durable": False,
            "adapter": metadata.get("adapter") or "unknown",
            "restored": restored,
            "note": "Full-run state could not be recorded; the assessment response remains available but must not be treated as restart-resumable.",
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


def _blocked_detail(result: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "code": str(result.get("error") or "blocked")[:80],
        "message": message,
        "run_id": result.get("run_id") or "",
        "progress": result.get("progress", []),
        "persistence": result.get("persistence", {}),
    }


def full_assessment_response(req: FullAssessmentRequest) -> dict[str, Any]:
    payload = _model_payload(req)
    result = run_full_assessment_orchestration(payload, handlers=default_full_assessment_handlers())
    result = _with_report_path(result)
    result = _record_result(result, payload, restored=False)
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=400,
            detail=_blocked_detail(result, "Request blocked by NICO safety, authorization, or review policy."),
        )
    return result


def full_assessment_status_response(run_id: str, req: FullAssessmentStatusRequest) -> dict[str, Any]:
    request_payload = _model_payload(req)
    payload, record = build_status_payload(run_id, request_payload, explicit_model_fields(req))
    plan = plan_full_assessment_continuation(
        payload,
        record,
        auto_continue=bool(request_payload.get("auto_continue", True)),
    )
    continuation_payload = plan["payload"]
    result = run_full_assessment_orchestration(continuation_payload, handlers=default_full_assessment_handlers())
    result = apply_full_assessment_continuation(result, plan)
    result["status_refresh"] = True
    result = _with_report_path(result)
    result = _record_result(result, continuation_payload, restored=bool(record))
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=400,
            detail=_blocked_detail(result, "Status refresh blocked by NICO safety, authorization, or review policy."),
        )
    return result


def register_full_assessment_routes(app: FastAPI) -> None:
    app.post("/assessment/full-run")(full_assessment_response)
    app.post("/assessment/full-run/{run_id}/status")(full_assessment_status_response)
