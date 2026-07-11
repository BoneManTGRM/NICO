from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nico.full_assessment_orchestrator import default_full_assessment_handlers, run_full_assessment_orchestration
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


def _model_payload(req: BaseModel) -> dict[str, Any]:
    if hasattr(req, "model_dump"):
        return req.model_dump()  # type: ignore[attr-defined]
    return req.dict()


def _with_report_path(result: dict[str, Any]) -> dict[str, Any]:
    """Mark this response as the full-run path so it cannot be confused with Express output."""

    return apply_report_path_truth(result, FULL_RUN_REPORT_PATH)


def full_assessment_response(req: FullAssessmentRequest) -> dict[str, Any]:
    result = run_full_assessment_orchestration(_model_payload(req), handlers=default_full_assessment_handlers())
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=400,
            detail={
                "status": "blocked",
                "code": str(result.get("error") or "blocked")[:80],
                "message": "Request blocked by NICO safety, authorization, or review policy.",
                "progress": result.get("progress", []),
            },
        )
    return _with_report_path(result)


def full_assessment_status_response(run_id: str, req: FullAssessmentStatusRequest) -> dict[str, Any]:
    payload = _model_payload(req)
    payload["run_id"] = run_id
    payload["run_scanners"] = False if not payload.get("scan_id") else bool(payload.get("scan_id"))
    payload["build_reports"] = bool(payload.get("build_reports", False))
    payload["create_final_review_request"] = bool(payload.get("create_final_review_request", False))
    result = run_full_assessment_orchestration(payload, handlers=default_full_assessment_handlers())
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=400,
            detail={
                "status": "blocked",
                "code": str(result.get("error") or "blocked")[:80],
                "message": "Status refresh blocked by NICO safety, authorization, or review policy.",
                "progress": result.get("progress", []),
            },
        )
    result["status_refresh"] = True
    return _with_report_path(result)


def register_full_assessment_routes(app: FastAPI) -> None:
    app.post("/assessment/full-run")(full_assessment_response)
    app.post("/assessment/full-run/{run_id}/status")(full_assessment_status_response)
