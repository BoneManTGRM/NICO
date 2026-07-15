from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hmac import compare_digest
from importlib import import_module
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import nico.hosted_assessment as hosted
from nico.storage import STORE, utc_now

EXPRESS_ASYNC_VERSION = "nico.express_async_api.v2"
EXPRESS_ASYNC_ROUTES = {
    ("POST", "/assessment/express-run"),
    ("POST", "/assessment/express-run/{run_id}/status"),
}
MAX_ACTIVE_EXPRESS_RUNS = 2
_TERMINAL_FAILURES = {"blocked", "failed", "error", "interrupted", "rejected"}
_TERMINAL_SUCCESS = {"complete", "completed"}
_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_ACTIVE_EXPRESS_RUNS, thread_name_prefix="nico-express")
_ACTIVE_RUNS: set[str] = set()
_ACTIVE_SCOPE_RUNS: dict[tuple[str, str, str], str] = {}
_ACTIVE_LOCK = Lock()

_EXPRESS_STAGE_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("request_accepted", "Request accepted and exact run identity recorded."),
    ("repository_evidence", "Collecting repository, activity, workflow, dependency, and source evidence."),
    ("scanner_reconciliation", "Reconciling current-run dependency, secret, and static-analysis evidence."),
    ("accuracy_review", "Applying evidence classification, false-positive controls, and report accuracy rules."),
    ("score_reconciliation", "Reconciling section scores and maturity against final evidence."),
    ("report_generation", "Generating Markdown, HTML, professional PDF, and repair intelligence."),
    ("truth_and_review_gates", "Applying final consistency, evidence-ledger, and human-review gates."),
    ("complete", "Assessment completed and draft report artifacts are ready for human review."),
)
_STAGE_PERCENT = {
    "request_accepted": 4,
    "repository_evidence": 14,
    "scanner_reconciliation": 48,
    "accuracy_review": 62,
    "score_reconciliation": 72,
    "report_generation": 82,
    "truth_and_review_gates": 94,
    "complete": 100,
    "failed": 100,
    "blocked": 100,
    "interrupted": 100,
}


class ExpressAssessmentRunRequest(BaseModel):
    repository: str
    authorized: bool = False
    authorization_confirmed: bool = False
    client_name: str = ""
    project_name: str = ""
    assessment_mode: str = "express"
    timeframe_days: int = 180
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    authorized_by: str = "requester_confirmation"
    authorization_scope: str = "repository assessment only"
    refresh_full_evidence: bool = True
    scanner_worker_artifact: dict[str, Any] = Field(default_factory=dict)
    scanner_artifact: dict[str, Any] = Field(default_factory=dict)
    worker_artifact: dict[str, Any] = Field(default_factory=dict)
    scanner_worker: dict[str, Any] = Field(default_factory=dict)


class ExpressAssessmentStatusRequest(BaseModel):
    customer_id: str = "default_customer"
    project_id: str = "default_project"


def _model_payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


def _persistence() -> dict[str, Any]:
    try:
        status = STORE.status()
    except Exception:
        return {
            "recorded": False,
            "durable": False,
            "adapter": "unknown",
            "note": "Express lifecycle persistence status is unavailable.",
        }
    return {
        "recorded": True,
        "durable": bool(status.get("persistence_available")),
        "adapter": str(status.get("adapter") or status.get("mode") or "unknown"),
        "note": str(status.get("persistence_note") or "Express lifecycle state is recorded through the configured storage adapter."),
    }


def _safe_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": str(payload.get("repository") or ""),
        "customer_id": str(payload.get("customer_id") or "default_customer"),
        "project_id": str(payload.get("project_id") or "default_project"),
        "client_name": str(payload.get("client_name") or "")[:160],
        "project_name": str(payload.get("project_name") or "")[:160],
        "assessment_mode": "express",
        "timeframe_days": max(30, min(int(payload.get("timeframe_days") or 180), 365)),
        "authorized_by": str(payload.get("authorized_by") or "requester_confirmation")[:120],
        "authorization_scope": str(payload.get("authorization_scope") or "repository assessment only")[:240],
        "authorization_confirmed": bool(payload.get("authorization_confirmed")),
        "authorized": bool(payload.get("authorized")),
    }


def _scope_key(payload: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(payload.get("repository") or ""),
        str(payload.get("customer_id") or "default_customer"),
        str(payload.get("project_id") or "default_project"),
    )


def _stage_progress(
    active_step: str,
    active_status: str,
    message: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    active_index = next((index for index, (step, _label) in enumerate(_EXPRESS_STAGE_DEFINITIONS) if step == active_step), 0)
    progress: list[dict[str, Any]] = []
    for index, (step, label) in enumerate(_EXPRESS_STAGE_DEFINITIONS):
        if step == active_step:
            status = active_status
            step_message = message
        elif index < active_index:
            status = "complete"
            step_message = label
        else:
            status = "pending"
            step_message = label
        item: dict[str, Any] = {
            "step": step,
            "status": status,
            "message": step_message,
            "evidence": {"same_run_continuation": True},
        }
        if step == active_step and evidence:
            item["evidence"].update(deepcopy(evidence))
        progress.append(item)
    return progress


def _response(
    run_id: str,
    payload: dict[str, Any],
    status: str,
    message: str,
    *,
    code: str = "",
    stage: str = "request_accepted",
    progress_percent: int | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage_status = status if status in _TERMINAL_FAILURES | _TERMINAL_SUCCESS else "running" if status == "running" else "queued"
    bounded_percent = max(0, min(100, int(progress_percent if progress_percent is not None else _STAGE_PERCENT.get(stage, 0))))
    response = {
        "status": status,
        "run_id": run_id,
        "assessment_type": "express",
        "service_tier": "express",
        "repository": str(payload.get("repository") or ""),
        "customer_id": str(payload.get("customer_id") or "default_customer"),
        "project_id": str(payload.get("project_id") or "default_project"),
        "current_stage": stage,
        "progress_percent": bounded_percent,
        "progress": _stage_progress(stage, stage_status, message, evidence=evidence),
        "human_review_required": True,
        "client_ready": False,
        "persistence": _persistence(),
        "updated_at": utc_now(),
    }
    if code:
        response["code"] = code
    return response


def _record(run_id: str, request_payload: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    existing = STORE.get("assessment_runs", run_id) or {}
    record = deepcopy(existing)
    record.update(
        {
            "workflow": "express",
            "run_id": run_id,
            "customer_id": str(request_payload.get("customer_id") or "default_customer"),
            "project_id": str(request_payload.get("project_id") or "default_project"),
            "repository": str(request_payload.get("repository") or ""),
            "status": str(response.get("status") or "unknown"),
            "request": _safe_request(request_payload),
            "response": deepcopy(response),
            "payload": deepcopy(response),
            "updated_at": utc_now(),
        }
    )
    record.setdefault("created_at", utc_now())
    return STORE.put("assessment_runs", run_id, record)


def _record_stage(
    run_id: str,
    request_payload: dict[str, Any],
    stage: str,
    message: str,
    *,
    progress_percent: int | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = _response(
        run_id,
        request_payload,
        "running",
        message,
        stage=stage,
        progress_percent=progress_percent,
        evidence=evidence,
    )
    _record(run_id, request_payload, response)
    return response


def _record_response(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("response") if isinstance(record.get("response"), dict) else record.get("payload")
    return deepcopy(value) if isinstance(value, dict) else {}


def _blocked_detail(result: dict[str, Any], run_id: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    api_main = import_module("nico.api.main")
    exc = api_main.safe_blocked_exception(result)
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    message = str(detail.get("message") or "Express assessment was blocked.")[:320]
    return _response(
        run_id,
        request_payload,
        "blocked",
        message,
        code=str(detail.get("code") or "blocked")[:80],
        stage="blocked",
        progress_percent=100,
    )


def _release_active(run_id: str, request_payload: dict[str, Any]) -> None:
    key = _scope_key(request_payload)
    with _ACTIVE_LOCK:
        _ACTIVE_RUNS.discard(run_id)
        if _ACTIVE_SCOPE_RUNS.get(key) == run_id:
            _ACTIVE_SCOPE_RUNS.pop(key, None)


def _execute(run_id: str, request_payload: dict[str, Any]) -> None:
    _record_stage(
        run_id,
        request_payload,
        "repository_evidence",
        "Collecting authorized repository structure, activity, workflows, manifests, source signals, and baseline evidence.",
    )
    try:
        api_main = import_module("nico.api.main")
        req = api_main.GithubAssessmentRequest(**request_payload)
        payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        if api_main.extract_scanner_worker_artifact(payload):
            result = api_main.run_github_assessment_with_scanner_artifacts(payload)
        else:
            result = api_main.run_github_assessment(payload)
        if result.get("status") == "blocked":
            blocked = _blocked_detail(result, run_id, request_payload)
            _record(run_id, request_payload, blocked)
            return

        result["run_id"] = run_id
        _record_stage(
            run_id,
            request_payload,
            "scanner_reconciliation",
            "Repository evidence is attached. Reconciling dependency, secret, static-analysis, CI, and complexity evidence for this exact run.",
            evidence={"repository_evidence_attached": True},
        )
        result = api_main.attach_existing_worker_evidence(result, payload)
        result = api_main.enrich_payload_with_scanner_evidence(result)

        _record_stage(
            run_id,
            request_payload,
            "accuracy_review",
            "Scanner evidence is attached. Applying source classification, contradiction removal, and false-positive controls.",
        )
        result = api_main.apply_report_accuracy(result)
        result = api_main.attach_express_review_target(result, payload)

        _record_stage(
            run_id,
            request_payload,
            "score_reconciliation",
            "Evidence classification is complete. Reconciling section scores and the maturity signal without score inflation.",
        )
        result = api_main.polish_express_result(result)

        _record_stage(
            run_id,
            request_payload,
            "report_generation",
            "Final scores are available. Generating the professional report, decision summary, repair intelligence, and downloadable formats.",
        )
        result = api_main.finalize_express_result_consistency(result)
        result = api_main.attach_express_review_target(result, payload)

        _record_stage(
            run_id,
            request_payload,
            "truth_and_review_gates",
            "Report formats are generated. Applying evidence-ledger, consistency, acceptance, and human-review gates.",
        )
        result = api_main.attach_evidence_artifact_bundle(result)
        result = api_main.attach_client_acceptance_gate(result)
        response_payload = api_main.safe_assessment_response_payload(result)
        response_payload["run_id"] = run_id
        response_payload["assessment_type"] = "express"
        response_payload["service_tier"] = "express"
        response_payload["human_review_required"] = True
        response_payload["client_ready"] = False
        response_payload["persistence"] = _persistence()
        response_payload["current_stage"] = "complete"
        response_payload["progress_percent"] = 100
        response_payload["progress"] = _stage_progress(
            "complete",
            "complete",
            "Express assessment completed. Draft report artifacts are ready for required human review.",
            evidence={
                "report_formats_ready": bool((response_payload.get("reports") or {}).get("pdf_base64")),
                "score_reconciled": True,
            },
        )
        response_payload["updated_at"] = utc_now()
        api_main._LAST_HOSTED_ASSESSMENT = response_payload

        record_id, storage_record = api_main.hosted_assessment_storage_record(req)
        if record_id != run_id:
            storage_record = deepcopy(storage_record)
            storage_record["run_id"] = run_id
            storage_record["status"] = response_payload.get("status") or "complete"
            storage_record["payload"] = deepcopy(response_payload)
        STORE.put("assessment_runs", run_id, storage_record)
        _record(run_id, request_payload, response_payload)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        terminal_status = "blocked" if exc.status_code < 500 else "failed"
        failure = _response(
            run_id,
            request_payload,
            terminal_status,
            str(detail.get("message") or "Express assessment execution was blocked.")[:320],
            code=str(detail.get("code") or f"http_{exc.status_code}")[:80],
            stage=terminal_status,
            progress_percent=100,
        )
        _record(run_id, request_payload, failure)
    except Exception:
        failure = _response(
            run_id,
            request_payload,
            "failed",
            "Express assessment execution failed on the backend. Internal exception details remain redacted; review authorized backend diagnostics before retrying.",
            code="express_backend_execution_failed",
            stage="failed",
            progress_percent=100,
        )
        _record(run_id, request_payload, failure)
    finally:
        _release_active(run_id, request_payload)


def express_assessment_start(req: ExpressAssessmentRunRequest) -> dict[str, Any]:
    payload = _model_payload(req)
    if not bool(payload.get("authorized")) or not bool(payload.get("authorization_confirmed")):
        api_main = import_module("nico.api.main")
        raise api_main.safe_blocked_exception(
            {
                "status": "blocked",
                "error": "Explicit authorization is required before NICO assesses a repository.",
            }
        )
    try:
        payload["repository"] = hosted.normalize_repository(str(payload.get("repository") or ""))
    except ValueError as exc:
        api_main = import_module("nico.api.main")
        raise api_main.safe_blocked_exception({"status": "blocked", "error": str(exc)})

    key = _scope_key(payload)
    with _ACTIVE_LOCK:
        existing_run_id = _ACTIVE_SCOPE_RUNS.get(key, "")
        if existing_run_id:
            existing = STORE.get("assessment_runs", existing_run_id)
            if isinstance(existing, dict):
                response = _record_response(existing)
                if str(response.get("status") or "").lower() in {"queued", "running"}:
                    response["duplicate_start_prevented"] = True
                    return response
            _ACTIVE_SCOPE_RUNS.pop(key, None)
            _ACTIVE_RUNS.discard(existing_run_id)
        if len(_ACTIVE_RUNS) >= MAX_ACTIVE_EXPRESS_RUNS:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "blocked",
                    "code": "express_capacity_reached",
                    "message": "Express capacity is currently occupied by authorized active runs. Wait for an existing run to finish before starting another.",
                    "assessment_type": "express",
                    "human_review_required": True,
                    "client_ready": False,
                },
            )
        run_id = f"express_run_{uuid4().hex}"
        _ACTIVE_RUNS.add(run_id)
        _ACTIVE_SCOPE_RUNS[key] = run_id

    queued = _response(
        run_id,
        payload,
        "queued",
        "Express run accepted. The exact run is recorded and will publish truthful stage updates while the browser polls short status requests.",
        stage="request_accepted",
        progress_percent=4,
    )
    try:
        _record(run_id, payload, queued)
        _EXECUTOR.submit(_execute, run_id, deepcopy(payload))
    except Exception:
        _release_active(run_id, payload)
        failed = _response(
            run_id,
            payload,
            "failed",
            "Express run could not be scheduled on the backend.",
            code="express_run_schedule_failed",
            stage="failed",
            progress_percent=100,
        )
        _record(run_id, payload, failed)
        raise HTTPException(status_code=503, detail=failed)
    return queued


def express_assessment_status(run_id: str, req: ExpressAssessmentStatusRequest) -> dict[str, Any]:
    if not str(run_id or "").startswith("express_run_"):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Express assessment run not found."})
    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Express assessment run not found."})

    request_record = record.get("request") if isinstance(record.get("request"), dict) else record
    stored_customer = str(record.get("customer_id") or request_record.get("customer_id") or "default_customer")
    stored_project = str(record.get("project_id") or request_record.get("project_id") or "default_project")
    if not compare_digest(str(req.customer_id or "default_customer"), stored_customer) or not compare_digest(
        str(req.project_id or "default_project"), stored_project
    ):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Express assessment run not found."})

    response = _record_response(record)
    response["run_id"] = run_id
    response["customer_id"] = stored_customer
    response["project_id"] = stored_project
    response.setdefault("assessment_type", "express")
    response.setdefault("human_review_required", True)
    response["client_ready"] = False

    status = str(response.get("status") or record.get("status") or "unknown").lower()
    if status in {"queued", "running"}:
        with _ACTIVE_LOCK:
            active = run_id in _ACTIVE_RUNS
        if not active:
            interrupted = _response(
                run_id,
                request_record,
                "interrupted",
                "The backend process restarted or stopped before this Express run reached a terminal result. The exact run ID is preserved; review Recovery before starting another run.",
                code="express_worker_interrupted",
                stage="interrupted",
                progress_percent=100,
            )
            _record(run_id, request_record, interrupted)
            raise HTTPException(status_code=503, detail=interrupted)
        return response
    if status in _TERMINAL_FAILURES:
        raise HTTPException(status_code=400 if status in {"blocked", "rejected"} else 503, detail=response)
    if status not in _TERMINAL_SUCCESS:
        unknown = _response(
            run_id,
            request_record,
            "failed",
            "Express run state was not recognized. NICO stopped rather than infer a successful result.",
            code="express_unknown_terminal_state",
            stage="failed",
            progress_percent=100,
        )
        _record(run_id, request_record, unknown)
        raise HTTPException(status_code=503, detail=unknown)
    return response


def _route_count(app: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def register_express_async_routes(app: FastAPI) -> dict[str, Any]:
    if getattr(app.state, "nico_express_async_version", "") == EXPRESS_ASYNC_VERSION:
        return {"status": "already_installed", "version": EXPRESS_ASYNC_VERSION}
    for method, path in EXPRESS_ASYNC_ROUTES:
        if _route_count(app, method, path):
            raise RuntimeError(f"Partial or conflicting Express async route registration detected for {method} {path}")
    app.post("/assessment/express-run")(express_assessment_start)
    app.post("/assessment/express-run/{run_id}/status")(express_assessment_status)
    app.state.nico_express_async_version = EXPRESS_ASYNC_VERSION
    app.openapi_schema = None
    missing = [(method, path) for method, path in EXPRESS_ASYNC_ROUTES if _route_count(app, method, path) != 1]
    if missing:
        raise RuntimeError(f"Express async route registration incomplete: {missing}")
    return {
        "status": "installed",
        "version": EXPRESS_ASYNC_VERSION,
        "routes": sorted(f"{method} {path}" for method, path in EXPRESS_ASYNC_ROUTES),
    }


__all__ = [
    "EXPRESS_ASYNC_ROUTES",
    "EXPRESS_ASYNC_VERSION",
    "ExpressAssessmentRunRequest",
    "ExpressAssessmentStatusRequest",
    "express_assessment_start",
    "express_assessment_status",
    "register_express_async_routes",
]
