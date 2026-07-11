from __future__ import annotations

import base64
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from nico.mid_assessment_report import generate_mid_draft_report
from nico.mid_assessment_runs import load_mid_assessment_run
from nico.storage import STORE


class MidDraftReportRequest(BaseModel):
    customer_id: str = "default_customer"
    project_id: str = "default_project"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    formats = report.get("formats") if isinstance(report.get("formats"), dict) else {}
    payload = formats.get("json") if isinstance(formats.get("json"), dict) else {}
    return {
        "status": report.get("status") or "unknown",
        "draft_status": report.get("draft_status") or "human_review_required",
        "report_version": report.get("report_version") or "",
        "report_type": report.get("report_type") or "",
        "report_path": report.get("report_path") or "",
        "report_id": report.get("report_id") or "",
        "run_id": report.get("run_id") or "",
        "customer_id": report.get("customer_id") or "default_customer",
        "project_id": report.get("project_id") or "default_project",
        "repository": report.get("repository") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "source_identity_sha256": report.get("source_identity_sha256") or "",
        "pdf_sha256": report.get("pdf_sha256") or "",
        "pdf_filename": report.get("pdf_filename") or "",
        "generated_at": report.get("generated_at") or "",
        "evidence_coverage": payload.get("evidence_coverage") or {},
        "executive_summary": payload.get("executive_summary") or {},
        "human_review_required": bool(report.get("human_review_required")),
        "approval_required": bool(report.get("approval_required")),
        "client_delivery_allowed": bool(report.get("client_delivery_allowed")),
        "approved": bool(report.get("approved")),
        "unsupported_claims_permitted": int(report.get("unsupported_claims_permitted") or 0),
        "idempotent_reuse": bool(report.get("idempotent_reuse")),
        "formats_available": {
            "json": bool(payload),
            "markdown": bool(formats.get("markdown")),
            "html": bool(formats.get("html")),
            "pdf": bool(formats.get("pdf")),
        },
        "rule": "This is a human-review-required Mid draft. Generating it does not approve the report or enable client delivery.",
    }


def _report_error(result: dict[str, Any]) -> None:
    if result.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail={"status": "not_found", "message": "Mid Assessment run not found."},
        )
    if result.get("status") == "blocked":
        status_code = 403 if result.get("admin_write") else 409
        raise HTTPException(
            status_code=status_code,
            detail={"status": "blocked", "message": str(result.get("error") or "Mid draft report generation was blocked.")},
        )


def mid_draft_report_response(
    run_id: str,
    req: MidDraftReportRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = generate_mid_draft_report(
        run_id,
        customer_id=req.customer_id,
        project_id=req.project_id,
        admin_token=x_nico_admin_token,
    )
    _report_error(result)
    return _public_report(result)


def mid_draft_report_pdf_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> Response:
    result = generate_mid_draft_report(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=x_nico_admin_token,
    )
    _report_error(result)
    formats = result.get("formats") if isinstance(result.get("formats"), dict) else {}
    try:
        pdf = base64.b64decode(str(formats.get("pdf") or ""), validate=True)
    except Exception:
        raise HTTPException(
            status_code=409,
            detail={"status": "blocked", "message": "The stored Mid draft PDF failed decoding."},
        )
    if not pdf.startswith(b"%PDF"):
        raise HTTPException(
            status_code=409,
            detail={"status": "blocked", "message": "The stored Mid draft PDF failed content verification."},
        )

    filename = str(result.get("pdf_filename") or "nico-mid-assessment-DRAFT.pdf").replace('"', "")
    exposed = ", ".join(
        [
            "Content-Disposition",
            "X-NICO-Report-ID",
            "X-NICO-PDF-SHA256",
            "X-NICO-Review-Packet-SHA256",
            "X-NICO-Source-Identity-SHA256",
            "X-NICO-Report-Path",
        ]
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-NICO-Report-ID": str(result.get("report_id") or ""),
            "X-NICO-PDF-SHA256": str(result.get("pdf_sha256") or ""),
            "X-NICO-Review-Packet-SHA256": str(result.get("review_packet_sha256") or ""),
            "X-NICO-Source-Identity-SHA256": str(result.get("source_identity_sha256") or ""),
            "X-NICO-Report-Path": str(result.get("report_path") or ""),
            "Access-Control-Expose-Headers": exposed,
        },
    )


def register_mid_report_routes(app: FastAPI) -> None:
    app.post("/assessment/mid-run/{run_id}/report/draft")(mid_draft_report_response)
    app.get("/assessment/mid-run/{run_id}/report/draft/pdf")(mid_draft_report_pdf_response)


__all__ = [
    "MidDraftReportRequest",
    "mid_draft_report_response",
    "mid_draft_report_pdf_response",
    "register_mid_report_routes",
]
