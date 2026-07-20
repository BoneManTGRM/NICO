from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunNotFound

VERSION = "nico.comprehensive_api_routes.v1"

COMPREHENSIVE_API_ROUTES = {
    ("POST", "/assessment/comprehensive-run"),
    ("GET", "/assessment/comprehensive-run/{run_id}"),
    ("POST", "/assessment/comprehensive-run/{run_id}/continue"),
}


def _controller(request: Request) -> ComprehensiveApiController:
    controller = getattr(request.app.state, "comprehensive_api_controller", None)
    if not isinstance(controller, ComprehensiveApiController):
        raise HTTPException(status_code=503, detail="comprehensive_service_not_configured")
    return controller


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ComprehensiveRunNotFound):
        return HTTPException(status_code=404, detail="comprehensive_run_not_found")
    if isinstance(exc, ComprehensiveRunConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="comprehensive_service_error")


def register_comprehensive_api_routes(
    app: FastAPI,
    *,
    controller: ComprehensiveApiController | None = None,
) -> FastAPI:
    if controller is not None:
        app.state.comprehensive_api_controller = controller

    existing = {
        (method.upper(), str(getattr(route, "path", "")))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    present = existing & COMPREHENSIVE_API_ROUTES
    if present:
        if present != COMPREHENSIVE_API_ROUTES:
            raise RuntimeError(
                "Partial Comprehensive route registration detected; "
                f"missing={sorted(COMPREHENSIVE_API_ROUTES - present)}"
            )
        return app

    @app.post("/assessment/comprehensive-run")
    async def start_comprehensive(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            return _controller(request).start(payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}")
    async def get_comprehensive(run_id: str, request: Request) -> dict[str, Any]:
        try:
            return _controller(request).status(run_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/assessment/comprehensive-run/{run_id}/continue")
    async def continue_comprehensive(run_id: str, request: Request) -> dict[str, Any]:
        try:
            raw = await request.body()
            payload = await request.json() if raw else {}
            return _controller(request).continue_run(run_id, payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    app.openapi_schema = None
    return app


__all__ = ["COMPREHENSIVE_API_ROUTES", "VERSION", "register_comprehensive_api_routes"]
