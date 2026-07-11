from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from nico.approved_delivery_access import (
    create_approved_delivery_access,
    inspect_approved_delivery_access,
    list_approved_delivery_access,
    redeem_approved_delivery_access,
    revoke_approved_delivery_access,
)
from nico.approved_delivery_receipts import create_delivery_receipt, list_delivery_receipts
from nico.approved_delivery_recovery import approved_delivery_status, attach_verified_approved_delivery
from nico.full_assessment_continuation import (
    apply_full_assessment_continuation,
    plan_full_assessment_continuation,
)
from nico.full_assessment_idempotent_handlers import idempotent_full_assessment_handlers
from nico.full_assessment_orchestrator import run_full_assessment_orchestration
from nico.full_assessment_runs import (
    build_status_payload,
    explicit_model_fields,
    persist_full_assessment_run,
    persistence_metadata,
)
from nico.report_path_truth import apply_report_path_truth
from nico.reports import get_report

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
    timeframe_days: int = 180
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
    timeframe_days: int = 180
    build_reports: bool = False
    create_final_review_request: bool = False
    auto_continue: bool = True


class ApprovedDeliveryAccessRequest(BaseModel):
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    report_id: str = ""
    recipient_label: str = ""
    created_by: str = "human_reviewer"
    expires_in_hours: int = 24
    max_downloads: int = 1


class ApprovedDeliveryAccessRevokeRequest(BaseModel):
    actor: str = "admin"


class ApprovedDeliveryTokenRequest(BaseModel):
    token: str = ""


def _model_payload(req: BaseModel) -> dict[str, Any]:
    if hasattr(req, "model_dump"):
        return req.model_dump()  # type: ignore[attr-defined]
    return req.dict()


def _with_report_path(result: dict[str, Any]) -> dict[str, Any]:
    """Mark this response as the full-run path so it cannot be confused with Express output."""

    return apply_report_path_truth(result, FULL_RUN_REPORT_PATH)


def _attach_repository_evidence(result: dict[str, Any]) -> dict[str, Any]:
    for item in result.get("progress") or []:
        if not isinstance(item, dict) or item.get("step") != "repo_evidence":
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        bundle = evidence.get("repository_evidence") if isinstance(evidence.get("repository_evidence"), dict) else {}
        if bundle:
            result["repository_evidence"] = bundle
            return result
    result.setdefault("repository_evidence", {"status": "not_attached", "run_id": result.get("run_id") or ""})
    return result


def _attach_assessment_truth_summary(result: dict[str, Any]) -> dict[str, Any]:
    assessment = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
    ledger = assessment.get("evidence_ledger") if isinstance(assessment.get("evidence_ledger"), dict) else {}
    display = assessment.get("trust_report_display") if isinstance(assessment.get("trust_report_display"), dict) else {}
    gate = assessment.get("export_truth_gate") if isinstance(assessment.get("export_truth_gate"), dict) else {}
    if not ledger and not display and not gate:
        return result

    result["trust_level"] = assessment.get("trust_level") or display.get("trust_level") or "Review-limited"
    result["client_delivery_status"] = assessment.get("client_delivery_status") or display.get("client_delivery_status") or "Human Review Required"
    result["evidence_ledger"] = ledger
    result["trust_report_display"] = display
    result["export_truth_gate"] = gate
    result["delivery_verdict"] = "human_review_required"
    result["human_review_required"] = True
    result["client_ready"] = False
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    if reports:
        reports.setdefault("trust_level", result["trust_level"])
        reports.setdefault("client_delivery_allowed", False)
        reports.setdefault("human_review_required", True)
        reports.setdefault("evidence_ledger_status", str(ledger.get("status") or "missing"))
        reports.setdefault("export_truth_gate", gate)
    return result


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


def _attach_persisted_delivery(result: dict[str, Any]) -> dict[str, Any]:
    return attach_verified_approved_delivery(result, include_pdf=True)


def _admin_access_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "blocked":
        status_code = 403 if result.get("admin_write") else 400
        raise HTTPException(
            status_code=status_code,
            detail={"status": "blocked", "message": str(result.get("error") or "Approved-delivery access action was blocked.")},
        )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Approved-delivery access record not found."})
    return result


def _admin_receipt_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "blocked":
        status_code = 403 if result.get("admin_write") else 400
        raise HTTPException(
            status_code=status_code,
            detail={"status": "blocked", "message": str(result.get("error") or "Approved-delivery receipt action was blocked.")},
        )
    return result


def full_assessment_response(req: FullAssessmentRequest) -> dict[str, Any]:
    payload = _model_payload(req)
    handlers = idempotent_full_assessment_handlers(timeframe_days=int(payload.get("timeframe_days") or 180))
    result = run_full_assessment_orchestration(payload, handlers=handlers)
    result = _attach_repository_evidence(result)
    result = _attach_assessment_truth_summary(result)
    result = _with_report_path(result)
    result = _attach_persisted_delivery(result)
    result = _record_result(result, payload, restored=False)
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=400,
            detail=_blocked_detail(result, "Request blocked by NICO safety, authorization, or review policy."),
        )
    return result


def full_assessment_status_response(run_id: str, req: FullAssessmentStatusRequest) -> dict[str, Any]:
    request_payload = _model_payload(req)
    explicit_fields = explicit_model_fields(req)
    payload, record = build_status_payload(run_id, request_payload, explicit_fields)
    saved_request = dict((record or {}).get("request") or {})
    auto_continue = (
        bool(request_payload.get("auto_continue"))
        if "auto_continue" in explicit_fields
        else bool(saved_request.get("auto_continue", True))
    )
    plan = plan_full_assessment_continuation(
        payload,
        record,
        auto_continue=auto_continue,
    )
    continuation_payload = plan["payload"]
    handlers = idempotent_full_assessment_handlers(timeframe_days=int(continuation_payload.get("timeframe_days") or 180))
    result = run_full_assessment_orchestration(continuation_payload, handlers=handlers)
    result = apply_full_assessment_continuation(result, plan)
    result["status_refresh"] = True
    result = _attach_repository_evidence(result)
    result = _attach_assessment_truth_summary(result)
    result = _with_report_path(result)
    result = _attach_persisted_delivery(result)
    result = _record_result(result, continuation_payload, restored=bool(record))
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=400,
            detail=_blocked_detail(result, "Status refresh blocked by NICO safety, authorization, or review policy."),
        )
    return result


def approved_delivery_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    include_pdf: bool = False,
) -> dict[str, Any]:
    result = approved_delivery_status(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        include_pdf=include_pdf,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Full Assessment report not found."})
    if result.get("status") == "blocked" and result.get("error"):
        raise HTTPException(
            status_code=400,
            detail={"status": "blocked", "message": str(result.get("error") or "Approved delivery verification failed.")},
        )
    return result


def approved_delivery_verify_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
) -> dict[str, Any]:
    return approved_delivery_response(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        include_pdf=False,
    )


def approved_delivery_access_create_response(
    run_id: str,
    req: ApprovedDeliveryAccessRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    payload = _model_payload(req)
    payload["run_id"] = run_id
    return _admin_access_result(create_approved_delivery_access(payload, admin_token=x_nico_admin_token))


def approved_delivery_access_list_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    return _admin_access_result(
        list_approved_delivery_access(
            run_id,
            customer_id=customer_id,
            project_id=project_id,
            admin_token=x_nico_admin_token,
        )
    )


def approved_delivery_receipts_list_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    return _admin_receipt_result(
        list_delivery_receipts(
            run_id,
            customer_id=customer_id,
            project_id=project_id,
            admin_token=x_nico_admin_token,
        )
    )


def approved_delivery_access_revoke_response(
    access_id: str,
    req: ApprovedDeliveryAccessRevokeRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    return _admin_access_result(
        revoke_approved_delivery_access(
            access_id,
            admin_token=x_nico_admin_token,
            actor=req.actor,
        )
    )


def approved_delivery_access_inspect_response(req: ApprovedDeliveryTokenRequest) -> dict[str, Any]:
    result = inspect_approved_delivery_access(req.token)
    if not result.get("available"):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "This approved-delivery link is unavailable."})
    return result


def approved_delivery_access_redeem_response(req: ApprovedDeliveryTokenRequest) -> Response:
    result = redeem_approved_delivery_access(req.token)
    if not result.get("available"):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "This approved-delivery link is unavailable."})

    access = result.get("access") if isinstance(result.get("access"), dict) else {}
    report = get_report(str(access.get("run_id") or access.get("report_id") or ""))
    if isinstance(report, dict) and report.get("status") != "not_found":
        result["customer_id"] = report.get("customer_id") or "default_customer"
        result["project_id"] = report.get("project_id") or "default_project"

    receipt_result = create_delivery_receipt(result)
    receipt = receipt_result.get("receipt") if isinstance(receipt_result.get("receipt"), dict) else {}
    if receipt_result.get("status") != "recorded" or not receipt.get("verified"):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "blocked",
                "message": "The approved PDF was not returned because its delivery receipt could not be persisted and verified.",
            },
        )

    filename = str(result.get("pdf_filename") or "nico-full-assessment-approved.pdf").replace('"', "")
    exposed_headers = ", ".join(
        [
            "Content-Disposition",
            "X-NICO-PDF-SHA256",
            "X-NICO-Receipt-ID",
            "X-NICO-Receipt-SHA256",
            "X-NICO-Receipt-Version",
            "X-NICO-Delivered-At",
            "X-NICO-Download-Number",
            "X-NICO-Receipt-Persistence",
        ]
    )
    return Response(
        content=result.get("pdf_bytes") or b"",
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-NICO-PDF-SHA256": str(result.get("pdf_sha256") or ""),
            "X-NICO-Receipt-ID": str(receipt.get("receipt_id") or ""),
            "X-NICO-Receipt-SHA256": str(receipt.get("receipt_sha256") or ""),
            "X-NICO-Receipt-Version": str(receipt.get("receipt_version") or ""),
            "X-NICO-Delivered-At": str(receipt.get("delivered_at") or ""),
            "X-NICO-Download-Number": str(receipt.get("download_number") or ""),
            "X-NICO-Receipt-Persistence": str((receipt.get("persistence") or {}).get("adapter") or "unknown"),
            "Access-Control-Expose-Headers": exposed_headers,
        },
    )


def register_full_assessment_routes(app: FastAPI) -> None:
    app.post("/assessment/full-run")(full_assessment_response)
    app.post("/assessment/full-run/{run_id}/status")(full_assessment_status_response)
    app.get("/assessment/full-run/{run_id}/approved-delivery")(approved_delivery_response)
    app.get("/assessment/full-run/{run_id}/approved-delivery/verify")(approved_delivery_verify_response)
    app.post("/assessment/full-run/{run_id}/approved-delivery/access")(approved_delivery_access_create_response)
    app.get("/assessment/full-run/{run_id}/approved-delivery/access")(approved_delivery_access_list_response)
    app.get("/assessment/full-run/{run_id}/approved-delivery/receipts")(approved_delivery_receipts_list_response)
    app.post("/assessment/full-run/approved-delivery/access/{access_id}/revoke")(approved_delivery_access_revoke_response)
    app.post("/delivery/approved/inspect")(approved_delivery_access_inspect_response)
    app.post("/delivery/approved/redeem")(approved_delivery_access_redeem_response)
    app.get("/reports/{run_id}/approved-delivery")(approved_delivery_response)
    app.get("/reports/{run_id}/approved-delivery/verify")(approved_delivery_verify_response)
    app.get("/reports/{run_id}/approved-delivery/receipts")(approved_delivery_receipts_list_response)
