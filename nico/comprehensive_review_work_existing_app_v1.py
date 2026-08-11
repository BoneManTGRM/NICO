from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

import nico.comprehensive_api_routes as routes_module
from nico.comprehensive_review_work_runtime_v1 import (
    GET_ROUTE,
    POST_ROUTE,
    install_comprehensive_review_work_runtime_v1,
)
from nico.comprehensive_review_work_safe_v1 import review_work_projection

VERSION = "nico.comprehensive_review_work_existing_app.v1"


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected
        in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def _review_action_record(record: dict[str, Any]) -> dict[str, Any]:
    existing = record.get("review_work_ledger")
    if not isinstance(existing, dict) or existing.get("candidate_count") != 0:
        return record
    compatible = dict(record)
    ledger = dict(existing)
    ledger["candidate_count"] = "0"
    compatible["review_work_ledger"] = ledger
    return compatible


def install_comprehensive_review_work_existing_app_v1(target: FastAPI) -> dict[str, Any]:
    """Install the protected Phase 2 routes on an already-mounted Comprehensive app."""

    runtime = install_comprehensive_review_work_runtime_v1()
    get_count = _route_count(target, "GET", GET_ROUTE)
    post_count = _route_count(target, "POST", POST_ROUTE)
    if (get_count, post_count) not in {(0, 0), (1, 1)}:
        raise RuntimeError(
            "Partial Phase 2 review-work route registration detected: "
            f"GET={get_count} POST={post_count}"
        )

    if get_count == 0:
        async def get_comprehensive_review_work(
            run_id: str,
            request: Request,
            x_nico_admin_token: str = Header(default=""),
        ) -> dict[str, Any]:
            try:
                routes_module._authorize_review(x_nico_admin_token)
                controller = routes_module._controller(request)
                record = routes_module._service(controller).load(run_id)
                return routes_module._with_runtime_truth(
                    request,
                    review_work_projection(_review_action_record(record)),
                )
            except Exception as exc:
                if isinstance(exc, HTTPException):
                    raise
                raise routes_module._translate_error(exc) from exc

        async def mutate_comprehensive_review_work(
            run_id: str,
            request: Request,
            x_nico_admin_token: str = Header(default=""),
        ) -> dict[str, Any]:
            try:
                routes_module._authorize_review(x_nico_admin_token)
                payload = await request.json()
                if not isinstance(payload, dict):
                    raise TypeError("request_body_must_be_object")
                controller = routes_module._controller(request)
                service = routes_module._service(controller)
                record = service.review_work(run_id, payload)
                return routes_module._with_runtime_truth(
                    request,
                    review_work_projection(_review_action_record(record)),
                )
            except Exception as exc:
                if isinstance(exc, HTTPException):
                    raise
                raise routes_module._translate_error(exc) from exc

        target.add_api_route(
            GET_ROUTE,
            get_comprehensive_review_work,
            methods=["GET"],
            tags=["comprehensive-review"],
        )
        target.add_api_route(
            POST_ROUTE,
            mutate_comprehensive_review_work,
            methods=["POST"],
            tags=["comprehensive-review"],
        )
        target.openapi_schema = None

    get_count = _route_count(target, "GET", GET_ROUTE)
    post_count = _route_count(target, "POST", POST_ROUTE)
    if get_count != 1 or post_count != 1:
        raise RuntimeError(
            "Phase 2 review-work routes must exist exactly once: "
            f"GET={get_count} POST={post_count}"
        )
    status = {
        "artifact_schema": VERSION,
        "status": "installed",
        "review_work_get_route": GET_ROUTE,
        "review_work_post_route": POST_ROUTE,
        "review_work_get_route_count": get_count,
        "review_work_post_route_count": post_count,
        "protected_admin_authorization": True,
        "runtime_service_binding": runtime.get("approval_requires_completed_candidate_review") is True,
        "configurable_quality_control_sampling": runtime.get("configurable_quality_control_sampling") is True,
        "bulk_review_fails_closed_for_individual_attention": runtime.get("bulk_review_fails_closed_for_individual_attention") is True,
        "report_truth_synchronized_before_approval": runtime.get("report_truth_synchronized_before_approval") is True,
        "approved_delivery_has_one_client_report": runtime.get("approved_delivery_has_one_client_report") is True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    target.state.nico_phase2_review_work = status
    return status


__all__ = ["VERSION", "install_comprehensive_review_work_existing_app_v1"]
