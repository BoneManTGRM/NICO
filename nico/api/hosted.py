from __future__ import annotations

from fastapi import FastAPI

from nico.api.main import app
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


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def register_hosted_extension_routes(target: FastAPI) -> FastAPI:
    """Register the complete hosted Full Assessment surface exactly once."""

    existing = _route_pairs(target)
    present = existing & REQUIRED_FULL_ASSESSMENT_ROUTES
    if present == REQUIRED_FULL_ASSESSMENT_ROUTES:
        return target
    if present:
        missing = sorted(REQUIRED_FULL_ASSESSMENT_ROUTES - present)
        raise RuntimeError(f"Partial Full Assessment route registration detected; missing={missing}")

    register_full_assessment_routes(target)
    registered = _route_pairs(target)
    missing = REQUIRED_FULL_ASSESSMENT_ROUTES - registered
    if missing:
        raise RuntimeError(f"Full Assessment route registration incomplete; missing={sorted(missing)}")
    target.openapi_schema = None
    return target


register_hosted_extension_routes(app)

__all__ = ["app", "register_hosted_extension_routes", "REQUIRED_FULL_ASSESSMENT_ROUTES"]
