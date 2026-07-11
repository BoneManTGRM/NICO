from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nico.full_assessment_orchestrator import default_full_assessment_handlers, run_full_assessment_orchestration

FULL_RUN_REPORT_PATH = "full_run"
FULL_RUN_REPORT_LABEL = "Full Assessment"
FULL_RUN_MARKDOWN_BANNER = "> Report path: Full Assessment (`full_run`). This is not Express Assessment output.\n\n"
FULL_RUN_HTML_BANNER = (
    '<aside data-nico-report-path="full_run" style="margin:12px 0;padding:12px;border:1px solid #38bdf8;'
    'border-radius:10px;background:#e0f2fe;color:#0c4a6e;font-weight:700">'
    'Report path: Full Assessment (<code>full_run</code>). This is not Express Assessment output.'
    '</aside>'
)


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


def _label_markdown(markdown: Any) -> Any:
    if not isinstance(markdown, str) or not markdown.strip():
        return markdown
    if "Report path: Full Assessment" in markdown:
        return markdown
    return FULL_RUN_MARKDOWN_BANNER + markdown


def _label_html(html: Any) -> Any:
    if not isinstance(html, str) or not html.strip():
        return html
    if 'data-nico-report-path="full_run"' in html:
        return html
    lower = html.lower()
    body_index = lower.find("<body")
    if body_index >= 0:
        close_index = html.find(">", body_index)
        if close_index >= 0:
            return html[: close_index + 1] + FULL_RUN_HTML_BANNER + html[close_index + 1 :]
    return FULL_RUN_HTML_BANNER + html


def _with_report_path(result: dict[str, Any]) -> dict[str, Any]:
    """Mark this response as the full-run path so it cannot be confused with Express output."""

    result["report_path"] = FULL_RUN_REPORT_PATH
    result["report_path_label"] = FULL_RUN_REPORT_LABEL
    reports = result.get("reports")
    if isinstance(reports, dict):
        reports["report_path"] = FULL_RUN_REPORT_PATH
        reports["report_path_label"] = FULL_RUN_REPORT_LABEL
        reports["markdown"] = _label_markdown(reports.get("markdown"))
        reports["html"] = _label_html(reports.get("html"))
    assessment = result.get("assessment")
    if isinstance(assessment, dict):
        assessment["report_path"] = FULL_RUN_REPORT_PATH
        assessment["report_path_label"] = FULL_RUN_REPORT_LABEL
    return result


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
