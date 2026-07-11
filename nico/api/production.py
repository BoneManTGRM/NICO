from __future__ import annotations

from fastapi import FastAPI

from nico.api.hosted import app
from nico.mid_approval_api import register_mid_approval_routes
from nico.mid_assessment_api import register_mid_assessment_routes
from nico.mid_delivery_api import register_mid_delivery_routes
from nico.mid_legacy_migration import LEGACY_MID_PATH, register_legacy_mid_migration
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
    ("POST", "/assessment/mid-run/{run_id}/approval/request"),
    ("GET", "/assessment/mid-run/{run_id}/approval"),
    ("POST", "/assessment/mid-run/approval/{approval_id}/{state}"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved/pdf"),
    ("POST", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/receipts"),
    ("POST", "/assessment/mid-run/delivery/access/{access_id}/revoke"),
    ("POST", "/assessment/mid-run/delivery/inspect"),
    ("POST", "/assessment/mid-run/delivery/redeem"),
    ("POST", LEGACY_MID_PATH),
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
MID_APPROVAL_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/approval/request"),
    ("GET", "/assessment/mid-run/{run_id}/approval"),
    ("POST", "/assessment/mid-run/approval/{approval_id}/{state}"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved/pdf"),
}
MID_DELIVERY_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/receipts"),
    ("POST", "/assessment/mid-run/delivery/access/{access_id}/revoke"),
    ("POST", "/assessment/mid-run/delivery/inspect"),
    ("POST", "/assessment/mid-run/delivery/redeem"),
}


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected_method = method.upper()
    count = 0
    for route in target.routes:
        methods = {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
        if str(getattr(route, "path", "")) == path and expected_method in methods:
            count += 1
    return count


def _validate_group(existing: set[tuple[str, str]], required: set[tuple[str, str]], label: str) -> bool:
    present = existing & required
    if present and present != required:
        raise RuntimeError(f"Partial {label} route registration detected; missing={sorted(required - present)}")
    return bool(present)


def register_production_routes(target: FastAPI) -> FastAPI:
    existing = _route_pairs(target)
    core_present = _validate_group(existing, MID_CORE_ROUTES, "unified Mid")
    optional_present = _validate_group(existing, MID_OPTIONAL_EVIDENCE_ROUTES, "Mid optional-evidence")
    review_present = _validate_group(existing, MID_REVIEW_ROUTES, "Mid review")
    report_present = _validate_group(existing, MID_REPORT_ROUTES, "Mid report")
    approval_present = _validate_group(existing, MID_APPROVAL_ROUTES, "Mid approval")
    delivery_present = _validate_group(existing, MID_DELIVERY_ROUTES, "Mid delivery")
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
    if not approval_present:
        register_mid_approval_routes(target)
        target.openapi_schema = None
    if not delivery_present:
        register_mid_delivery_routes(target)
        target.openapi_schema = None

    # The application imported above still contains the former manual-notes
    # POST /assessment/mid handler. Replace it after all route groups are loaded
    # so production exposes exactly one guarded migration boundary.
    register_legacy_mid_migration(target)
    if _route_count(target, "POST", LEGACY_MID_PATH) != 1:
        raise RuntimeError("Legacy Mid migration route registration must produce exactly one POST /assessment/mid handler")

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
    "MID_APPROVAL_ROUTES",
    "MID_DELIVERY_ROUTES",
]
