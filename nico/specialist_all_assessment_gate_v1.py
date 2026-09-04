from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from nico.admin_security import require_comprehensive_operator
from nico.specialist_access_v1 import (
    ADMIN_HEADER,
    SESSION_HEADER,
    SESSION_ROUTE,
    validate_specialist_session,
)

VERSION = "nico.specialist_all_assessment_gate.v1"
_PROTECTED_ROOTS = ("/assessment", "/reports")


def _protected(path: str) -> bool:
    normalized = str(path or "").rstrip("/") or "/"
    if normalized == SESSION_ROUTE:
        return False
    return any(
        normalized == root or normalized.startswith(f"{root}/")
        for root in _PROTECTED_ROOTS
    )


def _blocked(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "blocked",
            "detail": {
                "code": code,
                "message": "Authenticated NICO specialist access is required.",
                "retryable": False,
            },
        },
        headers={"Cache-Control": "no-store, private, max-age=0"},
    )


async def _enforce_all_assessment_access(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.method == "OPTIONS" or not _protected(request.url.path):
        return await call_next(request)

    raw_token = request.headers.get(ADMIN_HEADER, "").strip()
    session_token = request.headers.get(SESSION_HEADER, "").strip()
    authority: dict[str, Any] | None = None

    if raw_token:
        allowed, status = require_comprehensive_operator(raw_token)
        if not allowed:
            return _blocked(403, "specialist_operator_authentication_invalid")
        authority = dict(status)
    elif session_token:
        authority = validate_specialist_session(session_token)
        if authority is None:
            return _blocked(401, "specialist_session_invalid_or_expired")
    else:
        return _blocked(401, "specialist_authentication_required")

    request.state.nico_specialist_authority = authority
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, private, max-age=0"
    return response


def install_all_assessment_access_gate(app: FastAPI) -> dict[str, Any]:
    existing = getattr(app.state, "nico_specialist_all_assessment_gate_v1", None)
    if isinstance(existing, dict):
        return dict(existing)

    app.add_middleware(BaseHTTPMiddleware, dispatch=_enforce_all_assessment_access)
    status = {
        "artifact_schema": VERSION,
        "installed": True,
        "protected_roots": list(_PROTECTED_ROOTS),
        "session_route_exempt": True,
        "run_ids_are_credentials": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_specialist_all_assessment_gate_v1 = status
    app.openapi_schema = None
    return dict(status)


__all__ = [
    "VERSION",
    "install_all_assessment_access_gate",
]
