from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from nico.api.main import app
from nico.approved_delivery_storage_policy import delivery_storage_readiness
from nico.full_assessment_api import register_full_assessment_routes

REQUIRED_FULL_ASSESSMENT_ROUTES = {
    ("POST", "/assessment/full-run"),
    ("POST", "/assessment/full-run/{run_id}/status"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/verify"),
    ("POST", "/assessment/full-run/{run_id}/approved-delivery/access"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/access"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/receipts"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/acknowledgments"),
    ("POST", "/assessment/full-run/approved-delivery/access/{access_id}/revoke"),
    ("POST", "/delivery/approved/inspect"),
    ("POST", "/delivery/approved/redeem"),
    ("POST", "/delivery/approved/acknowledge"),
    ("GET", "/reports/{run_id}/approved-delivery"),
    ("GET", "/reports/{run_id}/approved-delivery/verify"),
    ("GET", "/reports/{run_id}/approved-delivery/receipts"),
    ("GET", "/reports/{run_id}/approved-delivery/acknowledgments"),
}
HOSTED_POLICY_ROUTES = {("GET", "/delivery/storage-readiness")}


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def _protected_delivery_write(request: Request) -> bool:
    if request.method.upper() != "POST":
        return False
    path = request.url.path.rstrip("/") or "/"
    if path in {"/delivery/approved/redeem", "/delivery/approved/acknowledge"}:
        return True
    return path.startswith("/assessment/full-run/") and path.endswith("/approved-delivery/access")


async def _enforce_durable_delivery_storage(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if _protected_delivery_write(request):
        readiness = delivery_storage_readiness()
        if not readiness.get("ready"):
            return JSONResponse(
                status_code=503,
                content={
                    "status": "blocked",
                    "code": "durable_delivery_storage_unavailable",
                    "message": "Hosted client delivery is temporarily unavailable because durable delivery storage is required but not ready.",
                    "storage_readiness": readiness,
                },
                headers={"Cache-Control": "no-store, private, max-age=0"},
            )
    return await call_next(request)


def _delivery_storage_readiness_response() -> dict[str, object]:
    return delivery_storage_readiness()


def register_hosted_extension_routes(target: FastAPI) -> FastAPI:
    """Register the complete hosted Full Assessment surface and delivery policy once."""

    existing = _route_pairs(target)
    present = existing & REQUIRED_FULL_ASSESSMENT_ROUTES
    changed = False
    if present != REQUIRED_FULL_ASSESSMENT_ROUTES:
        if present:
            missing = sorted(REQUIRED_FULL_ASSESSMENT_ROUTES - present)
            raise RuntimeError(f"Partial Full Assessment route registration detected; missing={missing}")
        register_full_assessment_routes(target)
        changed = True

    registered = _route_pairs(target)
    missing = REQUIRED_FULL_ASSESSMENT_ROUTES - registered
    if missing:
        raise RuntimeError(f"Full Assessment route registration incomplete; missing={sorted(missing)}")

    if ("GET", "/delivery/storage-readiness") not in registered:
        target.add_api_route(
            "/delivery/storage-readiness",
            _delivery_storage_readiness_response,
            methods=["GET"],
            tags=["approved-delivery"],
        )
        changed = True

    if not bool(getattr(target.state, "nico_durable_delivery_middleware", False)):
        target.middleware("http")(_enforce_durable_delivery_storage)
        target.state.nico_durable_delivery_middleware = True

    if changed:
        target.openapi_schema = None
    return target


register_hosted_extension_routes(app)

__all__ = [
    "app",
    "register_hosted_extension_routes",
    "REQUIRED_FULL_ASSESSMENT_ROUTES",
    "HOSTED_POLICY_ROUTES",
]
