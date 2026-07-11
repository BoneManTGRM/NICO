from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nico.full_assessment_orchestrator import default_full_assessment_handlers, run_full_assessment_orchestration


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


def full_assessment_response(req: FullAssessmentRequest) -> dict[str, Any]:
    result = run_full_assessment_orchestration(req.model_dump(), handlers=default_full_assessment_handlers())
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
    return result


def register_full_assessment_routes(app: FastAPI) -> None:
    app.post("/assessment/full-run")(full_assessment_response)
