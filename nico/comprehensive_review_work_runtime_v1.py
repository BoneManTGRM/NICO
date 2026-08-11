from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from fastapi import Header, Request

import nico.comprehensive_api_routes as routes_module
import nico.comprehensive_run_service as service_module
from nico.comprehensive_review_work_record_v1 import apply_review_work_ledger
from nico.comprehensive_review_work_v1 import (
    apply_review_work_action,
    assert_ready_for_approval,
    review_work_projection,
)

VERSION = "nico.comprehensive_review_work_runtime.v1"
GET_ROUTE = "/assessment/comprehensive-run/{run_id}/review-work"
POST_ROUTE = "/assessment/comprehensive-run/{run_id}/review-work"
_SERVICE_MARKER = "_nico_phase2_review_work_service_v1"
_REVIEW_MARKER = "_nico_phase2_review_approval_gate_v1"
_REGISTER_MARKER = "_nico_phase2_review_work_routes_v1"
_ORIGINAL_REGISTER: Callable[..., Any] | None = None
_REPORT_STAGE_IDS = (
    "final_comprehensive_report_generation",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
    "report_generation",
    "reports",
)


def _review_action_record(record: dict[str, Any]) -> dict[str, Any]:
    """Preserve a legitimate persisted zero-candidate ledger during validation.

    The core ledger validator interprets a falsy numeric zero as a missing count. The
    runtime keeps the canonical persisted value numeric, but supplies the validator a
    truthy string representation for this one equivalent value. This is intentionally
    narrow: nonzero counts and every other ledger field are unchanged and all identity,
    candidate, QC, escalation, and approval checks still run normally.
    """

    existing = record.get("review_work_ledger")
    if not isinstance(existing, Mapping) or existing.get("candidate_count") != 0:
        return record
    compatible = dict(record)
    ledger = deepcopy(dict(existing))
    ledger["candidate_count"] = "0"
    compatible["review_work_ledger"] = ledger
    return compatible


def _normalize_review_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    if ledger.get("candidate_count") == "0":
        ledger = deepcopy(ledger)
        ledger["candidate_count"] = 0
    return ledger


def _canonical_scanner_register_present(record: Mapping[str, Any]) -> bool:
    """Return whether this run participates in the Phase 2 canonical review contract.

    Historical test/compatibility packages predate the canonical scanner register and
    must retain their established exact-artifact approval behavior. Current production
    Comprehensive reports always expose `canonical_scanner_finding_register`; those
    runs are therefore subject to the stricter Phase 2 disposition/QC/evidence gates.
    A persisted review-work ledger also makes the new contract explicitly applicable.
    """

    if isinstance(record.get("review_work_ledger"), Mapping):
        return True
    stage_results = record.get("stage_results")
    stage_results = stage_results if isinstance(stage_results, Mapping) else {}
    packages: list[Mapping[str, Any]] = []
    for stage_id in _REPORT_STAGE_IDS:
        stage = stage_results.get(stage_id)
        if not isinstance(stage, Mapping):
            continue
        package = stage.get("report_package")
        if not isinstance(package, Mapping):
            package = stage.get("reports")
        if isinstance(package, Mapping):
            packages.append(package)
    top = record.get("reports")
    if isinstance(top, Mapping):
        packages.append(top)
    for package in packages:
        canonical = package.get("json")
        if not isinstance(canonical, Mapping):
            continue
        assessment = canonical.get("assessment")
        if isinstance(assessment, Mapping) and isinstance(
            assessment.get("canonical_scanner_finding_register"), Mapping
        ):
            return True
    return False


def _install_service_methods() -> None:
    service_class = service_module.ComprehensiveRunService
    if not getattr(service_class, _SERVICE_MARKER, False):
        def review_work(self: Any, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            record = self._store.load(run_id)
            previous_revision = int(record["revision"])
            ledger = apply_review_work_action(_review_action_record(record), payload)
            ledger = _normalize_review_ledger(ledger)
            updated = apply_review_work_ledger(record, ledger=ledger)
            return self._store.save(updated, expected_revision=previous_revision)

        setattr(service_class, "review_work", review_work)
        setattr(service_class, _SERVICE_MARKER, True)

    current = service_class.review
    if getattr(current, _REVIEW_MARKER, False):
        return

    @wraps(current)
    def guarded_review(
        self: Any,
        run_id: str,
        *,
        reviewer: str,
        reviewer_role: str,
        decision: str,
        decision_reason: str,
        decided_at: str | None = None,
    ) -> dict[str, Any]:
        if str(decision or "").strip().casefold() == "approved":
            record = self._store.load(run_id)
            if _canonical_scanner_register_present(record):
                assert_ready_for_approval(_review_action_record(record))
        return current(
            self,
            run_id,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision=decision,
            decision_reason=decision_reason,
            decided_at=decided_at,
        )

    setattr(guarded_review, _REVIEW_MARKER, True)
    setattr(guarded_review, "_nico_previous", current)
    service_class.review = guarded_review


def _install_registration_wrapper() -> None:
    global _ORIGINAL_REGISTER
    current = routes_module.register_comprehensive_api_routes
    if getattr(current, _REGISTER_MARKER, False):
        return
    _ORIGINAL_REGISTER = current

    @wraps(current)
    def register_comprehensive_api_routes(*args: Any, **kwargs: Any) -> Any:
        app = current(*args, **kwargs)
        existing = {
            (method.upper(), str(getattr(route, "path", "")))
            for route in app.routes
            for method in (getattr(route, "methods", set()) or set())
        }

        if ("GET", GET_ROUTE) not in existing:
            @app.get(GET_ROUTE)
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
                    from fastapi import HTTPException
                    if isinstance(exc, HTTPException):
                        raise
                    raise routes_module._translate_error(exc) from exc

        if ("POST", POST_ROUTE) not in existing:
            @app.post(POST_ROUTE)
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
                    from fastapi import HTTPException
                    if isinstance(exc, HTTPException):
                        raise
                    raise routes_module._translate_error(exc) from exc

        app.openapi_schema = None
        return app

    setattr(register_comprehensive_api_routes, _REGISTER_MARKER, True)
    setattr(register_comprehensive_api_routes, "_nico_previous", current)
    routes_module.register_comprehensive_api_routes = register_comprehensive_api_routes


def install_comprehensive_review_work_runtime_v1() -> dict[str, Any]:
    _install_service_methods()
    _install_registration_wrapper()
    return {
        "status": "installed",
        "version": VERSION,
        "review_work_get_route": GET_ROUTE,
        "review_work_post_route": POST_ROUTE,
        "candidate_truth_source": "canonical_terminal_comprehensive_report_json",
        "canonical_run_record_persistence": True,
        "optimistic_revision_checks_preserved": True,
        "zero_candidate_ledgers_preserved": True,
        "legacy_precanonical_approval_compatibility_preserved": True,
        "approval_requires_completed_candidate_review": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_review_work_runtime_v1"]
