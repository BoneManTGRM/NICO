from __future__ import annotations

from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Request

from nico.monitor_execute_contract import MonitorExecuteError
from nico.monitor_execute_service import (
    MonitorExecuteService,
    MonitorIntegrityError,
    MonitorItemDuplicate,
    MonitorItemMissing,
    MonitorRevisionConflict,
)


VERSION = "nico.monitor_execute_api.v1"
MONITOR_EXECUTE_ROUTES = {
    ("POST", "/monitor/work-items"),
    ("GET", "/monitor/work-items/{work_item_id}"),
    ("POST", "/monitor/work-items/{work_item_id}/proposal"),
    ("POST", "/monitor/work-items/{work_item_id}/approval"),
    ("POST", "/monitor/work-items/{work_item_id}/execution/begin"),
    ("POST", "/monitor/work-items/{work_item_id}/execution/complete"),
    ("POST", "/monitor/work-items/{work_item_id}/verification"),
}


def _safe_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MonitorItemMissing):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (MonitorItemDuplicate, MonitorRevisionConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, MonitorIntegrityError):
        return HTTPException(status_code=500, detail="monitor_integrity_verification_failed")
    if isinstance(exc, MonitorExecuteError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="monitor_execute_operation_failed")


def _service(request: Request) -> MonitorExecuteService:
    service = getattr(request.app.state, "monitor_execute_service", None)
    if not isinstance(service, MonitorExecuteService):
        raise HTTPException(status_code=503, detail="monitor_execute_service_not_configured")
    return service


async def _payload(request: Request) -> Mapping[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="request_body_must_be_object") from exc
    if not isinstance(payload, Mapping):
        raise HTTPException(status_code=422, detail="request_body_must_be_object")
    return payload


def _response(payload: Mapping[str, Any], *, operation: str) -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "service_id": "monitor_execute",
        "operation": operation,
        **dict(payload),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "production_execution_requires_explicit_approval": True,
    }


def register_monitor_execute_routes(app: FastAPI, *, service: MonitorExecuteService | None = None) -> None:
    existing = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    overlap = MONITOR_EXECUTE_ROUTES.intersection(existing)
    if overlap:
        if overlap == MONITOR_EXECUTE_ROUTES:
            if service is not None:
                app.state.monitor_execute_service = service
            return
        raise RuntimeError("monitor_execute_partial_route_group_detected")
    if service is not None:
        app.state.monitor_execute_service = service

    @app.post("/monitor/work-items")
    async def create_monitor_work_item(request: Request) -> dict[str, Any]:
        try:
            return _response(_service(request).create(await _payload(request)), operation="created")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.get("/monitor/work-items/{work_item_id}")
    async def get_monitor_work_item(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return _response(_service(request).status(work_item_id), operation="status")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.post("/monitor/work-items/{work_item_id}/proposal")
    async def propose_monitor_remediation(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return _response(_service(request).propose(work_item_id, await _payload(request)), operation="proposed")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.post("/monitor/work-items/{work_item_id}/approval")
    async def approve_monitor_remediation(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return _response(_service(request).approve(work_item_id, await _payload(request)), operation="approval_recorded")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.post("/monitor/work-items/{work_item_id}/execution/begin")
    async def begin_monitor_execution(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return _response(_service(request).begin(work_item_id, await _payload(request)), operation="execution_authorized")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.post("/monitor/work-items/{work_item_id}/execution/complete")
    async def complete_monitor_execution(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return _response(_service(request).complete_execution(work_item_id, await _payload(request)), operation="execution_recorded")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.post("/monitor/work-items/{work_item_id}/verification")
    async def verify_monitor_execution(work_item_id: str, request: Request) -> dict[str, Any]:
        try:
            return _response(_service(request).verify(work_item_id, await _payload(request)), operation="verification_recorded")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc


__all__ = ["MONITOR_EXECUTE_ROUTES", "VERSION", "register_monitor_execute_routes"]
