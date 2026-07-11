from __future__ import annotations

from fastapi import FastAPI

from nico.api.hosted import app
from nico.mid_assessment_api import register_mid_assessment_routes

REQUIRED_MID_ASSESSMENT_ROUTES = {
    ("POST", "/assessment/mid-run"),
    ("POST", "/assessment/mid-run/{run_id}/status"),
}


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def register_production_routes(target: FastAPI) -> FastAPI:
    existing = _route_pairs(target)
    present = existing & REQUIRED_MID_ASSESSMENT_ROUTES
    if present and present != REQUIRED_MID_ASSESSMENT_ROUTES:
        raise RuntimeError(f"Partial unified Mid route registration detected; missing={sorted(REQUIRED_MID_ASSESSMENT_ROUTES - present)}")
    if not present:
        register_mid_assessment_routes(target)
        target.openapi_schema = None
    missing = REQUIRED_MID_ASSESSMENT_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(f"Unified Mid route registration incomplete; missing={sorted(missing)}")
    return target


register_production_routes(app)

__all__ = ["app", "register_production_routes", "REQUIRED_MID_ASSESSMENT_ROUTES"]
