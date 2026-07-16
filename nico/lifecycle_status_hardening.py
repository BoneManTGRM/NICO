from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hmac import compare_digest
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from nico import express_async_api
from nico.mid_live_status_api import MID_LIVE_STATUS_PATH, mid_live_status_response
from nico.storage import STORE

LIFECYCLE_STATUS_HARDENING_VERSION = "nico.lifecycle_status_hardening.v2"
EXPRESS_STATUS_PATH = "/assessment/express-run/{run_id}/status"
_ACTIVE = {"queued", "running", "starting", "pending"}
_TERMINAL_FAILURE = {"blocked", "failed", "error", "interrupted", "rejected"}
_TERMINAL_SUCCESS = {"complete", "completed"}
_EXPRESS_WORKER_START_GRACE_SECONDS = 60


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bounded(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(value: Any) -> float | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _safe_scan(scan: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "scan_id",
        "run_id",
        "repository",
        "customer_id",
        "project_id",
        "status",
        "current_stage",
        "progress_percent",
        "active_tool",
        "message",
        "tools_requested",
        "tools_run",
        "unavailable_tools",
        "failed_tools",
        "timed_out_tools",
        "snapshot_id",
        "snapshot_commit_sha",
        "actual_commit_sha",
        "snapshot_match",
        "heartbeat_at",
        "heartbeat_sequence",
        "heartbeat_process_id",
        "heartbeat_thread",
        "heartbeat_persistence_status",
        "heartbeat_failure_type",
        "tool_elapsed_seconds",
        "created_at",
        "updated_at",
        "completed_at",
        "recovery",
    )
    output: dict[str, Any] = {}
    for key in allowed:
        value = scan.get(key)
        if isinstance(value, (str, int, float, bool, type(None))):
            output[key] = value
        elif isinstance(value, list):
            output[key] = [item for item in value[:100] if isinstance(item, (str, int, float, bool, type(None)))]
        elif isinstance(value, dict):
            output[key] = {
                str(item_key)[:80]: item_value
                for item_key, item_value in list(value.items())[:40]
                if isinstance(item_value, (str, int, float, bool, type(None)))
            }
    return output


def _safe_progress(progress: Any) -> list[dict[str, Any]]:
    if not isinstance(progress, list):
        return []
    output: list[dict[str, Any]] = []
    for item in progress[:20]:
        if not isinstance(item, dict):
            continue
        evidence = _record(item.get("evidence"))
        safe_evidence = {
            str(key)[:80]: value
            for key, value in list(evidence.items())[:60]
            if isinstance(value, (str, int, float, bool, type(None)))
        }
        output.append(
            {
                "step": _bounded(item.get("step"), 80),
                "status": _bounded(item.get("status"), 40),
                "message": _bounded(item.get("message"), 500),
                "evidence": safe_evidence,
            }
        )
    return output


def _safe_retained_response(record: dict[str, Any]) -> dict[str, Any]:
    """Return the exact public lifecycle payload, never the private run record.

    ``response``/``payload`` is already the sanitized client contract written by
    the lifecycle worker. Retaining it is necessary so completed Express status
    responses still contain their report artifacts, sections, scores, and review
    gates. Private request data and internal storage metadata are not copied.
    """

    source = _record(record.get("response")) or _record(record.get("payload"))
    output = deepcopy(source)
    output["progress"] = _safe_progress(source.get("progress"))
    scanner = source.get("scanner")
    if isinstance(scanner, dict):
        output["scanner"] = _safe_scan(scanner)

    scalar_fallbacks = (
        "status",
        "run_id",
        "repository",
        "customer_id",
        "project_id",
        "assessment_type",
        "service_tier",
        "mode",
        "current_stage",
        "progress_percent",
        "report_generation_status",
        "human_review_required",
        "client_ready",
        "snapshot_id",
        "snapshot_commit_sha",
        "scan_id",
        "created_at",
        "updated_at",
        "heartbeat_at",
        "heartbeat_sequence",
        "heartbeat_process_id",
        "worker_started",
        "worker_started_at",
        "worker_process_id",
        "worker_thread",
        "backend_stage",
        "status_truth",
        "code",
        "failure_stage",
        "exception_class",
        "diagnostic_id",
        "diagnostic_run_id",
        "diagnostic_recorded_at",
    )
    for key in scalar_fallbacks:
        if key not in output:
            value = record.get(key)
            if isinstance(value, (str, int, float, bool, type(None))):
                output[key] = value

    output.setdefault("run_id", record.get("run_id") or "")
    output.setdefault("repository", record.get("repository") or "")
    output.setdefault("customer_id", record.get("customer_id") or "default_customer")
    output.setdefault("project_id", record.get("project_id") or "default_project")
    output.setdefault("human_review_required", True)
    output["client_ready"] = False
    return output


def _scope_matches(record: dict[str, Any], customer_id: str, project_id: str) -> bool:
    request_record = _record(record.get("request"))
    stored_customer = str(record.get("customer_id") or request_record.get("customer_id") or "default_customer")
    stored_project = str(record.get("project_id") or request_record.get("project_id") or "default_project")
    return compare_digest(customer_id, stored_customer) and compare_digest(project_id, stored_project)


def _interrupt_express(
    run_id: str,
    request_record: dict[str, Any],
    *,
    code: str,
    message: str,
    evidence: dict[str, Any],
) -> None:
    interrupted = express_async_api._response(
        run_id,
        request_record,
        "interrupted",
        message,
        code=code,
        stage="interrupted",
        progress_percent=100,
        evidence={**evidence, "recovery_required": True},
    )
    interrupted["recovery_required"] = True
    interrupted["recovery_path"] = "/operations/recovery"
    express_async_api._record(run_id, request_record, interrupted)
    raise HTTPException(status_code=503, detail=interrupted)


def _express_status_response(run_id: str, customer_id: str, project_id: str) -> dict[str, Any]:
    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict) or str(record.get("workflow") or "") != "express":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Express assessment run not found."})
    if not _scope_matches(record, customer_id, project_id):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Express assessment run not found."})

    response = _safe_retained_response(record)
    response["run_id"] = run_id
    response["customer_id"] = customer_id
    response["project_id"] = project_id
    response.setdefault("assessment_type", "express")
    response.setdefault("service_tier", "express")
    response.setdefault("human_review_required", True)
    response["client_ready"] = False

    status = str(response.get("status") or record.get("status") or "unknown").lower()
    heartbeat_at = response.get("heartbeat_at") or record.get("heartbeat_at") or response.get("updated_at") or record.get("updated_at")
    heartbeat_age = _age_seconds(heartbeat_at)
    created_at = response.get("created_at") or record.get("created_at") or response.get("updated_at") or record.get("updated_at")
    run_age = _age_seconds(created_at)
    worker_started = bool(response.get("worker_started"))

    if status in _ACTIVE:
        response["status"] = "running" if status != "queued" else "queued"
        response["lifecycle_status"] = {
            "version": LIFECYCLE_STATUS_HARDENING_VERSION,
            "mode": "durable_exact_run_read",
            "heartbeat_at": heartbeat_at or "",
            "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age is not None else None,
            "worker_started": worker_started,
            "worker_started_at": response.get("worker_started_at") or "",
            "worker_process_id": response.get("worker_process_id"),
            "worker_thread": response.get("worker_thread") or "",
            "backend_stage": response.get("backend_stage") or "",
            "scanner_status": _record(response.get("scanner")).get("status") or "not_started",
            "process_local_active_set_required": False,
            "request_validation_422_possible": False,
        }
        request_record = _record(record.get("request")) or record
        if not worker_started and run_age is not None and run_age > _EXPRESS_WORKER_START_GRACE_SECONDS:
            _interrupt_express(
                run_id,
                request_record,
                code="express_worker_start_timeout",
                message="The Express run was accepted but the backend worker did not publish its start handshake within the bounded grace period. The exact run remains preserved for authenticated recovery.",
                evidence={
                    "worker_started": False,
                    "run_age_seconds": round(run_age, 1),
                    "worker_start_grace_seconds": _EXPRESS_WORKER_START_GRACE_SECONDS,
                },
            )
        if heartbeat_age is None or heartbeat_age <= 300:
            return response
        _interrupt_express(
            run_id,
            request_record,
            code="express_worker_heartbeat_stale",
            message="The Express lifecycle stopped updating before completion. The exact run remains preserved for authenticated recovery.",
            evidence={
                "heartbeat_at": heartbeat_at or "",
                "heartbeat_age_seconds": round(heartbeat_age, 1),
                "worker_started": worker_started,
            },
        )

    if status in _TERMINAL_FAILURE:
        raise HTTPException(status_code=400 if status in {"blocked", "rejected"} else 503, detail=response)
    if status in _TERMINAL_SUCCESS:
        return response

    unknown = deepcopy(response)
    unknown.update(
        {
            "status": "failed",
            "code": "express_unknown_terminal_state",
            "message": "Express run state was not recognized. NICO stopped rather than infer a successful result.",
            "current_stage": "failed",
            "progress_percent": 100,
            "human_review_required": True,
            "client_ready": False,
        }
    )
    express_async_api._record(run_id, _record(record.get("request")) or record, unknown)
    raise HTTPException(status_code=503, detail=unknown)


async def express_status_endpoint(run_id: str, request: Request) -> dict[str, Any]:
    """Accept bounded JSON, an empty body, or query scope without FastAPI 422."""

    payload: dict[str, Any] = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}
    customer_id = _bounded(payload.get("customer_id") or request.query_params.get("customer_id") or "default_customer", 120)
    project_id = _bounded(payload.get("project_id") or request.query_params.get("project_id") or "default_project", 120)
    try:
        return _express_status_response(run_id, customer_id or "default_customer", project_id or "default_project")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "temporarily_unavailable",
                "code": "express_status_read_failed",
                "message": "NICO could not read the exact Express lifecycle state. The run remains preserved; inspect Recovery before starting another run.",
                "run_id": run_id,
                "assessment_type": "express",
                "failure_type": type(exc).__name__[:80],
                "duplicate_start_allowed": False,
                "human_review_required": True,
                "client_ready": False,
            },
        ) from exc


def _mid_projection(run_id: str, customer_id: str, project_id: str, failure_type: str) -> dict[str, Any]:
    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict) or str(record.get("workflow") or "") != "mid_assessment":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found."})
    if not _scope_matches(record, customer_id or "default_customer", project_id or "default_project"):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found in this scope."})

    result = _safe_retained_response(record)
    scan_id = str(record.get("scan_id") or _record(record.get("request")).get("scan_id") or result.get("scan_id") or "")
    scan = _safe_scan(STORE.get("scanner_runs", scan_id) or {}) if scan_id else {"status": "not_started", "scan_id": ""}
    scan_status = str(scan.get("status") or "unknown").lower()
    scanner_percent = max(0, min(100, int(scan.get("progress_percent") or 0)))
    heartbeat_at = scan.get("heartbeat_at") or scan.get("updated_at") or ""
    heartbeat_age = _age_seconds(heartbeat_at)

    result.update(
        {
            "run_id": run_id,
            "assessment_type": "mid",
            "service_tier": "mid",
            "scanner": scan,
            "scan_id": scan_id,
            "status_refresh": True,
            "live_status_degraded": True,
            "code": "mid_live_status_projection_degraded",
            "projection_failure_type": failure_type[:80],
            "human_review_required": True,
            "client_ready": False,
            "status_read_path": {
                "version": LIFECYCLE_STATUS_HARDENING_VERSION,
                "mode": "bounded_degraded_projection",
                "read_only": True,
                "repository_recaptured": False,
                "orchestrator_reentered": False,
                "assessment_run_rewritten": False,
            },
        }
    )
    if scan_status in {"queued", "running"}:
        result["status"] = "running"
        result["current_stage"] = "scanner_worker"
        result["scanner_progress_percent"] = scanner_percent
        result["progress_percent"] = max(18, min(61, round(18 + scanner_percent * 0.43)))
        result["continuation_required"] = False
        result["recovery_required"] = False
        if heartbeat_age is not None and heartbeat_age > 600:
            result["status"] = "interrupted"
            result["current_stage"] = "scanner_recovery"
            result["recovery_required"] = True
            result["recovery_path"] = "/operations/recovery"
    elif scan_status == "recovery_required":
        result["status"] = "interrupted"
        result["current_stage"] = "scanner_recovery"
        result["recovery_required"] = True
        result["recovery_path"] = "/operations/recovery"
        result["continuation_required"] = False
    elif scan_status in {"complete", "failed", "error", "blocked", "cancelled", "unavailable"}:
        result["status"] = "running"
        result["current_stage"] = "scanner_reconciliation"
        result["progress_percent"] = max(62, int(result.get("progress_percent") or 0))
        result["continuation_required"] = True
        result["recovery_required"] = False
    else:
        result.setdefault("status", "running")
        result.setdefault("current_stage", "scanner_worker")
        result.setdefault("progress_percent", 18)
        result["continuation_required"] = False
        result["recovery_required"] = False
    result["heartbeat_at"] = heartbeat_at
    result["heartbeat_age_seconds"] = round(heartbeat_age, 1) if heartbeat_age is not None else None
    return result


async def mid_live_status_endpoint(
    run_id: str,
    customer_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    try:
        return mid_live_status_response(run_id, customer_id=customer_id, project_id=project_id)
    except HTTPException:
        raise
    except Exception as exc:
        try:
            return _mid_projection(run_id, customer_id, project_id, type(exc).__name__)
        except HTTPException:
            raise
        except Exception as projection_exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "temporarily_unavailable",
                    "code": "mid_live_status_read_failed",
                    "message": "NICO could not read the exact Mid lifecycle state. The run remains preserved; inspect Recovery before starting another run.",
                    "run_id": run_id,
                    "assessment_type": "mid",
                    "failure_type": type(projection_exc).__name__[:80],
                    "duplicate_start_allowed": False,
                    "human_review_required": True,
                    "client_ready": False,
                },
            ) from projection_exc


def _replace_route(app: FastAPI, method: str, path: str, endpoint: Any, tags: list[str]) -> None:
    expected = method.upper()
    retained = []
    removed = 0
    for route in app.router.routes:
        methods = {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
        if str(getattr(route, "path", "")) == path and expected in methods:
            removed += 1
            continue
        retained.append(route)
    if removed != 1:
        raise RuntimeError(f"Expected exactly one {method} {path} route before lifecycle hardening; found={removed}")
    app.router.routes = retained
    app.add_api_route(path, endpoint, methods=[method], tags=tags)
    app.openapi_schema = None


def install_lifecycle_status_hardening(app: FastAPI) -> dict[str, Any]:
    _replace_route(app, "POST", EXPRESS_STATUS_PATH, express_status_endpoint, ["assessment", "express", "status"])
    _replace_route(app, "GET", MID_LIVE_STATUS_PATH, mid_live_status_endpoint, ["assessment", "mid", "status"])
    return {
        "status": "installed",
        "version": LIFECYCLE_STATUS_HARDENING_VERSION,
        "express_request_validation_422_possible": False,
        "express_cross_worker_durable_read": True,
        "express_worker_start_handshake": True,
        "express_scanner_projection_preserved": True,
        "express_final_report_payload_preserved": True,
        "mid_generic_http_500_possible": False,
        "mid_bounded_degraded_projection": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "EXPRESS_STATUS_PATH",
    "LIFECYCLE_STATUS_HARDENING_VERSION",
    "express_status_endpoint",
    "install_lifecycle_status_hardening",
    "mid_live_status_endpoint",
]
