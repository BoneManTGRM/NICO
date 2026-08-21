from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from nico import comprehensive_api_routes as api_routes
from nico import comprehensive_final_report_background_v1 as background
from nico import comprehensive_final_report_process_isolation_v1 as isolation
from nico.comprehensive_final_report_process_isolation_v1 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import apply_comprehensive_stage_result
from nico.comprehensive_run_store import ComprehensiveRunConflict

VERSION = "nico.comprehensive_production_proof_lifecycle.v1"
PROOF_CUSTOMER_ID = "nico_production_proof"
PROOF_PROJECT_ID = "spanish_comprehensive_production"
PROOF_CANCEL_ROUTE = "/assessment/comprehensive-run/{run_id}/production-proof-cancel"
_INSTALL_STATE = "nico_comprehensive_production_proof_lifecycle_v1"
_INTAKE_MARKER = "__nico_comprehensive_production_proof_reaper_v1__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _is_reserved_proof_scope(record_or_payload: Mapping[str, Any]) -> bool:
    identity = record_or_payload.get("identity")
    source = identity if isinstance(identity, Mapping) else record_or_payload
    return (
        _text(source.get("customer_id")) == PROOF_CUSTOMER_ID
        and _text(source.get("project_id")) == PROOF_PROJECT_ID
    )


def _controller_parts(request: Request) -> tuple[Any, Any, Any]:
    controller = getattr(request.app.state, "comprehensive_api_controller", None)
    service = getattr(controller, "_service", None)
    store = getattr(service, "_store", None)
    return controller, service, store


def _active_final_report_lease(record: Mapping[str, Any]) -> str:
    if _text(record.get("current_stage")) != FINAL_REPORT_STAGE_ID:
        return ""
    stage_results = record.get("stage_results")
    if not isinstance(stage_results, Mapping):
        return ""
    stage = stage_results.get(FINAL_REPORT_STAGE_ID)
    if not isinstance(stage, Mapping):
        return ""
    execution = stage.get("stage_execution")
    if not isinstance(execution, Mapping):
        return ""
    return _text(execution.get("lease_id") or execution.get("publication_lease_id"))


def _cancel_isolated_final_report_worker(lease_id: str) -> bool:
    lease = _text(lease_id)
    if not lease:
        return False
    with background._LOCAL_TASKS_LOCK:
        state = background._LOCAL_TASKS.get(lease)
    if not isinstance(state, dict) or state.get("worker_model") != "isolated_subprocess":
        return False
    state_lock = state.get("state_lock")
    if state_lock is not None:
        with state_lock:
            state["phase"] = "terminating"
            state["explicitly_cancelled"] = True
    stop = state.get("stop")
    if stop is not None:
        stop.set()
    terminated = isolation._terminate_state_process(state)
    terminated = isolation._wait_for_invoke_shutdown(state) and terminated
    background._release_local_task_capacity(state)
    with background._LOCAL_TASKS_LOCK:
        if background._LOCAL_TASKS.get(lease) is state:
            background._LOCAL_TASKS.pop(lease, None)
    return terminated


def cancel_production_proof_record(
    store: Any,
    record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    """Terminalize only the reserved synthetic proof scope, retrying revision races."""

    current = record
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    run_id = _text(identity.get("run_id"))
    for _ in range(4):
        if current.get("terminal") is True:
            return current
        if not _is_reserved_proof_scope(current):
            raise ValueError("production_proof_scope_required")
        completed = list(current.get("completed_stages") or [])
        if len(completed) >= len(COMPREHENSIVE_STAGES):
            return current
        stage_id = COMPREHENSIVE_STAGES[len(completed)]
        lease_id = _active_final_report_lease(current)
        if lease_id:
            _cancel_isolated_final_report_worker(lease_id)

        result = {
            "status": "blocked",
            "reason": reason,
            "error_code": reason,
            "error_message": (
                "This synthetic production-proof run was superseded or cancelled. "
                "No client assessment or approved delivery state was changed."
            ),
            "retryable": False,
            "cancelable": False,
            "artifacts_available": False,
            "production_proof": True,
            "proof_scope": PROOF_PROJECT_ID,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        updated = apply_comprehensive_stage_result(
            current,
            stage_id=stage_id,
            result=result,
        )
        try:
            return store.save(updated, expected_revision=int(current["revision"]))
        except ComprehensiveRunConflict:
            if not run_id:
                return current
            current = store.load(run_id)
    return current


def _reap_prior_proof_runs(request: Request) -> int:
    _, _, store = _controller_parts(request)
    if store is None:
        return 0
    try:
        records = store.list_recent(
            customer_id=PROOF_CUSTOMER_ID,
            project_id=PROOF_PROJECT_ID,
            limit=25,
        )
    except Exception:
        return 0

    cancelled = 0
    for record in records:
        if not isinstance(record, dict) or record.get("terminal") is True:
            continue
        try:
            result = cancel_production_proof_record(
                store,
                record,
                reason="production_proof_superseded",
            )
            if result.get("terminal") is True:
                cancelled += 1
        except Exception:
            continue
    return cancelled


def _install_intake_reaper() -> bool:
    current = getattr(api_routes, "_intake", None)
    if not callable(current):
        return False
    if getattr(current, _INTAKE_MARKER, False):
        return True

    def wrapped(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, dict) and _is_reserved_proof_scope(payload):
            reaped = _reap_prior_proof_runs(request)
            response = current(request, payload)
            if isinstance(response, dict):
                response = dict(response)
                response["production_proof_scope"] = True
                response["superseded_proof_runs_reaped"] = reaped
            return response
        return current(request, payload)

    setattr(wrapped, _INTAKE_MARKER, True)
    api_routes._intake = wrapped
    return True


def _register_cancel_route(app: FastAPI) -> bool:
    if any(
        str(getattr(route, "path", "")) == PROOF_CANCEL_ROUTE
        and "POST"
        in {
            str(method).upper()
            for method in (getattr(route, "methods", set()) or set())
        }
        for route in app.routes
    ):
        return True

    def cancel_production_proof(run_id: str, request: Request) -> dict[str, Any]:
        _, _, store = _controller_parts(request)
        if store is None:
            raise HTTPException(
                status_code=503,
                detail="production_proof_store_unavailable",
            )
        try:
            record = store.load(run_id)
        except Exception as exc:
            raise HTTPException(
                status_code=404,
                detail="production_proof_run_not_found",
            ) from exc
        if not _is_reserved_proof_scope(record):
            # Do not reveal whether a non-proof run exists through the proof endpoint.
            raise HTTPException(
                status_code=404,
                detail="production_proof_run_not_found",
            )
        was_terminal = record.get("terminal") is True
        result = cancel_production_proof_record(
            store,
            record,
            reason="production_proof_cancelled",
        )
        terminal = bool(result.get("terminal"))
        return {
            "artifact_schema": VERSION,
            "status": (
                "already_terminal"
                if was_terminal
                else "cancelled"
                if terminal
                else "cancellation_pending"
            ),
            "run_id": run_id,
            "terminal": terminal,
            "production_proof": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    app.add_api_route(
        PROOF_CANCEL_ROUTE,
        cancel_production_proof,
        methods=["POST"],
        tags=["production-proof"],
    )
    app.openapi_schema = None
    return True


def install_comprehensive_production_proof_lifecycle_v1(app: FastAPI) -> dict[str, Any]:
    existing = getattr(app.state, _INSTALL_STATE, None)
    if isinstance(existing, Mapping) and existing.get("bound") is True:
        return dict(existing)

    intake_reaper = _install_intake_reaper()
    cancel_route = _register_cancel_route(app)
    bound = intake_reaper and cancel_route
    state = {
        "artifact_schema": VERSION,
        "status": "installed" if bound else "blocked",
        "bound": bound,
        "reserved_proof_scope": True,
        "proof_customer_id": PROOF_CUSTOMER_ID,
        "proof_project_id": PROOF_PROJECT_ID,
        "prior_proof_reaper_bound": intake_reaper,
        "proof_cancel_route_bound": cancel_route,
        "client_run_scope_untouched": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    setattr(app.state, _INSTALL_STATE, state)
    return dict(state)


__all__ = [
    "PROOF_CANCEL_ROUTE",
    "PROOF_CUSTOMER_ID",
    "PROOF_PROJECT_ID",
    "VERSION",
    "cancel_production_proof_record",
    "install_comprehensive_production_proof_lifecycle_v1",
]
