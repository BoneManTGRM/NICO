from __future__ import annotations

from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Request

from nico.monitor_approval_governance import ApprovalGovernanceError, GovernedMonitorExecuteService
from nico.monitor_execute_api import register_monitor_execute_routes


GOVERNANCE_ROUTES = {
    ("GET", "/monitor/work-items/{work_item_id}/approval"),
    ("POST", "/monitor/work-items/{work_item_id}/approval/revoke"),
}


def _service(request: Request) -> GovernedMonitorExecuteService:
    service = getattr(request.app.state, "monitor_execute_service", None)
    if not isinstance(service, GovernedMonitorExecuteService):
        raise HTTPException(status_code=503, detail="governed_monitor_execute_service_not_configured")
    return service


async def _payload(request: Request) -> Mapping[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="request_body_must_be_object") from exc
    if not isinstance(payload, Mapping):
        raise HTTPException(status_code=422, detail="request_body_must_be_object")
    return payload


def register_governed_monitor_routes(app: FastAPI, *, service: GovernedMonitorExecuteService) -> None:
    register_monitor_execute_routes(app, service=service)
    existing = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    overlap = GOVERNANCE_ROUTES.intersection(existing)
    if overlap:
        if overlap == GOVERNANCE_ROUTES:
            app.state.monitor_execute_service = service
            return
        raise RuntimeError("monitor_governance_partial_route_group_detected")
    app.state.monitor_execute_service = service

    @app.get("/monitor/work-items/{work_item_id}/approval")
    async def get_approval_status(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return {
                "artifact_schema": "nico.monitor_approval_governance.v1",
                **_service(request).approval_status(work_item_id),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        except HTTPException:
            raise
        except ApprovalGovernanceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/monitor/work-items/{work_item_id}/approval/revoke")
    async def revoke_approval(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return {
                "artifact_schema": "nico.monitor_approval_governance.v1",
                **_service(request).revoke(work_item_id, await _payload(request)),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        except HTTPException:
            raise
        except ApprovalGovernanceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["GOVERNANCE_ROUTES", "register_governed_monitor_routes"]
