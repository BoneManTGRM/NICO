from __future__ import annotations

import base64
from collections.abc import Mapping
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
from nico.comprehensive_approved_delivery_v1 import validate_approved_delivery_package
from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunNotFound
from nico.comprehensive_review_decision_v1 import review_artifact_identity
from nico.exact_commit_binding import expected_commit_sha
from nico.hosted_assessment import normalize_repository
from nico.repository_snapshot import capture_repository_snapshot

VERSION = "nico.comprehensive_api_routes.v16"
_BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"

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
    if isinstance(exc, ComprehensiveRunConflict):
        return HTTPException(status_code=409, detail=str(exc))
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
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="comprehensive_service_error")


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


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
    projected = {
        **response,
        "delivery_status": delivery_status,
        "review_artifact_identity": review_artifact_identity(record),
    }
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


def _intake(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("request_body_must_be_object")
    if (
        payload.get("authorized") is not True
        or payload.get("authorization_confirmed") is not True
    ):
        raise ValueError("explicit_authorization_required")

    repository = normalize_repository(
        _required(payload.get("repository"), "repository")
    )
    customer_id = _required(
        payload.get("customer_id") or "default_customer",
        "customer_id",
    )
    project_id = _required(
        payload.get("project_id") or "default_project",
        "project_id",
    )
    assessment_depth = _required(
        payload.get("assessment_depth") or "strategic",
        "assessment_depth",
    )
    report_language = _required(
        payload.get("report_language") or "en",
        "report_language",
    )

    # This is the canonical intake boundary, not a runtime monkey patch. Preserve the
    # optional display names here so every production call path retains them before the
    # controller/service canonicalizes the run. The detached report worker already reads
    # the retained stakeholder evidence as its durable display-metadata fallback.
    from nico.comprehensive_engagement_metadata_v1 import _literal

    client_name = _literal(payload.get("client_name"), 180)
    project_name = _literal(payload.get("project_name"), 180)
    from nico.comprehensive_intake_display_metadata_v2 import (
        _human_evidence_with_display_metadata,
    )

    human_evidence = _human_evidence_with_display_metadata(
        payload.get("human_evidence"),
        client_name=client_name,
        project_name=project_name,
    )

    requested_sha = expected_commit_sha(payload)
    run_id = f"comprun_{uuid4().hex}"
    evidence_ledger_id = f"ledger_comprehensive_{uuid4().hex}"
    snapshot = capture_repository_snapshot(
        {
            "run_id": run_id,
            "repository": repository,
            "customer_id": customer_id,
            "project_id": project_id,
            "authorized": True,
            "authorized_by": _required(
                payload.get("authorized_by") or "public_assessment_requester",
                "authorized_by",
            ),
            "authorization_scope": _required(
                payload.get("authorization_scope")
                or "authorized defensive repository assessment",
                "authorization_scope",
            ),
            "expected_commit_sha": requested_sha,
        }
    )
    if snapshot.get("status") != "attached" or not str(
        snapshot.get("commit_sha") or ""
    ).strip():
        notes = [
            str(item)
            for item in snapshot.get("unavailable_data_notes") or []
            if str(item).strip()
        ]
        reason = notes[0] if notes else "repository_snapshot_unavailable"
        raise ValueError(f"repository_snapshot_unavailable:{reason}")
    if (
        requested_sha
        and str(snapshot.get("commit_sha") or "").strip().lower()
        != requested_sha
    ):
        raise ValueError("repository_snapshot_commit_mismatch")

    response = _controller(request).start(
        {
            "repository": repository,
            "commit_sha": snapshot["commit_sha"],
            "run_id": run_id,
            "evidence_ledger_id": evidence_ledger_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "client_name": client_name,
            "project_name": project_name,
            "assessment_depth": assessment_depth,
            "report_language": report_language,
            "human_evidence": human_evidence,
            "authorized": True,
            "authorization_confirmed": True,
        }
    )
    return _with_runtime_truth(
        request,
        {
            **response,
            "operation": "intake_started",
            "repository_snapshot": snapshot,
            "client_name": client_name,
            "project_name": project_name,
        },
    )


def register_comprehensive_api_routes(
    app: FastAPI,
    *,
    controller: ComprehensiveApiController | None = None,
) -> FastAPI:
    if controller is not None:
        app.state.comprehensive_api_controller = controller

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
            record = _service(controller_value).load(run_id)
            response = controller_value._response(
                record,
                operation="status",
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

    @app.post("/assessment/comprehensive-run/{run_id}/continue")
    async def continue_comprehensive(
        run_id: str,
        request: Request,
    ) -> dict[str, Any]:
        try:
            raw = await request.body()
            payload = await request.json() if raw else {}
            controller_value = _controller(request)
            await run_in_threadpool(controller_value.continue_run, run_id, payload)
            record = _service(controller_value).load(run_id)
            response = controller_value._response(
                record,
                operation="continued",
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
