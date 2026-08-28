from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

import nico.comprehensive_api_routes as routes_module
from nico.comprehensive_report_review_integrity_v1 import (
    install_comprehensive_report_review_integrity_v1,
)
from nico.comprehensive_review_work_runtime_v1 import (
    GET_ROUTE,
    POST_ROUTE,
    install_comprehensive_review_work_runtime_v1,
)
from nico.comprehensive_review_work_safe_v1 import review_work_projection
from nico.phase3_professional_assessment_v1 import install_phase3_professional_assessment_v1
from nico.phase4_client_delivery_runtime_v1 import install_phase4_client_delivery_runtime_v1

VERSION = "nico.comprehensive_review_work_existing_app.v5"


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
    """Install protected review controls, then terminal Phase 3 and Phase 4 upgrades."""

    integrity = install_comprehensive_report_review_integrity_v1()
    runtime = install_comprehensive_review_work_runtime_v1()
    if runtime.get("approval_requires_completed_candidate_review") is not True:
        raise RuntimeError(
            "Phase 2 server-side approval path is not bound to completed review readiness"
        )
    if integrity.get("phase4_final_delivery_requires_phase2_readiness") is not True:
        raise RuntimeError(
            "Phase 4 delivery path is not bound to exception-first Phase 2 readiness"
        )

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

    phase3 = install_phase3_professional_assessment_v1(target)
    if phase3.get("one_client_report") is not True:
        raise RuntimeError("Phase 3 violated the one Comprehensive client report boundary")
    if phase3.get("parallel_assessment_pipeline_created") is not False:
        raise RuntimeError("Phase 3 unexpectedly created a parallel assessment pipeline")
    if phase3.get("canonical_scoring_replaced") is not False:
        raise RuntimeError("Phase 3 unexpectedly replaced canonical scoring")
    if phase3.get("report_pipeline_replaced") is not False:
        raise RuntimeError("Phase 3 unexpectedly replaced the Comprehensive report pipeline")

    phase4 = install_phase4_client_delivery_runtime_v1(target)
    if phase4.get("one_client_report") is not True:
        raise RuntimeError("Phase 4 violated the one Comprehensive client report boundary")
    if phase4.get("parallel_assessment_pipeline_created") is not False:
        raise RuntimeError("Phase 4 unexpectedly created a parallel assessment pipeline")
    if phase4.get("report_pipeline_replaced") is not False:
        raise RuntimeError("Phase 4 unexpectedly replaced the Comprehensive report pipeline")
    if phase4.get("terminal_approved_delivery_builder_upgraded") is not True:
        raise RuntimeError("Phase 4 approved delivery builder is not terminally bound")
    if phase4.get("protected_download_validator_upgraded") is not True:
        raise RuntimeError("Phase 4 approved download validator is not terminally bound")

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
        "final_human_decision_bound_into_accepted_edition": runtime.get("final_human_decision_bound_into_accepted_edition") is True,
        "approved_delivery_has_one_client_report": runtime.get("approved_delivery_has_one_client_report") is True,
        "approved_client_pdf_preserved_exactly": runtime.get("approved_client_pdf_preserved_exactly") is True,
        "approval_certificate_is_separate_json": runtime.get("approval_certificate_is_separate_json") is True,
        "delivery_validates_exact_review_ledger": runtime.get("delivery_validates_exact_review_ledger") is True,
        "four_hour_target_is_safety_gate": runtime.get("four_hour_target_is_safety_gate") is True,
        "report_review_integrity": integrity,
        "phase3_professional_assessment": phase3,
        "phase4_client_delivery_hardening": phase4,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    target.state.nico_phase2_review_work = status
    target.state.nico_phase3_professional_assessment = phase3
    target.state.nico_phase4_client_delivery_runtime = phase4
    return status


__all__ = ["VERSION", "install_comprehensive_review_work_existing_app_v1"]
