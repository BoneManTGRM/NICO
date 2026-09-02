from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
import re
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from nico.admin_security import require_admin_write
from nico.comprehensive_api_controller import (
    ComprehensiveApiController,
    _canonical_final_report_outputs,
    _client_delivery_integrity_bound,
)
from nico.comprehensive_browser_continuation_dispatch_v1 import (
    dispatch_browser_continuation,
)
from nico.comprehensive_approved_delivery_v1 import validate_approved_delivery_package
from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunNotFound
from nico.comprehensive_review_decision_v1 import review_artifact_identity
from nico.exact_commit_binding import expected_commit_sha
from nico.hosted_assessment import normalize_repository
from nico.repository_snapshot import capture_repository_snapshot
from nico.provider_live_clients import ProviderClientError

VERSION = "nico.comprehensive_api_routes.v20"
_BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"
_FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
_ACTIVE_FINAL_REPORT_STATUSES = {"active", "pending", "queued", "running"}
_PUBLIC_INTAKE_RUN_ID_RE = re.compile(r"^comprun_[0-9a-f]{32}$")
_PUBLIC_INTAKE_LEASE_SECONDS = 300.0

COMPREHENSIVE_API_ROUTES = {
    ("POST", "/assessment/comprehensive-intake"),
    ("POST", "/assessment/comprehensive-run"),
    ("GET", "/assessment/comprehensive-run/{run_id}"),
    ("POST", "/assessment/comprehensive-run/{run_id}/continue"),
    ("GET", "/assessment/comprehensive-run/{run_id}/review-queue"),
    ("POST", "/assessment/comprehensive-run/{run_id}/review"),
    ("POST", "/assessment/comprehensive-run/{run_id}/authorize-delivery"),
    ("GET", "/assessment/comprehensive-run/{run_id}/approved-delivery-package"),
}

_SAFE_RUNTIME_REASONS = {
    "comprehensive_durable_storage_required": (
        "Comprehensive is temporarily unavailable because durable assessment storage is not configured."
    ),
    "comprehensive_sqlite_storage_unavailable": (
        "Comprehensive is temporarily unavailable because its configured durable storage could not be opened."
    ),
    "comprehensive_sqlite_persistent_volume_required": (
        "Comprehensive is temporarily unavailable because SQLite is not attached to a deployment-surviving volume. Configure Postgres or a persistent volume before retrying."
    ),
    "comprehensive_database_url_required": (
        "Comprehensive is temporarily unavailable because its production database is not configured."
    ),
    "comprehensive_database_url_must_be_postgres": (
        "Comprehensive is temporarily unavailable because its production database configuration is invalid."
    ),
}

def _controller(request: Request) -> ComprehensiveApiController:
    controller = getattr(request.app.state, "comprehensive_api_controller", None)
    if not isinstance(controller, ComprehensiveApiController):
        runtime = dict(getattr(request.app.state, "comprehensive_runtime", {}) or {})
        reason = str(runtime.get("reason") or "").strip()
        message = _SAFE_RUNTIME_REASONS.get(
            reason,
            "Comprehensive is temporarily unavailable because its production runtime is not ready.",
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "comprehensive_service_not_configured",
                "reason": reason or "runtime_not_ready",
                "message": message,
                "retryable": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    return controller


def _browser_projection_requested(request: Request) -> bool:
    return (
        str(request.headers.get("x-nico-browser-projection") or "").strip().lower()
        == _BROWSER_PROJECTION_VALUE
    )


def _detached_browser_continuation_enabled(request: Request) -> bool:
    runtime = dict(getattr(request.app.state, "comprehensive_runtime", {}) or {})
    return bool(
        runtime.get("detached_stage_execution") is True
        and runtime.get("continuation_transport_owns_provider_lifetime") is False
    )


def _browser_continuation_has_work(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    bounded = payload.get("max_stages")
    if bounded is None:
        return True
    value = int(bounded)
    if value < 0:
        raise ValueError("max_stages_must_be_non_negative")
    return value > 0


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ComprehensiveRunNotFound):
        return HTTPException(
            status_code=404,
            detail={
                "code": "comprehensive_run_not_found",
                "message": (
                    "The run ID is not present in the active durable store. This can indicate "
                    "a replaced container without persistent storage or requests routed to a "
                    "different backend deployment. Start a new run only after runtime diagnostics "
                    "confirm deployment-surviving persistence."
                ),
                "retryable": False,
                "persistence_diagnostic_required": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    if isinstance(exc, (ComprehensiveRunConflict, ValueError)) and str(exc) in {
        "public_intake_idempotency_conflict",
        "public_intake_legacy_run_unbound",
    }:
        return HTTPException(
            status_code=409,
            detail={
                "code": str(exc),
                "message": "The reserved intake identity is already bound and cannot be changed or retroactively rebound.",
                "retryable": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    if isinstance(exc, ComprehensiveRunConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError) and str(exc) == "public_intake_run_id_invalid":
        return HTTPException(
            status_code=422,
            detail={
                "code": "public_intake_run_id_invalid",
                "message": "The reserved public intake identity is invalid.",
                "retryable": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    if isinstance(exc, ProviderClientError):
        definitions = {
            "provider_read_only_authentication_required": (403, False),
            "provider_repository_not_publicly_accessible": (403, False),
            "provider_permission_denied": (403, False),
            "provider_repository_not_found": (404, False),
            "provider_anonymous_rate_limit_reached": (429, True),
            "provider_rate_limited": (429, True),
            "provider_service_unavailable": (503, True),
            "provider_network_timeout": (504, True),
            "provider_malformed_response": (502, False),
            "provider_repository_empty": (422, False),
            "provider_required_source_evidence_unavailable": (422, False),
        }
        status, retryable = definitions.get(exc.code, (502, bool(exc.retryable)))
        return HTTPException(
            status_code=status,
            detail={
                "code": exc.code,
                "message": "Provider evidence acquisition failed safely; no incomplete assessment report was created.",
                "retryable": retryable,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    if isinstance(exc, ValueError) and str(exc) == "stale_review_artifact_identity":
        return HTTPException(
            status_code=409,
            detail={
                "code": "stale_review_artifact_identity",
                "message": (
                    "The report artifact set changed after it was loaded. "
                    "Reload and review the current exact artifacts before approving "
                    "or authorizing client delivery."
                ),
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    if isinstance(exc, ValueError) and str(exc).startswith("browser_projection_"):
        return HTTPException(
            status_code=503,
            detail={
                "code": "comprehensive_browser_projection_integrity_invalid",
                "message": (
                    "The bounded run status did not match its durable canonical "
                    "revision. Exact-run status is unavailable until integrity is "
                    "restored."
                ),
                "retryable": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="comprehensive_service_error")


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


def _bounded_required(value: Any, field: str, limit: int) -> str:
    normalized = _required(value, field)
    if len(normalized) > limit:
        raise ValueError(f"{field}_too_long")
    return normalized


def public_intake_identity(payload: Mapping[str, Any]) -> tuple[str, str]:
    """Return the one browser-reserved identity for a public intake."""

    supplied = str(payload.get("run_id") or "").strip().lower()
    if supplied and not _PUBLIC_INTAKE_RUN_ID_RE.fullmatch(supplied):
        raise ValueError("public_intake_run_id_invalid")
    run_id = supplied or f"comprun_{uuid4().hex}"
    return run_id, f"ledger_comprehensive_{run_id.removeprefix('comprun_')}"


def _public_intake_request_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _matching_public_intake_response(
    request: Request,
    *,
    payload: Mapping[str, Any],
    expected_commit_sha_value: str,
) -> dict[str, Any] | None:
    """Validate the canonical row after its full request hash was bound."""

    controller = _controller(request)
    status_reader = getattr(controller, "status_read_only", None)
    if not callable(status_reader):
        return None
    run_id = str(payload.get("run_id") or "")
    try:
        existing = status_reader(run_id)
    except ComprehensiveRunNotFound:
        return None
    expected_identity = {
        "repository": payload.get("repository"),
        "customer_id": payload.get("customer_id"),
        "project_id": payload.get("project_id"),
        "assessment_depth": payload.get("assessment_depth"),
        "report_language": payload.get("report_language"),
    }
    if any(
        str(existing.get(field) or "") != str(value or "")
        for field, value in expected_identity.items()
    ):
        raise ComprehensiveRunConflict("public_intake_idempotency_conflict")
    if expected_commit_sha_value and str(existing.get("commit_sha") or "").lower() != str(
        expected_commit_sha_value
    ).lower():
        raise ComprehensiveRunConflict("public_intake_idempotency_conflict")
    expected_metadata = (
        payload.get("engagement_metadata")
        if isinstance(payload.get("engagement_metadata"), Mapping)
        else {}
    )
    existing_metadata = (
        existing.get("engagement_metadata")
        if isinstance(existing.get("engagement_metadata"), Mapping)
        else {}
    )
    if str(existing_metadata.get("engagement_metadata_sha256") or "") != str(
        expected_metadata.get("engagement_metadata_sha256") or ""
    ):
        raise ComprehensiveRunConflict("public_intake_idempotency_conflict")
    return _with_runtime_truth(
        request,
        {**existing, "operation": "intake_idempotent_reuse", "intake_idempotent_reuse": True},
    )


def _assert_no_unbound_existing_run(
    request: Request,
    *,
    service: Any,
    run_id: str,
) -> None:
    """Never retroactively bind a legacy/direct run to a new intake request."""

    if service.load_public_intake(run_id) is not None:
        return
    status_reader = getattr(_controller(request), "status_read_only", None)
    if not callable(status_reader):
        return
    try:
        status_reader(run_id)
    except ComprehensiveRunNotFound:
        return
    raise ComprehensiveRunConflict("public_intake_legacy_run_unbound")


def _prepare_public_intake_reservation_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("request_body_must_be_object")
    if payload.get("authorized") is not True or payload.get("authorization_confirmed") is not True:
        raise ValueError("explicit_authorization_required")

    from nico.hosted_provider_comprehensive_runtime_v1 import (
        _access_mode as hosted_access_mode,
        assert_no_raw_provider_credentials,
        canonical_repository_label,
        normalize_submitted_provider_repository,
    )
    from nico.provider_neutral_contract import ProviderAccessMode
    from nico.provider_platform_contract_v1 import ProviderKind
    from nico.comprehensive_engagement_metadata_v1 import (
        _literal,
        build_comprehensive_engagement_metadata,
    )
    from nico.comprehensive_intake_display_metadata_v2 import (
        _human_evidence_with_display_metadata,
    )
    from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence

    assert_no_raw_provider_credentials(payload)
    provider, provider_repository, organization, provider_project = (
        normalize_submitted_provider_repository(
            payload.get("repository"),
            payload.get("provider"),
            organization=payload.get("provider_organization"),
            project=payload.get("provider_project"),
        )
    )
    requested_access_mode = hosted_access_mode(
        payload.get("provider_access_mode") or ProviderAccessMode.AUTO.value
    )
    if requested_access_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY:
        raise ValueError("provider_authenticated_access_operator_only")
    if requested_access_mode is ProviderAccessMode.AUTO:
        requested_access_mode = ProviderAccessMode.ANONYMOUS_PUBLIC
    repository = (
        normalize_repository(provider_repository)
        if provider is ProviderKind.GITHUB
        else canonical_repository_label(
            provider,
            provider_repository,
            organization=organization,
            project=provider_project,
        )
    )
    client_name = _literal(payload.get("client_name"), 180)
    project_name = _literal(payload.get("project_name"), 180)
    raw_human_evidence = _human_evidence_with_display_metadata(
        payload.get("human_evidence"),
        client_name=client_name,
        project_name=project_name,
    )
    human_evidence = normalize_strategic_human_evidence(raw_human_evidence)
    engagement_metadata = build_comprehensive_engagement_metadata(
        client_name=client_name,
        project_name=project_name,
        human_evidence=human_evidence,
        field_states=payload.get("engagement_field_states"),
    )
    run_id, evidence_ledger_id = public_intake_identity(payload)
    return {
        "run_id": run_id,
        "evidence_ledger_id": evidence_ledger_id,
        "repository": repository,
        "provider": provider.value,
        "provider_repository": provider_repository,
        "provider_organization": organization,
        "provider_project": provider_project,
        "customer_id": _bounded_required(
            payload.get("customer_id") or "default_customer", "customer_id", 240
        ),
        "project_id": _bounded_required(
            payload.get("project_id") or "default_project", "project_id", 240
        ),
        "client_name": client_name,
        "project_name": project_name,
        "assessment_depth": _bounded_required(
            payload.get("assessment_depth") or "strategic", "assessment_depth", 80
        ),
        "report_language": _bounded_required(
            payload.get("report_language") or "en", "report_language", 20
        ),
        "human_evidence": human_evidence,
        "engagement_field_states": engagement_metadata["field_states"],
        "engagement_metadata": engagement_metadata,
        "authorized_by": _bounded_required(
            payload.get("authorized_by") or "public_assessment_requester",
            "authorized_by",
            600,
        ),
        "authorization_scope": _bounded_required(
            payload.get("authorization_scope")
            or "authorized defensive repository assessment",
            "authorization_scope",
            4000,
        ),
        "expected_commit_sha": expected_commit_sha(payload),
        "requested_access_mode": requested_access_mode.value,
        "authorized": True,
        "authorization_confirmed": True,
    }


def _authorize_review(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "strategic_review_admin_authentication_required",
            "message": "Operator admin authentication is required for Comprehensive internal review and approved delivery access.",
            "admin_write": status,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )


def _runtime_persistence(request: Request) -> dict[str, Any]:
    runtime = dict(getattr(request.app.state, "comprehensive_runtime", {}) or {})
    adapter = str(runtime.get("persistence_adapter") or "unavailable")
    configured = runtime.get("configured") is True
    durable = configured and bool(
        runtime.get("durability_verified")
        or adapter in {"postgres", "sqlite"}
    )
    result: dict[str, Any] = {
        "recorded": configured,
        "durable": durable,
        "adapter": adapter,
        "storage_source": str(runtime.get("storage_source") or adapter),
    }
    if "survives_container_replacement_verified" in runtime:
        result["survives_container_replacement_verified"] = configured and (
            runtime.get("survives_container_replacement_verified") is True
        )
    elif configured and adapter == "postgres":
        result["survives_container_replacement_verified"] = True
    return result


def _with_runtime_truth(
    request: Request,
    response: dict[str, Any],
) -> dict[str, Any]:
    delivery_allowed = response.get("client_delivery_allowed") is True
    return {
        **response,
        "persistence": _runtime_persistence(request),
        "human_review_required": True,
        "client_delivery_allowed": delivery_allowed,
    }


def _service(controller: ComprehensiveApiController) -> Any:
    service = getattr(controller, "_service", None)
    if service is None:
        raise RuntimeError("comprehensive_review_service_unavailable")
    return service


def _approved_delivery_projection(record: dict[str, Any]) -> dict[str, Any]:
    candidate = record.get("approved_delivery_package")
    if not isinstance(candidate, dict):
        return {}
    certificate = (
        candidate.get("certificate")
        if isinstance(candidate.get("certificate"), dict)
        else {}
    )
    return {
        "artifact_schema": str(candidate.get("artifact_schema") or ""),
        "status": str(candidate.get("status") or ""),
        "filename": str(candidate.get("filename") or ""),
        "zip_sha256": str(candidate.get("zip_sha256") or ""),
        "zip_size_bytes": int(candidate.get("zip_size_bytes") or 0),
        "artifact_count": int(candidate.get("artifact_count") or 0),
        "certificate": certificate,
        "human_review_required": True,
        "client_delivery_allowed": candidate.get("client_delivery_allowed") is True,
    }


def _review_projection(
    response: dict[str, Any],
    record: dict[str, Any],
    *,
    include_review_artifact_identity: bool = True,
) -> dict[str, Any]:
    response_projection = (
        response.get("response_projection")
        if isinstance(response.get("response_projection"), Mapping)
        else {}
    )
    approval_invalidated = (
        response_projection.get("approval_invalidated_by_artifact_mismatch")
        is True
    )
    delivery_invalidated = (
        response_projection.get("delivery_authorization_invalidated") is True
    )
    rejection_invalidated = (
        response_projection.get("rejection_invalidated_by_review_mismatch")
        is True
    )
    review_decision_integrity_valid = (
        response_projection.get("review_decision_integrity_valid") is True
    )
    allowed = response.get("client_delivery_allowed") is True
    approved_projection = (
        response.get("approval_status") == "approved_final"
        and response.get("human_review_completed") is True
    )
    delivery_status = str(response.get("delivery_status") or "").strip()
    if not delivery_status:
        delivery_status = (
            "approved_for_delivery"
            if allowed
            else "pending_authorization"
            if str(response.get("status") or "").strip().casefold() == "approved"
            and response.get("human_review_completed") is True
            else "blocked"
        )
    projected = {**response, "delivery_status": delivery_status}
    if include_review_artifact_identity:
        projected["review_artifact_identity"] = review_artifact_identity(record)
    review_decision = record.get("review_decision")
    if (
        not approval_invalidated
        and not rejection_invalidated
        and review_decision_integrity_valid
        and isinstance(review_decision, dict)
    ):
        review = (
            review_decision.get("review")
            if isinstance(review_decision.get("review"), Mapping)
            else {}
        )
        decision = str(review.get("decision") or "").strip().casefold()
        decision_matches_projection = (
            (approved_projection and decision == "approved")
            or (response.get("approval_status") == "rejected" and decision == "rejected")
            or (
                response.get("approval_status") == "pending_human_approval"
                and decision == "request_more_evidence"
            )
        )
        if decision_matches_projection:
            projected["review_decision"] = review_decision
    if (
        not approval_invalidated
        and not rejection_invalidated
        and review_decision_integrity_valid
        and not delivery_invalidated
        and isinstance(review_decision, dict)
        and isinstance(record.get("review_context"), dict)
    ):
        projected["review_context"] = record["review_context"]
    if (
        allowed
        and not approval_invalidated
        and not delivery_invalidated
        and isinstance(record.get("delivery_authorization"), dict)
    ):
        projected["delivery_authorization"] = record["delivery_authorization"]
    delivery_projection = (
        _approved_delivery_projection(record)
        if allowed and not approval_invalidated
        else {}
    )
    if delivery_projection:
        projected["approved_delivery_package"] = delivery_projection
    public_record = projected.get("record")
    if isinstance(public_record, dict):
        public_record["status"] = projected["status"]
        public_record["human_review_completed"] = projected["human_review_completed"]
        public_record["client_delivery_allowed"] = allowed
        public_record["delivery_status"] = projected["delivery_status"]
    return projected


def _status_projection(
    controller_value: ComprehensiveApiController,
    run_id: str,
    browser_projection: bool,
    operation: str = "status",
) -> dict[str, Any]:
    """Load and assemble an exact status response outside the ASGI event loop."""

    record = _service(controller_value).load(run_id)
    response = controller_value._response(
        record,
        operation=operation,
        browser_projection=browser_projection,
    )
    return _review_projection(
        response,
        record,
        # Public terminal consumers cannot approve an artifact and do not consume this
        # expensive full-package digest. Reviewer/admin reads keep the exact identity.
        include_review_artifact_identity=not browser_projection,
    )


def _durable_browser_projection_builder(
    controller_value: ComprehensiveApiController,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Build the exact small response committed beside one validated run revision."""

    response = controller_value._response(
        record,
        operation="status",
        browser_projection=True,
    )
    projected = _review_projection(
        response,
        record,
        include_review_artifact_identity=False,
    )
    response_projection = (
        dict(projected.get("response_projection") or {})
        if isinstance(projected.get("response_projection"), Mapping)
        else {}
    )
    response_projection.update(
        {
            "durable_projection": True,
            "durable_projection_schema": "nico.comprehensive-browser-projection.v1",
            "canonical_artifact_authority": "full_exact_run_artifact_endpoints",
            "human_review_authority_unchanged": True,
            "client_delivery_authority_unchanged": True,
        }
    )
    projected["response_projection"] = response_projection
    return projected


def _load_durable_browser_projection(
    controller_value: ComprehensiveApiController,
    run_id: str,
) -> dict[str, Any] | None:
    service = _service(controller_value)
    loader = getattr(service, "load_browser_projection", None)
    if not callable(loader):
        return None
    return loader(run_id)


def _continue_projection(
    controller_value: ComprehensiveApiController,
    run_id: str,
    payload: dict[str, Any],
    browser_projection: bool,
) -> dict[str, Any]:
    """Assemble the first continuation projection outside the ASGI event loop."""

    return controller_value.continue_run(
        run_id,
        payload,
        browser_projection=browser_projection,
    )


def _continued_browser_projection_is_authoritative(
    response: Mapping[str, Any],
) -> bool:
    """Reuse a bounded continuation projection when no second load adds truth.

    A durable running final-report marker is authoritative for the current tick;
    asynchronous publication may complete immediately afterward and the next browser
    poll will observe it. Other nonterminal stages retain the historical reload so no
    background-stage publication race is widened by this final-report-only repair.

    A terminal response may be reused only before human disposition or delivery.
    Reviewer and delivery states still reload the full canonical record so their
    protected receipts remain available to the public projection.
    """

    if response.get("terminal") is True:
        return (
            response.get("human_review_completed") is False
            and response.get("client_delivery_allowed") is False
        )

    current_stage = str(response.get("current_stage") or "").strip()
    if current_stage != _FINAL_REPORT_STAGE_ID:
        return False

    record = response.get("record")
    stage_results = (
        record.get("stage_results")
        if isinstance(record, Mapping)
        and isinstance(record.get("stage_results"), Mapping)
        else {}
    )
    final_stage = stage_results.get(_FINAL_REPORT_STAGE_ID)
    final_status = (
        str(final_stage.get("status") or "").strip().casefold()
        if isinstance(final_stage, Mapping)
        else ""
    )
    if final_status in _ACTIVE_FINAL_REPORT_STATUSES:
        return True

    activity = response.get("active_stage_execution")
    activity_status = (
        str(activity.get("status") or "").strip().casefold()
        if isinstance(activity, Mapping)
        else ""
    )
    return activity_status in _ACTIVE_FINAL_REPORT_STATUSES


def _review_queue_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": code,
            "message": message,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )


def _canonical_review_queue_register(record: Mapping[str, Any]) -> Mapping[str, Any]:
    if record.get("terminal") is not True or str(record.get("status") or "") != "review_required":
        raise _review_queue_error(
            "comprehensive_review_queue_terminal_run_required",
            "The exception-first reviewer queue is available only at the exact terminal human-review boundary.",
        )
    if record.get("human_review_completed") is True or record.get("client_delivery_allowed") is True:
        raise _review_queue_error(
            "comprehensive_review_queue_preapproval_boundary_required",
            "The exception-first queue is a pre-approval technical-review surface and cannot project an approved delivery state.",
        )

    identity = record.get("identity")
    if not isinstance(identity, Mapping):
        raise _review_queue_error(
            "comprehensive_review_queue_identity_missing",
            "The exact run identity is unavailable.",
        )
    stage_results = record.get("stage_results")
    stage_results = stage_results if isinstance(stage_results, Mapping) else {}

    final_stage = stage_results.get("final_comprehensive_report_generation")
    final_stage = final_stage if isinstance(final_stage, Mapping) else {}
    final_package = final_stage.get("report_package")
    if not isinstance(final_package, Mapping):
        final_package = final_stage.get("reports")
    report_candidates = [final_package] if isinstance(final_package, Mapping) else []

    for package in report_candidates:
        canonical = package.get("json")
        if not isinstance(canonical, Mapping):
            continue
        canonical_identity = canonical.get("identity")
        if not isinstance(canonical_identity, Mapping):
            continue
        identity_matches = all(
            str(canonical_identity.get(field) or "").strip()
            == str(identity.get(field) or "").strip()
            for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
        )
        if not identity_matches:
            raise _review_queue_error(
                "comprehensive_review_queue_identity_mismatch",
                "The terminal report candidate register does not match the exact run identity.",
            )
        final_report, _assessment = _canonical_final_report_outputs(dict(record))
        if not final_report or dict(final_report) != dict(package):
            raise _review_queue_error(
                "comprehensive_review_queue_artifact_integrity_invalid",
                "The exact terminal review package failed immutable artifact validation.",
            )
        assessment = canonical.get("assessment")
        if not isinstance(assessment, Mapping):
            continue
        register = assessment.get("canonical_scanner_finding_register")
        if not isinstance(register, Mapping):
            continue
        findings = register.get("findings")
        if not isinstance(findings, list):
            raise _review_queue_error(
                "comprehensive_review_queue_findings_missing",
                "The terminal report candidate register does not contain its canonical findings list.",
            )
        try:
            declared_count = int(register.get("candidate_record_count"))
        except (TypeError, ValueError):
            declared_count = -1
        if declared_count != len(findings):
            raise _review_queue_error(
                "comprehensive_review_queue_candidate_count_mismatch",
                "The terminal report candidate count does not reconcile with the canonical findings list.",
            )
        return register

    raise _review_queue_error(
        "comprehensive_review_queue_register_unavailable",
        "The exact terminal report does not contain the canonical scanner candidate register.",
    )


def _review_queue_projection(record: dict[str, Any]) -> dict[str, Any]:
    identity = record.get("identity")
    if not isinstance(identity, Mapping):
        raise _review_queue_error(
            "comprehensive_review_queue_identity_missing",
            "The exact run identity is unavailable.",
        )
    register = _canonical_review_queue_register(record)
    triage = register.get("technical_triage")
    triage = triage if isinstance(triage, Mapping) else {}
    return {
        "artifact_schema": "nico.exception_first_reviewer_queue.v1",
        "service_id": "comprehensive",
        "operation": "review_queue",
        "run_id": str(identity.get("run_id") or ""),
        "repository": str(identity.get("repository") or ""),
        "commit_sha": str(identity.get("commit_sha") or ""),
        "evidence_ledger_id": str(identity.get("evidence_ledger_id") or ""),
        "status": "review_required",
        "terminal": True,
        "read_only": True,
        "source": "canonical_terminal_comprehensive_report_json",
        "candidate_count": int(register.get("candidate_record_count") or 0),
        "human_review_work_units": int(triage.get("human_review_work_units") or 0),
        "candidate_register": dict(register),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _approved_delivery_response(record: dict[str, Any]) -> Response:
    final_report, _assessment = _canonical_final_report_outputs(record)
    if not final_report or not _client_delivery_integrity_bound(record):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approved_delivery_package_integrity_invalid",
                "message": "The exact approved artifacts or delivery authorization failed immutable-package validation.",
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    candidate = record.get("approved_delivery_package")
    validation = validate_approved_delivery_package(record, candidate)
    if validation["status"] != "valid":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approved_delivery_package_unavailable",
                "message": "The approved delivery package is missing or failed immutable-package validation.",
                "validation_errors": validation["validation_errors"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    if record.get("status") != "approved" or record.get("client_delivery_allowed") is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approved_delivery_package_not_authorized",
                "message": "This exact run is not approved for client delivery.",
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    assert isinstance(candidate, dict)
    try:
        archive = base64.b64decode(str(candidate.get("zip_base64") or ""), validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approved_delivery_package_invalid",
                "message": "The approved delivery package failed base64 integrity validation.",
            },
        ) from exc
    if not archive.startswith(b"PK"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approved_delivery_package_invalid",
                "message": "The approved delivery package failed ZIP integrity validation.",
            },
        )
    filename = str(
        candidate.get("filename")
        or f"nico-comprehensive-delivery-{record['identity']['run_id']}-APPROVED.zip"
    )
    filename = filename.replace("\r", "").replace("\n", "").replace('"', "'")
    certificate = (
        candidate.get("certificate")
        if isinstance(candidate.get("certificate"), dict)
        else {}
    )
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private, max-age=0",
            "X-NICO-Run-ID": str(record["identity"]["run_id"]),
            "X-NICO-Delivery-Package-SHA256": str(candidate.get("zip_sha256") or ""),
            "X-NICO-Accepted-Edition-SHA256": str(
                certificate.get("accepted_edition_manifest_sha256") or ""
            ),
            "X-NICO-Delivery-Certificate-SHA256": str(
                certificate.get("delivery_authorization_certificate_sha256") or ""
            ),
        },
    )


def _public_intake_failure_truth(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, ProviderClientError):
        return str(exc.code), bool(exc.retryable)
    if isinstance(exc, ComprehensiveRunConflict):
        return str(exc), False
    if isinstance(exc, (TypeError, ValueError)):
        return str(exc).split(":", 1)[0], False
    return "public_intake_internal_failure", True


def _public_intake_reservation_projection(
    request: Request,
    reservation: Mapping[str, Any],
) -> dict[str, Any]:
    payload = (
        reservation.get("payload")
        if isinstance(reservation.get("payload"), Mapping)
        else {}
    )
    status = str(reservation.get("status") or "")
    failed = status != "acquiring"
    failure_code = str(reservation.get("failure_code") or "")
    if status == "accepted" and not failure_code:
        failure_code = "public_intake_accepted_run_missing"
    return _with_runtime_truth(
        request,
        {
            "artifact_schema": "nico.comprehensive_public_intake_reservation.v1",
            "service_id": "comprehensive",
            "operation": "intake_failed" if failed else "intake_pending",
            "intake_reserved": True,
            "run_id": str(reservation.get("run_id") or ""),
            "repository": str(payload.get("repository") or ""),
            "repository_provider": str(payload.get("provider") or ""),
            "customer_id": str(payload.get("customer_id") or ""),
            "project_id": str(payload.get("project_id") or ""),
            "assessment_depth": str(payload.get("assessment_depth") or ""),
            "report_language": str(payload.get("report_language") or ""),
            "provider_access_mode": (
                "pending" if not failed else str(payload.get("requested_access_mode") or "auto")
            ),
            "provider_credential_used": False,
            "current_stage": "provider_source_acquisition",
            "progress_percent": 0,
            "status": "failed" if failed else "running",
            "canonical_status": "intake_failed" if failed else "intake_pending",
            "terminal": failed,
            "failure_code": failure_code if failed else "",
            "retryable": bool(reservation.get("failure_retryable")) if failed else True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )


def _reserve_prepared_public_intake(
    request: Request,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    controller = _controller(request)
    service = getattr(controller, "_service", None)
    request_hash = _public_intake_request_sha256(payload)
    if service is None:
        return {
            "run_id": payload["run_id"],
            "request_sha256": request_hash,
            "status": "acquiring",
            "lease_id": "contract_test_controller",
            "payload": dict(payload),
            "lease_owner": True,
        }
    _assert_no_unbound_existing_run(
        request,
        service=service,
        run_id=str(payload.get("run_id") or ""),
    )
    return service.reserve_public_intake(
        run_id=str(payload.get("run_id") or ""),
        request_sha256=request_hash,
        payload=payload,
        lease_seconds=_PUBLIC_INTAKE_LEASE_SECONDS,
    )


def _accepted_public_intake_response(
    request: Request,
    reservation: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(reservation.get("payload") or {})
    existing = _matching_public_intake_response(
        request,
        payload=payload,
        expected_commit_sha_value=str(reservation.get("accepted_commit_sha") or ""),
    )
    return existing or _public_intake_reservation_projection(request, reservation)


def _execute_public_intake_reservation(
    request: Request,
    reservation: Mapping[str, Any],
) -> dict[str, Any]:
    from nico.hosted_provider_comprehensive_runtime_v1 import capture_hosted_provider_snapshot
    from nico.provider_platform_contract_v1 import ProviderKind

    payload = dict(reservation.get("payload") or {})
    run_id = _required(reservation.get("run_id"), "run_id")
    lease_id = _required(reservation.get("lease_id"), "public_intake_lease_id")
    controller = _controller(request)
    service = getattr(controller, "_service", None)

    def heartbeat() -> None:
        if service is None:
            return
        if not service.heartbeat_public_intake(
            run_id=run_id,
            lease_id=lease_id,
            lease_until_epoch=time.time() + _PUBLIC_INTAKE_LEASE_SECONDS,
        ):
            raise ComprehensiveRunConflict("public_intake_reservation_lease_lost")

    try:
        heartbeat()
        provider = ProviderKind(str(payload.get("provider") or ""))
        context = {
            "run_id": run_id,
            "repository": str(payload.get("repository") or ""),
            "customer_id": str(payload.get("customer_id") or ""),
            "project_id": str(payload.get("project_id") or ""),
            "authorized": True,
            "authorized_by": str(payload.get("authorized_by") or ""),
            "authorization_scope": str(payload.get("authorization_scope") or ""),
            "expected_commit_sha": str(payload.get("expected_commit_sha") or ""),
            "provider_repository": str(payload.get("provider_repository") or ""),
            "provider_organization": str(payload.get("provider_organization") or ""),
            "provider_project": str(payload.get("provider_project") or ""),
            "provider_access_mode": str(payload.get("requested_access_mode") or "auto"),
            "provider_credential_fallback_authorized": False,
            "_provider_activity_callback": heartbeat,
        }
        snapshot = (
            capture_repository_snapshot(context)
            if provider is ProviderKind.GITHUB
            else capture_hosted_provider_snapshot(context, provider)
        )
        heartbeat()
        if snapshot.get("status") != "attached" or not str(snapshot.get("commit_sha") or "").strip():
            provider_failure = str(snapshot.get("provider_access_failure_code") or "").strip()
            if provider_failure:
                raise ProviderClientError(provider_failure)
            raise ValueError("provider_required_source_evidence_unavailable")
        commit_sha = str(snapshot["commit_sha"]).strip().lower()
        requested_sha = str(payload.get("expected_commit_sha") or "").lower()
        if requested_sha and commit_sha != requested_sha:
            raise ValueError("repository_snapshot_commit_mismatch")
        heartbeat()
        try:
            response = controller.start(
                {
                    "repository": payload["repository"],
                    "commit_sha": commit_sha,
                    "run_id": run_id,
                    "evidence_ledger_id": payload["evidence_ledger_id"],
                    "customer_id": payload["customer_id"],
                    "project_id": payload["project_id"],
                    "client_name": payload.get("client_name"),
                    "project_name": payload.get("project_name"),
                    "assessment_depth": payload["assessment_depth"],
                    "report_language": payload["report_language"],
                    "human_evidence": payload.get("human_evidence"),
                    "engagement_field_states": payload.get("engagement_field_states"),
                    "repository_provider": provider.value,
                    "provider_access_mode": snapshot.get("access_mode") or "anonymous_public",
                    "provider_credential_used": snapshot.get("credential_used") is True,
                    "authorized": True,
                    "authorization_confirmed": True,
                }
            )
        except ComprehensiveRunConflict:
            response = _matching_public_intake_response(
                request,
                payload=payload,
                expected_commit_sha_value=commit_sha,
            )
            if response is None:
                raise
        if service is not None and not service.complete_public_intake(
            run_id=run_id,
            lease_id=lease_id,
            commit_sha=commit_sha,
        ):
            completed = service.load_public_intake(run_id)
            if not completed or completed.get("status") != "accepted":
                raise ComprehensiveRunConflict("public_intake_reservation_completion_conflict")
        return _with_runtime_truth(
            request,
            {
                **response,
                "operation": "intake_started",
                "repository_snapshot": snapshot,
                "client_name": payload.get("client_name"),
                "project_name": payload.get("project_name"),
                "repository_provider": provider.value,
                "provider_access_mode": snapshot.get("access_mode") or "anonymous_public",
                "provider_credential_used": snapshot.get("credential_used") is True,
            },
        )
    except Exception as exc:
        failure_code, retryable = _public_intake_failure_truth(exc)
        if service is not None:
            service.fail_public_intake(
                run_id=run_id,
                lease_id=lease_id,
                failure_code=failure_code,
                retryable=retryable,
            )
        raise


def _reserved_public_intake_status(request: Request, run_id: str) -> dict[str, Any]:
    service = _service(_controller(request))
    reservation = service.load_public_intake(run_id)
    if reservation is None:
        raise ComprehensiveRunNotFound(run_id)
    if reservation.get("status") == "acquiring":
        claimed = service.reserve_public_intake(
            run_id=run_id,
            request_sha256=str(reservation.get("request_sha256") or ""),
            payload=dict(reservation.get("payload") or {}),
            lease_seconds=_PUBLIC_INTAKE_LEASE_SECONDS,
        )
        if claimed.get("lease_owner") is True:
            return _execute_public_intake_reservation(request, claimed)
        reservation = claimed
    if reservation.get("status") == "accepted":
        return _accepted_public_intake_response(request, reservation)
    return _public_intake_reservation_projection(request, reservation)


def _reconcile_public_intake_after_run_recovery(
    request: Request,
    *,
    run_id: str,
    response: Mapping[str, Any],
) -> None:
    service = _service(_controller(request))
    reservation = service.load_public_intake(run_id)
    if not reservation or reservation.get("status") != "acquiring":
        return
    payload = dict(reservation.get("payload") or {})
    if _matching_public_intake_response(
        request,
        payload=payload,
        expected_commit_sha_value=str(response.get("commit_sha") or ""),
    ) is None:
        return
    service.reconcile_public_intake_accepted(
        run_id=run_id,
        request_sha256=str(reservation.get("request_sha256") or ""),
        commit_sha=str(response.get("commit_sha") or ""),
    )


def _intake(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    prepared = _prepare_public_intake_reservation_payload(payload)
    reservation = _reserve_prepared_public_intake(request, prepared)
    if reservation.get("lease_owner") is not True:
        if reservation.get("status") == "accepted":
            return _accepted_public_intake_response(request, reservation)
        return _public_intake_reservation_projection(request, reservation)
    return _execute_public_intake_reservation(request, reservation)


def register_comprehensive_api_routes(
    app: FastAPI,
    *,
    controller: ComprehensiveApiController | None = None,
) -> FastAPI:
    if controller is not None:
        app.state.comprehensive_api_controller = controller
        service = _service(controller)
        binder = getattr(service, "bind_browser_projection_builder", None)
        if callable(binder):
            binder(
                lambda record: _durable_browser_projection_builder(
                    controller,
                    record,
                )
            )

    existing = {
        (method.upper(), str(getattr(route, "path", "")))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    present = existing & COMPREHENSIVE_API_ROUTES
    if present:
        if present != COMPREHENSIVE_API_ROUTES:
            raise RuntimeError(
                "Partial Comprehensive route registration detected; "
                f"missing={sorted(COMPREHENSIVE_API_ROUTES - present)}"
            )
        return app

    @app.post("/assessment/comprehensive-intake")
    async def start_comprehensive_intake(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            return await run_in_threadpool(_intake, request, payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/assessment/comprehensive-run")
    async def start_comprehensive(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            return _with_runtime_truth(
                request,
                _controller(request).start(payload),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}")
    async def get_comprehensive(
        run_id: str,
        request: Request,
    ) -> dict[str, Any]:
        try:
            controller_value = _controller(request)
            browser_projection = _browser_projection_requested(request)
            response = None
            if browser_projection:
                response = await run_in_threadpool(
                    _load_durable_browser_projection,
                    controller_value,
                    run_id,
                )
            if response is None:
                try:
                    response = await run_in_threadpool(
                        _status_projection,
                        controller_value,
                        run_id,
                        browser_projection,
                    )
                except ComprehensiveRunNotFound:
                    response = await run_in_threadpool(
                        _reserved_public_intake_status,
                        request,
                        run_id,
                    )
            if response.get("intake_reserved") is not True:
                await run_in_threadpool(
                    _reconcile_public_intake_after_run_recovery,
                    request,
                    run_id=run_id,
                    response=response,
                )
            return _with_runtime_truth(request, response)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/assessment/comprehensive-run/{run_id}/continue")
    async def continue_comprehensive(
        run_id: str,
        request: Request,
    ) -> dict[str, Any]:
        try:
            raw = await request.body()
            payload = await request.json() if raw else {}
            controller_value = _controller(request)
            browser_projection = _browser_projection_requested(request)
            if (
                browser_projection
                and _detached_browser_continuation_enabled(request)
                and _browser_continuation_has_work(payload)
            ):
                current = await run_in_threadpool(
                    _load_durable_browser_projection,
                    controller_value,
                    run_id,
                )
                if current is not None and current.get("terminal") is not True:
                    dispatch = dispatch_browser_continuation(
                        controller_value,
                        run_id=run_id,
                        payload=payload,
                    )
                    response = dict(current)
                    response["operation"] = "continuation_dispatched"
                    response["continuation_dispatch"] = dispatch
                    return _with_runtime_truth(request, response)
            continued = await run_in_threadpool(
                _continue_projection,
                controller_value,
                run_id,
                payload,
                browser_projection,
            )
            if (
                browser_projection
                and _continued_browser_projection_is_authoritative(continued)
            ):
                projected_record = (
                    continued.get("record")
                    if isinstance(continued.get("record"), dict)
                    else {}
                )
                response = _review_projection(
                    continued,
                    projected_record,
                    include_review_artifact_identity=False,
                )
            else:
                response = await run_in_threadpool(
                    _status_projection,
                    controller_value,
                    run_id,
                    browser_projection,
                    "continued",
                )
            return _with_runtime_truth(request, response)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}/review-queue")
    async def get_comprehensive_review_queue(
        run_id: str,
        request: Request,
        x_nico_admin_token: str = Header(default=""),
    ) -> dict[str, Any]:
        try:
            _authorize_review(x_nico_admin_token)
            controller_value = _controller(request)
            record = _service(controller_value).load(run_id)
            return _with_runtime_truth(
                request,
                _review_queue_projection(record),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/assessment/comprehensive-run/{run_id}/review")
    async def review_comprehensive(
        run_id: str,
        request: Request,
        x_nico_admin_token: str = Header(default=""),
    ) -> dict[str, Any]:
        try:
            _authorize_review(x_nico_admin_token)
            payload = await request.json()
            if not isinstance(payload, dict):
                raise TypeError("request_body_must_be_object")
            if (
                payload.get("review_authorized") is not True
                or payload.get("authorization_confirmed") is not True
            ):
                raise ValueError("explicit_review_authorization_required")
            controller_value = _controller(request)
            record = _service(controller_value).review(
                run_id,
                reviewer=_required(payload.get("reviewer"), "reviewer"),
                reviewer_role=_required(
                    payload.get("reviewer_role"),
                    "reviewer_role",
                ),
                decision=_required(payload.get("decision"), "decision"),
                decision_reason=_required(
                    payload.get("decision_reason"),
                    "decision_reason",
                ),
                decided_at=(
                    str(payload.get("decided_at")).strip()
                    if payload.get("decided_at")
                    else None
                ),
                expected_artifact_identity=payload.get(
                    "expected_artifact_identity"
                ),
            )
            response = controller_value._response(
                record,
                operation="reviewed",
                browser_projection=_browser_projection_requested(request),
            )
            return _with_runtime_truth(
                request,
                _review_projection(response, record),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/assessment/comprehensive-run/{run_id}/authorize-delivery")
    async def authorize_comprehensive_delivery(
        run_id: str,
        request: Request,
        x_nico_admin_token: str = Header(default=""),
    ) -> dict[str, Any]:
        try:
            _authorize_review(x_nico_admin_token)
            payload = await request.json()
            if not isinstance(payload, dict):
                raise TypeError("request_body_must_be_object")
            if (
                payload.get("delivery_authorized") is not True
                or payload.get("authorization_confirmed") is not True
            ):
                raise ValueError("explicit_delivery_authorization_required")
            controller_value = _controller(request)
            record = _service(controller_value).authorize_delivery(
                run_id,
                authorizer=_required(payload.get("authorizer"), "authorizer"),
                authorizer_role=_required(
                    payload.get("authorizer_role"),
                    "authorizer_role",
                ),
                authorization_reason=_required(
                    payload.get("authorization_reason"),
                    "authorization_reason",
                ),
                authorized_at=(
                    str(payload.get("authorized_at")).strip()
                    if payload.get("authorized_at")
                    else None
                ),
                expected_artifact_identity=payload.get(
                    "expected_artifact_identity"
                ),
            )
            response = controller_value._response(
                record,
                operation="delivery_authorized",
                browser_projection=_browser_projection_requested(request),
            )
            return _with_runtime_truth(
                request,
                _review_projection(response, record),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}/approved-delivery-package")
    async def approved_delivery_package(
        run_id: str,
        request: Request,
        x_nico_admin_token: str = Header(default=""),
    ) -> Response:
        try:
            _authorize_review(x_nico_admin_token)
            controller_value = _controller(request)
            record = _service(controller_value).load(run_id)
            return _approved_delivery_response(record)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    app.openapi_schema = None
    return app


__all__ = ["COMPREHENSIVE_API_ROUTES", "VERSION", "register_comprehensive_api_routes"]
