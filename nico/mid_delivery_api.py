from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from nico.mid_delivery_access import (
    create_mid_delivery_access,
    inspect_mid_delivery_access,
    list_mid_delivery_access,
    list_mid_delivery_receipts,
    redeem_mid_delivery_access,
    revoke_mid_delivery_access,
)


class MidDeliveryCreateRequest(BaseModel):
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    recipient_label: str = Field(default="", max_length=160)
    created_by: str = Field(default="", max_length=160)
    expires_in_hours: int = 24
    max_downloads: int = 1


class MidDeliveryInspectRequest(BaseModel):
    token: str = Field(default="", max_length=240)


class MidDeliveryRedeemRequest(BaseModel):
    token: str = Field(default="", max_length=240)
    recipient_name: str = Field(default="", max_length=160)
    acknowledged: bool = False
    acknowledgement_text: str = Field(default="", max_length=2000)


class MidDeliveryRevokeRequest(BaseModel):
    actor: str = Field(default="", max_length=160)
    reason: str = Field(default="", max_length=1000)


def _raise(result: dict[str, Any], default_message: str) -> None:
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": default_message})
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=403 if result.get("admin_write") else 409,
            detail={"status": "blocked", "message": str(result.get("error") or default_message)},
        )


def mid_delivery_create_response(
    run_id: str,
    req: MidDeliveryCreateRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    payload = req.model_dump()
    payload["run_id"] = run_id
    result = create_mid_delivery_access(payload, admin_token=x_nico_admin_token)
    _raise(result, "Mid delivery access could not be created.")
    return result


def mid_delivery_list_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = list_mid_delivery_access(run_id, customer_id, project_id, admin_token=x_nico_admin_token)
    _raise(result, "Mid Assessment run not found.")
    return result


def mid_delivery_receipts_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = list_mid_delivery_receipts(run_id, customer_id, project_id, admin_token=x_nico_admin_token)
    _raise(result, "Mid Assessment run not found.")
    return result


def mid_delivery_revoke_response(
    access_id: str,
    req: MidDeliveryRevokeRequest,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = revoke_mid_delivery_access(access_id, req.actor, req.reason, admin_token=x_nico_admin_token)
    _raise(result, "Mid delivery link not found.")
    return result


def mid_delivery_inspect_response(req: MidDeliveryInspectRequest) -> dict[str, Any]:
    result = inspect_mid_delivery_access(req.token)
    _raise(result, "This Mid delivery link is unavailable.")
    return result


def mid_delivery_redeem_response(req: MidDeliveryRedeemRequest) -> Response:
    result = redeem_mid_delivery_access(
        req.token,
        recipient_name=req.recipient_name,
        acknowledged=req.acknowledged,
        acknowledgement_text=req.acknowledgement_text,
    )
    _raise(result, "This Mid delivery link is unavailable.")
    pdf = bytes(result.get("pdf") or b"")
    if not pdf.startswith(b"%PDF"):
        raise HTTPException(status_code=409, detail={"status": "blocked", "message": "The approved Mid PDF failed response validation."})
    receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
    access = result.get("access") if isinstance(result.get("access"), dict) else {}
    filename = str(result.get("pdf_filename") or "nico-mid-assessment-APPROVED.pdf").replace('"', "")
    exposed = ", ".join(
        [
            "Content-Disposition",
            "X-NICO-Report-ID",
            "X-NICO-PDF-SHA256",
            "X-NICO-Approval-ID",
            "X-NICO-Approval-Identity-SHA256",
            "X-NICO-Review-Packet-SHA256",
            "X-NICO-Delivery-Access-ID",
            "X-NICO-Delivery-Receipt-ID",
            "X-NICO-Delivery-Receipt-SHA256",
            "X-NICO-Downloads-Remaining",
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
            "X-NICO-Approval-ID": str(result.get("approval_id") or ""),
            "X-NICO-Approval-Identity-SHA256": str(result.get("approval_identity_sha256") or ""),
            "X-NICO-Review-Packet-SHA256": str(result.get("review_packet_sha256") or ""),
            "X-NICO-Delivery-Access-ID": str(access.get("access_id") or ""),
            "X-NICO-Delivery-Receipt-ID": str(receipt.get("receipt_id") or ""),
            "X-NICO-Delivery-Receipt-SHA256": str(receipt.get("receipt_sha256") or ""),
            "X-NICO-Downloads-Remaining": str(access.get("downloads_remaining") or 0),
            "Access-Control-Expose-Headers": exposed,
        },
    )


def register_mid_delivery_routes(app: FastAPI) -> None:
    app.post("/assessment/mid-run/{run_id}/delivery/access")(mid_delivery_create_response)
    app.get("/assessment/mid-run/{run_id}/delivery/access")(mid_delivery_list_response)
    app.get("/assessment/mid-run/{run_id}/delivery/receipts")(mid_delivery_receipts_response)
    app.post("/assessment/mid-run/delivery/access/{access_id}/revoke")(mid_delivery_revoke_response)
    app.post("/assessment/mid-run/delivery/inspect")(mid_delivery_inspect_response)
    app.post("/assessment/mid-run/delivery/redeem")(mid_delivery_redeem_response)


__all__ = [
    "MidDeliveryCreateRequest",
    "MidDeliveryInspectRequest",
    "MidDeliveryRedeemRequest",
    "MidDeliveryRevokeRequest",
    "mid_delivery_create_response",
    "mid_delivery_list_response",
    "mid_delivery_receipts_response",
    "mid_delivery_revoke_response",
    "mid_delivery_inspect_response",
    "mid_delivery_redeem_response",
    "register_mid_delivery_routes",
]
