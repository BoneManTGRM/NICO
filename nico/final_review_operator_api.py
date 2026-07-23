from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from nico.admin_security import require_admin_write
from nico.client_acceptance import (
    client_acceptance_status,
    request_client_acceptance,
    transition_client_acceptance,
)
from nico.final_review_workflow import (
    final_review_status,
    request_final_review,
    transition_final_review,
)

VERSION = "nico.final_review_operator_api.v1"
OPERATOR_REVIEW_ROUTES = {
    ("GET", "/operations/final-review/{service}/{run_id}"),
    ("POST", "/operations/final-review/{service}/{run_id}/request"),
    ("POST", "/operations/final-review/{service}/{approval_id}/{state}"),
}
_PROTECTED_LEGACY_PREFIXES = (
    "/reports/final-review/",
    "/client-acceptance/",
)


class OperatorReviewRequest(BaseModel):
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    report_id: str = ""
    repository: str = ""
    evidence: list[str] = Field(default_factory=list)
    requester: str = "nico_operator"
    risk_level: str = "delivery_review"
    test_plan: str = ""
    rollback_plan: str = ""


class OperatorReviewTransition(BaseModel):
    actor: str = "human_reviewer"
    note: str = ""


def _service(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"express", "comprehensive"}:
        return normalized
    raise HTTPException(
        status_code=400,
        detail={"status": "blocked", "message": "service must be express or comprehensive"},
    )


def _authorize(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "status": "blocked",
            "message": "Operator admin authentication is required for final-review access.",
            "admin_write": status,
        },
    )


def _blocked(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "blocked",
                "message": str(result.get("error") or result.get("message") or "Final-review action was blocked."),
            },
        )
    return result


def _review_status(service: str, run_id: str, customer_id: str, project_id: str) -> dict[str, Any]:
    if service == "express":
        result = client_acceptance_status(run_id, customer_id, project_id)
        result["service"] = "express"
        result["review_kind"] = "client_acceptance_signoff"
        return result
    result = final_review_status(run_id, customer_id, project_id)
    result["service"] = "comprehensive"
    result["review_kind"] = "final_report_approval"
    return result


def _request_review(service: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    request_payload = dict(payload)
    request_payload["run_id"] = run_id
    if service == "express":
        result = _blocked(request_client_acceptance(request_payload))
        result["service"] = "express"
        result["review_kind"] = "client_acceptance_signoff"
        return result
    result = _blocked(request_final_review(request_payload))
    result["service"] = "comprehensive"
    result["review_kind"] = "final_report_approval"
    return result


def _transition_review(service: str, approval_id: str, state: str, actor: str, note: str) -> dict[str, Any]:
    if state not in {"approved", "needs_more_evidence", "rejected"}:
        raise HTTPException(
            status_code=400,
            detail={"status": "blocked", "message": "state must be approved, needs_more_evidence, or rejected"},
        )
    if service == "express":
        result = _blocked(transition_client_acceptance(approval_id, state, actor=actor, note=note))
        result["service"] = "express"
        result["review_kind"] = "client_acceptance_signoff"
        return result
    result = _blocked(transition_final_review(approval_id, state, actor=actor, note=note))
    result["service"] = "comprehensive"
    result["review_kind"] = "final_report_approval"
    return result


def _legacy_final_review_path(method: str, path: str) -> bool:
    if method != "POST":
        return False
    if path.startswith("/reports/") and path.endswith("/final-review/request"):
        return True
    return path.startswith(_PROTECTED_LEGACY_PREFIXES)


class FinalReviewAdminBoundaryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method") or "GET").upper()
        path = str(scope.get("path") or "")
        protected = path.startswith("/operations/final-review/") or _legacy_final_review_path(method, path)
        if not protected:
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers") or []
        }
        allowed, status = require_admin_write(headers.get("x-nico-admin-token", ""))
        if allowed:
            await self.app(scope, receive, send)
            return
        body = (
            '{"detail":{"status":"blocked","message":"Operator admin authentication is required for final-review access."}}'
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store, private, max-age=0"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def register_final_review_operator_routes(target: FastAPI) -> dict[str, Any]:
    if not bool(getattr(target.state, "nico_final_review_admin_boundary", False)):
        target.user_middleware.append(Middleware(FinalReviewAdminBoundaryMiddleware))
        target.middleware_stack = None
        target.state.nico_final_review_admin_boundary = True

    existing = _route_pairs(target)
    if existing & OPERATOR_REVIEW_ROUTES and (existing & OPERATOR_REVIEW_ROUTES) != OPERATOR_REVIEW_ROUTES:
        raise RuntimeError("Partial operator final-review route registration detected")

    if OPERATOR_REVIEW_ROUTES <= existing:
        return {"status": "already_installed", "version": VERSION, "routes": sorted(OPERATOR_REVIEW_ROUTES)}

    def review_status(
        service: str,
        run_id: str,
        customer_id: str = "default_customer",
        project_id: str = "default_project",
        x_nico_admin_token: str = Header(default=""),
    ) -> dict[str, Any]:
        _authorize(x_nico_admin_token)
        return _review_status(_service(service), run_id, customer_id, project_id)

    def request_review(
        service: str,
        run_id: str,
        req: OperatorReviewRequest,
        x_nico_admin_token: str = Header(default=""),
    ) -> dict[str, Any]:
        _authorize(x_nico_admin_token)
        return _request_review(_service(service), run_id, req.model_dump())

    def transition_review(
        service: str,
        approval_id: str,
        state: str,
        req: OperatorReviewTransition,
        x_nico_admin_token: str = Header(default=""),
    ) -> dict[str, Any]:
        _authorize(x_nico_admin_token)
        return _transition_review(_service(service), approval_id, state, req.actor, req.note)

    target.add_api_route(
        "/operations/final-review/{service}/{run_id}",
        review_status,
        methods=["GET"],
        tags=["operations", "final-review"],
    )
    target.add_api_route(
        "/operations/final-review/{service}/{run_id}/request",
        request_review,
        methods=["POST"],
        tags=["operations", "final-review"],
    )
    target.add_api_route(
        "/operations/final-review/{service}/{approval_id}/{state}",
        transition_review,
        methods=["POST"],
        tags=["operations", "final-review"],
    )
    target.openapi_schema = None
    missing = OPERATOR_REVIEW_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(f"Operator final-review routes missing after registration: {sorted(missing)}")
    return {
        "status": "installed",
        "version": VERSION,
        "routes": sorted(OPERATOR_REVIEW_ROUTES),
        "legacy_write_routes_require_admin": True,
        "operator_routes_require_admin": True,
        "express_and_comprehensive_supported": True,
        "human_review_required": True,
    }


__all__ = [
    "FinalReviewAdminBoundaryMiddleware",
    "OPERATOR_REVIEW_ROUTES",
    "VERSION",
    "register_final_review_operator_routes",
]
