from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunNotFound
from nico.exact_commit_binding import expected_commit_sha
from nico.hosted_assessment import normalize_repository
from nico.repository_snapshot import capture_repository_snapshot

VERSION = "nico.comprehensive_api_routes.v5"

COMPREHENSIVE_API_ROUTES = {
    ("POST", "/assessment/comprehensive-intake"),
    ("POST", "/assessment/comprehensive-run"),
    ("GET", "/assessment/comprehensive-run/{run_id}"),
    ("POST", "/assessment/comprehensive-run/{run_id}/continue"),
}

_SAFE_RUNTIME_REASONS = {
    "comprehensive_durable_storage_required": (
        "Comprehensive is temporarily unavailable because durable assessment storage is not configured."
    ),
    "comprehensive_sqlite_storage_unavailable": (
        "Comprehensive is temporarily unavailable because its configured durable storage could not be opened."
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
                "message": message,
                "retryable": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    return controller


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ComprehensiveRunNotFound):
        return HTTPException(status_code=404, detail="comprehensive_run_not_found")
    if isinstance(exc, ComprehensiveRunConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="comprehensive_service_error")


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


def _runtime_persistence(request: Request) -> dict[str, Any]:
    runtime = dict(getattr(request.app.state, "comprehensive_runtime", {}) or {})
    adapter = str(runtime.get("persistence_adapter") or "unavailable")
    configured = runtime.get("configured") is True
    # The active durable adapter is authoritative. Older deployments may retain a
    # stale false durability flag even after Postgres or persistent SQLite opened.
    durable = configured and bool(
        runtime.get("durability_verified")
        or adapter in {"postgres", "sqlite"}
    )
    return {
        "recorded": configured,
        "durable": durable,
        "adapter": adapter,
        "storage_source": str(runtime.get("storage_source") or adapter),
    }


def _with_runtime_truth(request: Request, response: dict[str, Any]) -> dict[str, Any]:
    return {
        **response,
        "persistence": _runtime_persistence(request),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _intake(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("request_body_must_be_object")
    if payload.get("authorized") is not True or payload.get("authorization_confirmed") is not True:
        raise ValueError("explicit_authorization_required")

    repository = normalize_repository(_required(payload.get("repository"), "repository"))
    customer_id = _required(payload.get("customer_id") or "default_customer", "customer_id")
    project_id = _required(payload.get("project_id") or "default_project", "project_id")
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
            "authorized_by": _required(payload.get("authorized_by") or "public_assessment_requester", "authorized_by"),
            "authorization_scope": _required(
                payload.get("authorization_scope") or "authorized defensive repository assessment",
                "authorization_scope",
            ),
            # Preserve the explicit immutable release binding as a first-class field.
            # The authorization marker remains a compatibility fallback only.
            "expected_commit_sha": requested_sha,
        }
    )
    if snapshot.get("status") != "attached" or not str(snapshot.get("commit_sha") or "").strip():
        notes = [str(item) for item in snapshot.get("unavailable_data_notes") or [] if str(item).strip()]
        reason = notes[0] if notes else "repository_snapshot_unavailable"
        raise ValueError(f"repository_snapshot_unavailable:{reason}")
    if requested_sha and str(snapshot.get("commit_sha") or "").strip().lower() != requested_sha:
        raise ValueError("repository_snapshot_commit_mismatch")

    response = _controller(request).start(
        {
            "repository": repository,
            "commit_sha": snapshot["commit_sha"],
            "run_id": run_id,
            "evidence_ledger_id": evidence_ledger_id,
            "customer_id": customer_id,
            "project_id": project_id,
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
            "client_name": str(payload.get("client_name") or ""),
            "project_name": str(payload.get("project_name") or ""),
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
            return _intake(request, payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/assessment/comprehensive-run")
    async def start_comprehensive(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            return _with_runtime_truth(request, _controller(request).start(payload))
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}")
    async def get_comprehensive(run_id: str, request: Request) -> dict[str, Any]:
        try:
            return _with_runtime_truth(request, _controller(request).status(run_id))
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/assessment/comprehensive-run/{run_id}/continue")
    async def continue_comprehensive(run_id: str, request: Request) -> dict[str, Any]:
        try:
            raw = await request.body()
            payload = await request.json() if raw else {}
            return _with_runtime_truth(
                request,
                _controller(request).continue_run(run_id, payload),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise _translate_error(exc) from exc

    app.openapi_schema = None
    return app


__all__ = ["COMPREHENSIVE_API_ROUTES", "VERSION", "register_comprehensive_api_routes"]
