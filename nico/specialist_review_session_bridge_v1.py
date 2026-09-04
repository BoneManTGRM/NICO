from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from nico.specialist_access_v1 import validate_specialist_session

VERSION = "nico.specialist_review_session_bridge.v1"
_SESSION_HEADER = "x-nico-operator-session"
_CURRENT_AUTHORITY: ContextVar[dict[str, Any] | None] = ContextVar(
    "nico_specialist_review_authority",
    default=None,
)


async def _bind_session_context(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    authority = validate_specialist_session(request.headers.get(_SESSION_HEADER))
    reset: Token[dict[str, Any] | None] | None = None
    if authority is not None:
        reset = _CURRENT_AUTHORITY.set(dict(authority))
    try:
        return await call_next(request)
    finally:
        if reset is not None:
            _CURRENT_AUTHORITY.reset(reset)


def install_specialist_review_session_bridge(app: FastAPI) -> dict[str, Any]:
    from nico import comprehensive_api_routes as routes

    if getattr(routes, "_nico_specialist_review_session_bridge_v1", False):
        return {
            "artifact_schema": VERSION,
            "installed": True,
            "request_context_isolated": True,
        }

    original = routes.require_comprehensive_operator

    def require_comprehensive_operator_with_session(provided_token: str | None = None):
        allowed, status = original(provided_token)
        if allowed:
            return allowed, status
        authority = _CURRENT_AUTHORITY.get()
        if authority is None:
            return allowed, status
        return True, {
            "enabled": True,
            "status": "session",
            "authority": str(
                authority.get("authority") or "nico_comprehensive_operator"
            ),
            "scope": "comprehensive_review_and_delivery",
            "reason": "Signed scoped Comprehensive specialist session accepted.",
            "publicly_usable": False,
        }

    routes.require_comprehensive_operator = require_comprehensive_operator_with_session
    routes._nico_specialist_review_session_bridge_v1 = True
    app.add_middleware(BaseHTTPMiddleware, dispatch=_bind_session_context)
    app.openapi_schema = None
    return {
        "artifact_schema": VERSION,
        "installed": True,
        "request_context_isolated": True,
        "raw_admin_authority_unchanged": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_specialist_review_session_bridge"]
