from __future__ import annotations

import base64
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from nico.mid_assessment_approval import (
    get_mid_approved_report,
    mid_approval_status,
    request_mid_approval,
    transition_mid_approval,
)
from nico.mid_review_dispositions import (
    get_mid_review_dispositions,
    submit_mid_review_disposition,
)


class MidApprovalRequest(BaseModel):
    customer_id: str = "default_customer"
    project_id: str = "default_project"


class MidApprovalDecisionRequest(BaseModel):
    actor: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=4000)
    reviewed_item_ids: list[str] = Field(default_factory=list, max_length=500)


class MidReviewDispositionRequest(BaseModel):
    decision: str = Field(default="", max_length=64)
    actor: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=4000)


def _raise(result: dict[str, Any], default_message: str) -> None:
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": str(result.get("error") or default_message)})
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=403 if result.get("admin_write") else 409,
            detail={
                "status": "blocked",
                "message": str(result.get("error") or default_message),
                "validation": result.get("validation") or {},
                "review_dispositions": result.get("review_dispositions") or {},
                "missing_reviewed_item_ids": result.get("missing_reviewed_item_ids") or [],
                "unexpected_reviewed_item_ids": result.get("unexpected_reviewed_item_ids") or [],
            },
        )


def mid_approval_request_response(run_id: str, req: MidApprovalRequest, x_nico_admin_token: str = Header(default="")) -> dict[str, Any]:
    result = request_mid_approval(run_id, req.customer_id, req.project_id, admin_token=x_nico_admin_token)
    _raise(result, "Mid approval request was unavailable.")
    return result


def mid_approval_status_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = mid_approval_status(run_id, customer_id, project_id, admin_token=x_nico_admin_token)
    _raise(result, "Mid Assessment run not found.")
    return result


def mid_approval_decision_response(
    approval_id: str,
    state: str,
    req: MidApprovalDecisionRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = transition_mid_approval(
        approval_id,
        state,
        actor=req.actor,
        note=req.note,
        reviewed_item_ids=req.reviewed_item_ids,
        admin_token=x_nico_admin_token,
    )
    _raise(result, "Mid approval not found.")
    return result


def mid_review_dispositions_response(
    approval_id: str,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = get_mid_review_dispositions(approval_id, admin_token=x_nico_admin_token)
    _raise(result, "Mid approval not found.")
    return result


def mid_review_disposition_response(
    approval_id: str,
    item_id: str,
    req: MidReviewDispositionRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = submit_mid_review_disposition(
        approval_id,
        item_id,
        decision=req.decision,
        actor=req.actor,
        note=req.note,
        admin_token=x_nico_admin_token,
    )
    _raise(result, "Mid review exception not found.")
    return result


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    formats = report.get("formats") if isinstance(report.get("formats"), dict) else {}
    payload = formats.get("json") if isinstance(formats.get("json"), dict) else {}
    return {
        "status": report.get("status") or "unknown",
        "approval_status": report.get("approval_status") or "",
        "report_version": report.get("report_version") or "",
        "report_type": report.get("report_type") or "",
        "report_path": report.get("report_path") or "",
        "report_id": report.get("report_id") or "",
        "run_id": report.get("run_id") or "",
        "repository": report.get("repository") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "source_draft_report_id": report.get("source_draft_report_id") or "",
        "source_draft_pdf_sha256": report.get("source_draft_pdf_sha256") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "approval_id": report.get("approval_id") or "",
        "approved_by": report.get("approved_by") or "",
        "approved_at": report.get("approved_at") or "",
        "approval_identity_sha256": report.get("approval_identity_sha256") or "",
        "pdf_sha256": report.get("pdf_sha256") or "",
        "pdf_filename": report.get("pdf_filename") or "",
        "human_review_required": bool(report.get("human_review_required")),
        "approved": bool(report.get("approved")),
        "delivery_eligible": bool(report.get("delivery_eligible")),
        "client_delivery_allowed": False,
        "delivery_status": report.get("delivery_status") or "not_configured",
        "unsupported_claims_permitted": int(report.get("unsupported_claims_permitted") or 0),
        "delivery_note": payload.get("delivery_note") or "",
        "formats_available": {"json": bool(payload), "pdf": bool(formats.get("pdf"))},
        "rule": "This is a separate human-approved Mid artifact. Secure client delivery remains disabled until a dedicated delivery grant is created.",
    }


def mid_approved_report_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = get_mid_approved_report(run_id, customer_id, project_id, admin_token=x_nico_admin_token)
    _raise(result, "Approved Mid report not found.")
    return _public_report(result)


def mid_approved_report_pdf_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> Response:
    report = get_mid_approved_report(run_id, customer_id, project_id, admin_token=x_nico_admin_token)
    _raise(report, "Approved Mid report not found.")
    formats = report.get("formats") if isinstance(report.get("formats"), dict) else {}
    try:
        pdf = base64.b64decode(str(formats.get("pdf") or ""), validate=True)
    except Exception:
        raise HTTPException(status_code=409, detail={"status": "blocked", "message": "The approved Mid PDF failed decoding."})
    if not pdf.startswith(b"%PDF"):
        raise HTTPException(status_code=409, detail={"status": "blocked", "message": "The approved Mid PDF failed content verification."})
    filename = str(report.get("pdf_filename") or "nico-mid-assessment-APPROVED.pdf").replace('"', "")
    exposed = ", ".join([
        "Content-Disposition", "X-NICO-Report-ID", "X-NICO-PDF-SHA256", "X-NICO-Approval-ID",
        "X-NICO-Approval-Identity-SHA256", "X-NICO-Source-Draft-PDF-SHA256",
        "X-NICO-Review-Packet-SHA256", "X-NICO-Report-Path",
    ])
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-NICO-Report-ID": str(report.get("report_id") or ""),
            "X-NICO-PDF-SHA256": str(report.get("pdf_sha256") or ""),
            "X-NICO-Approval-ID": str(report.get("approval_id") or ""),
            "X-NICO-Approval-Identity-SHA256": str(report.get("approval_identity_sha256") or ""),
            "X-NICO-Source-Draft-PDF-SHA256": str(report.get("source_draft_pdf_sha256") or ""),
            "X-NICO-Review-Packet-SHA256": str(report.get("review_packet_sha256") or ""),
            "X-NICO-Report-Path": str(report.get("report_path") or ""),
            "Access-Control-Expose-Headers": exposed,
        },
    )


def register_mid_approval_routes(app: FastAPI) -> None:
    app.post("/assessment/mid-run/{run_id}/approval/request")(mid_approval_request_response)
    app.get("/assessment/mid-run/{run_id}/approval")(mid_approval_status_response)
    app.get("/assessment/mid-run/approval/{approval_id}/review-items")(mid_review_dispositions_response)
    app.post("/assessment/mid-run/approval/{approval_id}/review-items/{item_id}")(mid_review_disposition_response)
    app.post("/assessment/mid-run/approval/{approval_id}/{state}")(mid_approval_decision_response)
    app.get("/assessment/mid-run/{run_id}/report/approved")(mid_approved_report_response)
    app.get("/assessment/mid-run/{run_id}/report/approved/pdf")(mid_approved_report_pdf_response)


__all__ = [
    "MidApprovalRequest", "MidApprovalDecisionRequest", "MidReviewDispositionRequest",
    "mid_approval_request_response", "mid_approval_status_response", "mid_approval_decision_response",
    "mid_review_dispositions_response", "mid_review_disposition_response", "mid_approved_report_response",
    "mid_approved_report_pdf_response", "register_mid_approval_routes",
]
