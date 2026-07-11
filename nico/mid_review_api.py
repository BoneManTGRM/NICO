from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException

from nico.mid_review_by_exception import build_mid_review_packet


def mid_review_packet_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    result = build_mid_review_packet(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=x_nico_admin_token,
    )
    if result.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail={"status": "not_found", "message": "Mid Assessment run not found."},
        )
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=403 if result.get("admin_write") else 400,
            detail={"status": "blocked", "message": str(result.get("error") or "Mid review packet was blocked.")},
        )
    return result


def register_mid_review_routes(app: FastAPI) -> None:
    app.get("/assessment/mid-run/{run_id}/review-exceptions")(mid_review_packet_response)


__all__ = ["mid_review_packet_response", "register_mid_review_routes"]
