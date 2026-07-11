from __future__ import annotations

from fastapi import FastAPI

from nico.api.hosted import app
from nico.mid_assessment_api import register_mid_assessment_routes
from nico.mid_optional_evidence_api import register_mid_optional_evidence_routes
from nico.mid_report_api import register_mid_report_routes
from nico.mid_review_api import register_mid_review_routes

REQUIRED_MID_ASSESSMENT_ROUTES = {
    ("POST", "/assessment/mid-run"),
    ("POST", "/assessment/mid-run/{run_id}/status"),
    ("POST", "/assessment/mid-run/{run_id}/evidence"),
    ("GET", "/assessment/mid-run/{run_id}/review-exceptions"),
    ("POST", "/assessment/mid-run/{run_id}/report/draft"),
    ("GET", "/assessment/mid-run/{run_id}/report/draft/pdf"),
}
MID_CORE_ROUTES = {
    ("POST", "/assessment/mid-run"),
    ("POST", "/assessment/mid-run/{run_id}/status"),
}
MID_OPTIONAL_EVIDENCE_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/evidence"),
}
MID_REVIEW_ROUTES = {
    ("GET", "/assessment/mid-run/{run_id}/review-exceptions"),
}
MID_REPORT_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/report/draft"),
    ("GET", "/assessment/mid-run/{run_id}/report/draft/pdf"),
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
    core_present = existing & MID_CORE_ROUTES
    optional_present = existing & MID_OPTIONAL_EVIDENCE_ROUTES
    review_present = existing & MID_REVIEW_ROUTES
    report_present = existing & MID_REPORT_ROUTES
    if core_present and core_present != MID_CORE_ROUTES:
        raise RuntimeError(f"Partial unified Mid route registration detected; missing={sorted(MID_CORE_ROUTES - core_present)}")
    if optional_present and optional_present != MID_OPTIONAL_EVIDENCE_ROUTES:
        raise RuntimeError(f"Partial Mid optional-evidence route registration detected; missing={sorted(MID_OPTIONAL_EVIDENCE_ROUTES - optional_present)}")
    if review_present and review_present != MID_REVIEW_ROUTES:
        raise RuntimeError(f"Partial Mid review route registration detected; missing={sorted(MID_REVIEW_ROUTES - review_present)}")
    if report_present and report_present != MID_REPORT_ROUTES:
        raise RuntimeError(f"Partial Mid report route registration detected; missing={sorted(MID_REPORT_ROUTES - report_present)}")
    if not core_present:
        register_mid_assessment_routes(target)
        target.openapi_schema = None
    if not optional_present:
        register_mid_optional_evidence_routes(target)
        target.openapi_schema = None
    if not review_present:
        register_mid_review_routes(target)
        target.openapi_schema = None
    if not report_present:
        register_mid_report_routes(target)
        target.openapi_schema = None
    missing = REQUIRED_MID_ASSESSMENT_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(f"Unified Mid route registration incomplete; missing={sorted(missing)}")
    return target


register_production_routes(app)

__all__ = [
    "app",
    "register_production_routes",
    "REQUIRED_MID_ASSESSMENT_ROUTES",
    "MID_CORE_ROUTES",
    "MID_OPTIONAL_EVIDENCE_ROUTES",
    "MID_REVIEW_ROUTES",
    "MID_REPORT_ROUTES",
]
