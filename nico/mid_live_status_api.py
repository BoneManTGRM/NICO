from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from nico.mid_live_progress_patch import attach_mid_live_progress
from nico.mid_status_read_path import _active_status_response, _final_mid_ready, _retained_final_response, _retained_response
from nico.scanner_recovery import (
    ACTIVE_SCANNER_STATUSES,
    RECOVERY_REQUIRED_STATUS,
    _recovery_patch,
    atomic_scanner_transition,
    scanner_age_seconds,
    scanner_is_stale,
)
from nico.storage import STORE, utc_now

MID_LIVE_STATUS_PATH = "/assessment/mid-run/{run_id}/live-status"
MID_LIVE_STATUS_ROUTE = ("GET", MID_LIVE_STATUS_PATH)
MID_LIVE_STATUS_VERSION = "nico.mid_live_status.v1"
_TERMINAL_SCANNER_STATUSES = {"complete", "failed", "error", "blocked", "cancelled", "unavailable"}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _scope_matches(record: dict[str, Any], customer_id: str, project_id: str) -> bool:
    if customer_id and str(record.get("customer_id") or "default_customer") != customer_id:
        return False
    if project_id and str(record.get("project_id") or "default_project") != project_id:
        return False
    return True


def _scan_id(record: dict[str, Any], retained: dict[str, Any]) -> str:
    request = _record(record.get("request"))
    scanner = _record(retained.get("scanner"))
    scanner_evidence = _record(retained.get("scanner_evidence"))
    return str(
        record.get("scan_id")
        or request.get("scan_id")
        or scanner.get("scan_id")
        or scanner_evidence.get("scan_id")
        or ""
    )


def _scanner_record(scan_id: str) -> dict[str, Any]:
    if not scan_id:
        return {"status": "not_started", "scan_id": ""}
    durable = STORE.get("scanner_runs", scan_id)
    return deepcopy(durable) if isinstance(durable, dict) else {"status": "not_found", "scan_id": scan_id}


def _recovery_required_response(record: dict[str, Any], scan: dict[str, Any]) -> dict[str, Any]:
    result = _retained_response(record)
    run_id = str(record.get("run_id") or result.get("run_id") or "")
    scan_id = str(scan.get("scan_id") or record.get("scan_id") or "")
    age = scanner_age_seconds(scan)
    result.update(
        {
            "status": "interrupted",
            "run_id": run_id,
            "current_stage": "scanner_recovery",
            "scanner": deepcopy(scan),
            "scanner_evidence": {
                "status": RECOVERY_REQUIRED_STATUS,
                "scanner_status": RECOVERY_REQUIRED_STATUS,
                "scan_id": scan_id,
                "run_id": run_id,
                "recovery_required": True,
                "stale_age_seconds": round(age, 1) if age is not None else None,
            },
            "status_refresh": True,
            "continuation_required": False,
            "recovery_required": True,
            "recovery_path": "/operations/recovery",
            "status_read_path": {
                "version": MID_LIVE_STATUS_VERSION,
                "mode": "recovery_required",
                "orchestrator_reentered": False,
                "repository_recaptured": False,
                "assessment_run_rewritten": False,
                "read_only": True,
            },
            "human_review_required": True,
            "client_ready": False,
        }
    )
    progress = [deepcopy(item) for item in result.get("progress") or [] if isinstance(item, dict)]
    replacement = {
        "step": "scanner_recovery",
        "status": "interrupted",
        "message": "The snapshot scanner stopped updating and now requires an exact-run recovery action. NICO did not start a duplicate assessment.",
        "evidence": {
            "run_id": run_id,
            "scan_id": scan_id,
            "scanner_status": RECOVERY_REQUIRED_STATUS,
            "stale_age_seconds": round(age, 1) if age is not None else None,
            "recovery_path": "/operations/recovery",
        },
    }
    replaced = False
    for index, item in enumerate(progress):
        if item.get("step") in {"scanner_worker", "scanner_recovery"}:
            progress[index] = replacement
            replaced = True
            break
    if not replaced:
        progress.append(replacement)
    result["progress"] = progress
    return result


def _continuation_required_response(record: dict[str, Any], scan: dict[str, Any]) -> dict[str, Any]:
    result = _retained_response(record)
    run_id = str(record.get("run_id") or result.get("run_id") or "")
    scan_status = str(scan.get("status") or "unknown")
    result.update(
        {
            "status": "running",
            "run_id": run_id,
            "current_stage": "scanner_reconciliation",
            "progress_percent": max(62, int(result.get("progress_percent") or 0)),
            "scanner": deepcopy(scan),
            "scanner_evidence": {
                "status": "ready_for_attachment",
                "scanner_status": scan_status,
                "scan_id": scan.get("scan_id") or "",
                "run_id": run_id,
            },
            "status_refresh": True,
            "continuation_required": True,
            "status_read_path": {
                "version": MID_LIVE_STATUS_VERSION,
                "mode": "terminal_scanner_handoff",
                "orchestrator_reentered": False,
                "repository_recaptured": False,
                "assessment_run_rewritten": False,
                "read_only": True,
            },
            "human_review_required": True,
            "client_ready": False,
        }
    )
    progress = [deepcopy(item) for item in result.get("progress") or [] if isinstance(item, dict)]
    replacement = {
        "step": "scanner_reconciliation",
        "status": "running",
        "message": "Scanner execution reached a terminal state. NICO is continuing the exact run through evidence attachment, scoring, report generation, and human-review preparation.",
        "evidence": {
            "run_id": run_id,
            "scan_id": scan.get("scan_id") or "",
            "scanner_status": scan_status,
            "continuation_required": True,
        },
    }
    replaced = False
    for index, item in enumerate(progress):
        if item.get("step") in {"scanner_worker", "scanner_reconciliation"}:
            progress[index] = replacement
            replaced = True
            break
    if not replaced:
        progress.append(replacement)
    result["progress"] = progress
    return attach_mid_live_progress(result)


def mid_live_status_response(
    run_id: str,
    customer_id: str = Query(default=""),
    project_id: str = Query(default=""),
) -> dict[str, Any]:
    if not str(run_id or "").startswith("midrun_"):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found."})

    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict) or str(record.get("workflow") or "") != "mid_assessment":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found."})
    if not _scope_matches(record, customer_id, project_id):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found in this scope."})

    retained = _retained_response(record)
    if _final_mid_ready(retained):
        final = _retained_final_response(record)
        final["continuation_required"] = False
        final["status_read_path"]["version"] = MID_LIVE_STATUS_VERSION
        final["status_read_path"]["mode"] = "retained_final"
        return final

    scan_id = _scan_id(record, retained)
    scan = _scanner_record(scan_id)
    scan_status = str(scan.get("status") or "unknown")

    if scan_status in ACTIVE_SCANNER_STATUSES:
        if scanner_is_stale(scan):
            age = scanner_age_seconds(scan)
            transitioned = atomic_scanner_transition(
                scan_id,
                {scan_status},
                RECOVERY_REQUIRED_STATUS,
                _recovery_patch(scan, now_text=utc_now(), age_seconds=age),
                store=STORE,
            )
            scan = transitioned or _scanner_record(scan_id)
            return _recovery_required_response(record, scan)
        active = _active_status_response(record, scan)
        active["continuation_required"] = False
        active["status_read_path"]["version"] = MID_LIVE_STATUS_VERSION
        active["status_read_path"]["mode"] = "durable_live_status"
        return active

    if scan_status == RECOVERY_REQUIRED_STATUS:
        return _recovery_required_response(record, scan)

    if scan_status in _TERMINAL_SCANNER_STATUSES:
        return _continuation_required_response(record, scan)

    result = _retained_response(record)
    result.update(
        {
            "status": "running",
            "run_id": run_id,
            "current_stage": "scanner_worker",
            "progress_percent": max(18, int(result.get("progress_percent") or 0)),
            "status_refresh": True,
            "continuation_required": False,
            "scanner": deepcopy(scan),
            "status_read_path": {
                "version": MID_LIVE_STATUS_VERSION,
                "mode": "scanner_record_pending",
                "orchestrator_reentered": False,
                "repository_recaptured": False,
                "assessment_run_rewritten": False,
                "read_only": True,
            },
            "human_review_required": True,
            "client_ready": False,
        }
    )
    return attach_mid_live_progress(result)


def register_mid_live_status_routes(app: FastAPI) -> dict[str, Any]:
    existing = [
        route
        for route in app.routes
        if str(getattr(route, "path", "")) == MID_LIVE_STATUS_PATH
        and "GET" in {str(method).upper() for method in (getattr(route, "methods", set()) or set())}
    ]
    if not existing:
        app.add_api_route(
            MID_LIVE_STATUS_PATH,
            mid_live_status_response,
            methods=["GET"],
            tags=["assessment", "mid", "status"],
        )
        app.openapi_schema = None
    return {
        "status": "installed",
        "version": MID_LIVE_STATUS_VERSION,
        "route": f"GET {MID_LIVE_STATUS_PATH}",
        "route_count": 1 if not existing else len(existing),
        "read_only": True,
        "canonical_terminal_continuation_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_LIVE_STATUS_PATH",
    "MID_LIVE_STATUS_ROUTE",
    "MID_LIVE_STATUS_VERSION",
    "mid_live_status_response",
    "register_mid_live_status_routes",
]
