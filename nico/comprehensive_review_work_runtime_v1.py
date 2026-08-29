from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Callable

from fastapi import Header, Request

import nico.comprehensive_api_routes as routes_module
import nico.comprehensive_run_service as service_module
from nico.comprehensive_approved_delivery_v3 import (
    attach_approved_delivery_package as attach_approved_delivery_package_v3,
)
from nico.comprehensive_approved_delivery_v1 import (
    require_new_report_after_evidence_request,
)
from nico.comprehensive_review_report_truth_v1 import synchronize_review_truth
from nico.comprehensive_review_work_record_v1 import apply_review_work_ledger
from nico.comprehensive_review_work_safe_v1 import (
    apply_review_work_action,
    assert_ready_for_approval,
    canonical_candidate_register,
    review_work_projection,
)
from nico.comprehensive_review_decision_v1 import (
    assert_expected_review_artifact_identity,
)

VERSION = "nico.comprehensive_review_work_runtime.v3"
GET_ROUTE = "/assessment/comprehensive-run/{run_id}/review-work"
POST_ROUTE = "/assessment/comprehensive-run/{run_id}/review-work"
_SERVICE_MARKER = "_nico_phase2_review_work_service_v3"
_REVIEW_MARKER = "_nico_phase2_review_approval_gate_v3"
_REGISTER_MARKER = "_nico_phase2_review_work_routes_v3"
_ORIGINAL_REGISTER: Callable[..., Any] | None = None


def _review_action_record(record: dict[str, Any]) -> dict[str, Any]:
    """Preserve a legitimate persisted zero-candidate ledger during validation."""

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
    try:
        canonical_candidate_register(record)
    except ValueError as exc:
        if str(exc) == "review_work_canonical_register_unavailable":
            return False
        raise
    return True


def _decision_timestamp(decided_at: str | None) -> str:
    normalized = str(decided_at or "").strip()
    return normalized or datetime.now(UTC).replace(microsecond=0).isoformat()


def _install_service_methods() -> None:
    # The service resolves this module global at call time. Rebinding here keeps the
    # existing service API while making the terminal approved-delivery boundary use
    # the single certified Comprehensive client PDF and exact Phase 2 ledger checks.
    service_module.attach_approved_delivery_package = attach_approved_delivery_package_v3
    service_class = service_module.ComprehensiveRunService
    if not getattr(service_class, _SERVICE_MARKER, False):
        def review_work(self: Any, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            record = self._store.load(run_id)
            service_module._require_exact_final_report_integrity(record)
            previous_revision = int(record["revision"])
            ledger = apply_review_work_action(_review_action_record(record), payload)
            ledger = _normalize_review_ledger(ledger)
            updated = apply_review_work_ledger(record, ledger=ledger)
            updated = synchronize_review_truth(updated)
            return self._store.save(updated, expected_revision=previous_revision)

        setattr(service_class, "review_work", review_work)
        setattr(service_class, _SERVICE_MARKER, True)

    current = service_class.review
    if getattr(current, _REVIEW_MARKER, False):
        return

    def guarded_review(
        self: Any,
        run_id: str,
        *,
        reviewer: str,
        reviewer_role: str,
        decision: str,
        decision_reason: str,
        decided_at: str | None = None,
        expected_artifact_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self._store.load(run_id)
        service_module._require_exact_final_report_integrity(record)
        previous_revision = int(record["revision"])
        normalized_decision = str(decision or "").strip().casefold()
        canonical_phase2 = False
        readiness_projection: Mapping[str, Any] | None = None
        if _canonical_scanner_register_present(record):
            canonical_phase2 = True
            if normalized_decision == "approved":
                readiness_projection = assert_ready_for_approval(
                    _review_action_record(record)
                )
        assert_expected_review_artifact_identity(
            record,
            expected_artifact_identity,
        )

        timestamp = _decision_timestamp(decided_at)
        decision_record = record
        if canonical_phase2:
            if readiness_projection is not None:
                ledger = readiness_projection.get("ledger")
                if not isinstance(ledger, Mapping):
                    raise ValueError("review_work_ledger_missing")
                normalized_ledger = _normalize_review_ledger(
                    deepcopy(dict(ledger))
                )
                decision_record = deepcopy(dict(record))
                decision_record["review_work_ledger"] = normalized_ledger
                decision_record["review_work_status"] = {
                    "artifact_schema": "nico.comprehensive_review_work_record.v1",
                    "audit_event_count": len(normalized_ledger.get("audit_events") or []),
                    "updated_at": str(normalized_ledger.get("updated_at") or ""),
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
                from nico.comprehensive_run_record import _record_hash

                decision_record["integrity_sha256"] = _record_hash(decision_record)
        manifest = service_module.build_reviewed_edition(
            decision_record,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision=normalized_decision,
            decision_reason=decision_reason,
            decided_at=timestamp,
        )
        if normalized_decision == "approved":
            require_new_report_after_evidence_request(decision_record, manifest)
        updated = service_module.apply_comprehensive_review_decision(
            decision_record,
            manifest=manifest,
        )
        return self._store.save(updated, expected_revision=previous_revision)

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
                    service_module._require_exact_final_report_integrity(record)
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
        "configurable_quality_control_sampling": True,
        "exception_queue_projection": True,
        "bulk_review_fails_closed_for_individual_attention": True,
        "report_truth_synchronized_before_approval": True,
        "final_human_decision_bound_into_accepted_edition": True,
        "approved_delivery_has_one_client_report": True,
        "approved_client_pdf_preserved_exactly": True,
        "approval_certificate_is_separate_json": True,
        "delivery_validates_exact_review_ledger": True,
        "four_hour_target_is_safety_gate": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_review_work_runtime_v1"]
