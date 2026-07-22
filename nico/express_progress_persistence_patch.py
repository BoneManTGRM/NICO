from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Callable

EXPRESS_PROGRESS_PERSISTENCE_VERSION = "nico.express_progress_persistence.v5"
_RECORD_MARKER = "_nico_express_progress_record_v1"
_STATUS_MARKER = "_nico_express_progress_status_v1"
_HARDENED_STATUS_MARKER = "_nico_express_hardened_progress_status_v1"
_PROGRESS_COLLECTION = "express_run_progress"
_PROGRESS_LOCK = RLock()
_STAGE_ORDER = {
    "request_accepted": 0,
    "repository_evidence": 1,
    "scanner_reconciliation": 2,
    "accuracy_review": 3,
    "score_reconciliation": 4,
    "report_generation": 5,
    "truth_and_review_gates": 6,
    "complete": 7,
    "blocked": 7,
    "failed": 7,
    "interrupted": 7,
}
_TERMINAL_SUCCESS = {"complete", "completed"}
_TERMINAL_FAILURE = {"blocked", "failed", "error", "interrupted", "rejected"}
_ACTIVE = {"queued", "running", "starting", "pending"}


def _bounded_percent(value: Any) -> int:
    try:
        return max(0, min(100, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def _report_formats_ready(response: dict[str, Any]) -> bool:
    reports = response.get("reports") if isinstance(response.get("reports"), dict) else {}
    return all(bool(str(reports.get(name) or "").strip()) for name in ("markdown", "html", "pdf_base64"))


def _progress_identity(response: dict[str, Any]) -> dict[str, Any]:
    status = str(response.get("status") or "unknown").strip().lower()
    stage = str(response.get("current_stage") or "request_accepted").strip().lower()
    percent = _bounded_percent(response.get("progress_percent"))
    terminal = status in _TERMINAL_SUCCESS | _TERMINAL_FAILURE
    report_formats_ready = _report_formats_ready(response)
    terminal_success_ready = (
        status in _TERMINAL_SUCCESS
        and stage == "complete"
        and percent == 100
        and report_formats_ready
    )
    return {
        "run_id": str(response.get("run_id") or ""),
        "status": status,
        "current_stage": stage,
        "progress_percent": percent,
        "progress": deepcopy(response.get("progress") or []),
        "updated_at": response.get("updated_at"),
        "terminal": terminal,
        "terminal_success_ready": terminal_success_ready,
        "report_formats_ready": report_formats_ready,
        "report_generation_status": str(response.get("report_generation_status") or ""),
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }


def _terminal_success_ready(progress_record: dict[str, Any]) -> bool:
    return bool(
        str(progress_record.get("status") or "").lower() in _TERMINAL_SUCCESS
        and str(progress_record.get("current_stage") or "").lower() == "complete"
        and _bounded_percent(progress_record.get("progress_percent")) == 100
        and progress_record.get("terminal") is True
        and progress_record.get("terminal_success_ready") is True
        and progress_record.get("report_formats_ready") is True
    )


def _reconcile_progress_identity(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Keep lightweight progress monotonic and make terminal evidence sticky.

    Express report finalization and heartbeat publication can overlap in separate
    threads. The main assessment record has richer reconciliation, but the compact
    progress collection must independently prevent a late active-stage write from
    replacing a completed or failed exact run.
    """

    if not isinstance(existing, dict) or not existing:
        return deepcopy(incoming)

    existing_status = str(existing.get("status") or "unknown").lower()
    incoming_status = str(incoming.get("status") or "unknown").lower()

    if existing_status in _TERMINAL_SUCCESS | _TERMINAL_FAILURE:
        if incoming_status not in _TERMINAL_SUCCESS | _TERMINAL_FAILURE:
            return deepcopy(existing)
        if existing_status in _TERMINAL_FAILURE and incoming_status in _TERMINAL_SUCCESS:
            return deepcopy(existing)
        if existing_status in _TERMINAL_SUCCESS and incoming_status in _TERMINAL_FAILURE:
            return deepcopy(existing)

    if existing_status in _ACTIVE and incoming_status in _ACTIVE:
        existing_stage = str(existing.get("current_stage") or "request_accepted")
        incoming_stage = str(incoming.get("current_stage") or "request_accepted")
        existing_rank = _STAGE_ORDER.get(existing_stage, -1)
        incoming_rank = _STAGE_ORDER.get(incoming_stage, -1)
        existing_percent = _bounded_percent(existing.get("progress_percent"))
        incoming_percent = _bounded_percent(incoming.get("progress_percent"))
        if existing_rank > incoming_rank or (
            existing_rank == incoming_rank and existing_percent > incoming_percent
        ):
            return deepcopy(existing)

    return deepcopy(incoming)


def _persist_progress(api: Any, run_id: str, response: dict[str, Any]) -> dict[str, Any]:
    incoming = _progress_identity(response)
    with _PROGRESS_LOCK:
        existing = api.STORE.get(_PROGRESS_COLLECTION, run_id)
        reconciled = _reconcile_progress_identity(
            existing if isinstance(existing, dict) else {},
            incoming,
        )
        api.STORE.put(_PROGRESS_COLLECTION, run_id, reconciled)
    return reconciled


def _force_terminal_success(api: Any, output: dict[str, Any]) -> dict[str, Any]:
    output["status"] = "complete"
    output["current_stage"] = "complete"
    output["progress_percent"] = 100
    output["report_generation_status"] = "complete"
    output["terminal"] = True
    output["progress"] = api._stage_progress(
        "complete",
        "complete",
        "Express assessment completed. Draft report artifacts are ready for required human review.",
        evidence={"report_formats_ready": bool((output.get("reports") or {}).get("pdf_base64"))},
    )
    output["human_review_required"] = True
    output["client_ready"] = False
    output["client_delivery_allowed"] = False
    output["delivery_status"] = "blocked_pending_human_review"
    return output


def _overlay_progress(
    api: Any,
    run_id: str,
    response: dict[str, Any],
    *,
    store: Any | None = None,
) -> dict[str, Any]:
    output = deepcopy(response)
    status = str(output.get("status") or "unknown").lower()

    # The authoritative status function has already completed tenant/run scope
    # validation before this function is called. Error and not-found responses
    # are never passed here, so independently persisted progress cannot disclose
    # another tenant's run or replace an authorization failure.
    if status in _TERMINAL_SUCCESS:
        return _force_terminal_success(api, output)

    selected_store = store if store is not None else api.STORE
    progress_record = selected_store.get(_PROGRESS_COLLECTION, run_id)
    if not isinstance(progress_record, dict):
        return output

    stored_status = str(progress_record.get("status") or "unknown").lower()
    response_stage = str(output.get("current_stage") or "request_accepted")
    stored_stage = str(progress_record.get("current_stage") or "request_accepted")
    stored_terminal_success = _terminal_success_ready(progress_record)
    use_stored = (
        stored_status in _ACTIVE
        and _STAGE_ORDER.get(stored_stage, -1) >= _STAGE_ORDER.get(response_stage, -1)
    ) or stored_status in _TERMINAL_FAILURE or stored_terminal_success
    if not use_stored:
        return output

    for key in ("status", "current_stage", "progress_percent", "progress", "updated_at"):
        if key in progress_record:
            output[key] = deepcopy(progress_record[key])

    if stored_terminal_success:
        output = _force_terminal_success(api, output)
        lifecycle = output.get("lifecycle_status") if isinstance(output.get("lifecycle_status"), dict) else {}
        lifecycle = deepcopy(lifecycle)
        lifecycle.update(
            {
                "status_reconciled_from_independent_progress": True,
                "terminal_progress_record_verified": True,
                "status_read_is_terminal_write": False,
            }
        )
        output["lifecycle_status"] = lifecycle
        output["progress_reconciliation"] = {
            "version": EXPRESS_PROGRESS_PERSISTENCE_VERSION,
            "source": _PROGRESS_COLLECTION,
            "exact_run_identity_preserved": True,
            "terminal_success_recovered": True,
            "report_formats_ready": True,
            "status_read_only": True,
        }
    else:
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False
    return output


def install_express_progress_persistence() -> dict[str, Any]:
    from nico import express_async_api as api

    current_record: Callable[..., dict[str, Any]] = api._record
    record_status = "already_installed"
    if not getattr(current_record, _RECORD_MARKER, False):
        def record_with_independent_progress(
            run_id: str,
            request_payload: dict[str, Any],
            response: dict[str, Any],
        ) -> dict[str, Any]:
            persisted = current_record(run_id, request_payload, response)
            _persist_progress(api, run_id, response)
            return persisted

        setattr(record_with_independent_progress, _RECORD_MARKER, True)
        setattr(record_with_independent_progress, "_nico_previous", current_record)
        api._record = record_with_independent_progress
        record_status = "installed"

    current_status: Callable[..., dict[str, Any]] = api.express_assessment_status
    status_status = "already_installed"
    if not getattr(current_status, _STATUS_MARKER, False):
        def status_with_independent_progress(run_id: str, req: Any) -> dict[str, Any]:
            result = current_status(run_id, req)
            return _overlay_progress(api, run_id, result, store=api.STORE)

        setattr(status_with_independent_progress, _STATUS_MARKER, True)
        setattr(status_with_independent_progress, "_nico_previous", current_status)
        api.express_assessment_status = status_with_independent_progress
        status_status = "installed"

    # Production replaces the typed FastAPI route with the request-tolerant
    # lifecycle hardening endpoint. That endpoint calls this module-level function
    # at request time, so it must receive the same independent progress overlay.
    from nico import lifecycle_status_hardening as hardening

    current_hardened_status: Callable[[str, str, str], dict[str, Any]] = hardening._express_status_response
    hardened_status = "already_installed"
    if not getattr(current_hardened_status, _HARDENED_STATUS_MARKER, False):
        def hardened_status_with_independent_progress(
            run_id: str,
            customer_id: str,
            project_id: str,
        ) -> dict[str, Any]:
            result = current_hardened_status(run_id, customer_id, project_id)
            return _overlay_progress(api, run_id, result, store=hardening.STORE)

        setattr(hardened_status_with_independent_progress, _HARDENED_STATUS_MARKER, True)
        setattr(hardened_status_with_independent_progress, "_nico_previous", current_hardened_status)
        hardening._express_status_response = hardened_status_with_independent_progress
        hardened_status = "installed"

    from nico.express_durable_duplicate_start_guard import install_express_durable_duplicate_start_guard
    from nico.express_repository_stage_watchdog import install_express_repository_stage_watchdog

    duplicate_start_guard = install_express_durable_duplicate_start_guard()
    watchdog = install_express_repository_stage_watchdog()
    return {
        "status": "installed",
        "version": EXPRESS_PROGRESS_PERSISTENCE_VERSION,
        "collection": _PROGRESS_COLLECTION,
        "record_binding": record_status,
        "typed_status_binding": status_status,
        "hardened_status_binding": hardened_status,
        "report_record_overwrite_can_reset_progress": False,
        "terminal_progress_can_regress": False,
        "terminal_success_forces_100_percent": True,
        "production_hardened_status_uses_terminal_progress": True,
        "tenant_scope_failures_are_never_overlaid": True,
        "durable_duplicate_start_guard": duplicate_start_guard,
        "repository_stage_watchdog": watchdog,
        "human_review_required": True,
        "client_ready": False,
    }


__all__ = [
    "EXPRESS_PROGRESS_PERSISTENCE_VERSION",
    "install_express_progress_persistence",
]
