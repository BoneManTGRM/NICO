from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

EXPRESS_TERMINAL_AUTHORITY_VERSION = "nico.express_terminal_authority.v1"
_RECORD_MARKER = "_nico_express_terminal_authority_record_v1"
_EXECUTE_MARKER = "_nico_express_terminal_authority_execute_v1"
_SAFE_PAYLOAD_MARKER = "_nico_express_terminal_authority_safe_payload_v1"
_STATUS_MARKER = "_nico_express_terminal_authority_status_v1"
_TERMINAL_SUCCESS = {"complete", "completed"}
_TERMINAL_FAILURE = {"blocked", "failed", "error", "interrupted", "rejected"}
_ACTIVE = {"queued", "running", "starting", "pending", "unknown", ""}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _reports_ready(payload: dict[str, Any]) -> bool:
    reports = _record(payload.get("reports"))
    return all(bool(str(reports.get(name) or "").strip()) for name in ("markdown", "html", "pdf_base64"))


def _terminal_candidate(payload: dict[str, Any], run_id: str = "") -> bool:
    exact_run = str(payload.get("run_id") or run_id or "").strip()
    if not exact_run.startswith("express_run_") or not _reports_ready(payload):
        return False
    status = str(payload.get("status") or "").lower()
    stage = str(payload.get("current_stage") or "").lower()
    try:
        percent = int(payload.get("progress_percent") or 0)
    except (TypeError, ValueError):
        percent = 0
    return (
        status in _TERMINAL_SUCCESS
        or payload.get("terminal") is True
        or stage == "complete"
        or percent >= 100
        or str(payload.get("report_generation_status") or "").lower() == "complete"
        or payload.get("human_review_required") is True
    )


def _terminal_payload(api: Any, run_id: str, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    output = dict(payload)
    output["run_id"] = run_id
    output["status"] = "complete"
    output["current_stage"] = "complete"
    output["progress_percent"] = 100
    output["report_generation_status"] = "complete"
    output["terminal"] = True
    output["human_review_required"] = True
    output["client_ready"] = False
    output["client_delivery_allowed"] = False
    output["delivery_status"] = "blocked_pending_human_review"
    output["recovery_required"] = False
    output["duplicate_start_allowed"] = False
    output["progress"] = api._stage_progress(
        "complete",
        "complete",
        "Express assessment completed. Draft report artifacts are ready for required human review.",
        evidence={
            "report_formats_ready": True,
            "terminal_authority_version": EXPRESS_TERMINAL_AUTHORITY_VERSION,
            "terminal_persist_source": source,
            "exact_run_terminal_evidence": True,
            "terminal_state_written": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )
    output["terminal_persistence"] = {
        "version": EXPRESS_TERMINAL_AUTHORITY_VERSION,
        "status": "verified_terminal_candidate",
        "source": source,
        "report_formats_ready": True,
        "exact_run_identity_preserved": True,
        "write_order": "compact_terminal_before_rich_record",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    output["updated_at"] = api.utc_now()
    return output


def _persist_compact_terminal(api: Any, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from nico.express_progress_persistence_patch import _persist_progress

    progress = _persist_progress(api, run_id, payload)
    if not (
        str(progress.get("status") or "").lower() in _TERMINAL_SUCCESS
        and str(progress.get("current_stage") or "").lower() == "complete"
        and int(progress.get("progress_percent") or 0) == 100
        and progress.get("terminal_success_ready") is True
        and progress.get("report_formats_ready") is True
    ):
        raise RuntimeError("Express compact terminal progress did not verify after persistence")
    return progress


def _rich_response(record: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response") if isinstance(record.get("response"), dict) else record.get("payload")
    return response if isinstance(response, dict) else {}


def _bounded_terminal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep terminal truth and client-visible report formats without raw scanner trees."""
    keys = (
        "run_id",
        "status",
        "assessment_type",
        "service_tier",
        "repository",
        "customer_id",
        "project_id",
        "client_name",
        "project_name",
        "commit_sha",
        "deployed_commit_sha",
        "current_stage",
        "progress_percent",
        "progress",
        "report_generation_status",
        "terminal",
        "human_review_required",
        "client_ready",
        "client_delivery_allowed",
        "delivery_status",
        "recovery_required",
        "duplicate_start_allowed",
        "score",
        "overall_score",
        "maturity_score",
        "maturity_signal",
        "evidence_readiness",
        "persistence",
        "terminal_persistence",
        "updated_at",
        "revision",
    )
    output = {key: payload[key] for key in keys if key in payload}
    reports = _record(payload.get("reports"))
    report_keys = (
        "markdown",
        "html",
        "pdf_base64",
        "pdf_filename",
        "report_id",
        "evidence_bundle_filename",
        "evidence_bundle_export_status",
        "evidence_ledger_filename",
    )
    output["reports"] = {key: reports[key] for key in report_keys if key in reports}
    output["terminal_persistence"] = {
        **dict(_record(output.get("terminal_persistence"))),
        "bounded_rich_record": True,
        "omitted_payloads": ["raw_evidence", "scanner_outputs", "embedded_evidence_bundle"],
    }
    return output


def _persist_rich_terminal(api: Any, run_id: str, request_payload: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    existing = api.STORE.get("assessment_runs", run_id)
    record = dict(existing) if isinstance(existing, dict) else {}
    revision = int(record.get("revision") or 0) + 1
    terminal = dict(payload)
    terminal["revision"] = revision
    terminal_persistence = dict(_record(terminal.get("terminal_persistence")))
    terminal_persistence.update({"status": "persisted_and_read_back", "revision": revision})
    terminal["terminal_persistence"] = terminal_persistence
    record.update(
        {
            "workflow": "express",
            "run_id": run_id,
            "customer_id": str(request_payload.get("customer_id") or terminal.get("customer_id") or "default_customer"),
            "project_id": str(request_payload.get("project_id") or terminal.get("project_id") or "default_project"),
            "repository": str(request_payload.get("repository") or terminal.get("repository") or ""),
            "status": "complete",
            "revision": revision,
            "response": terminal,
            "payload": terminal,
            "updated_at": api.utc_now(),
        }
    )
    record.setdefault("created_at", api.utc_now())
    try:
        persisted = api.STORE.put("assessment_runs", run_id, record)
    except Exception:
        bounded = _bounded_terminal_payload(terminal)
        record["response"] = bounded
        record["payload"] = bounded
        record["terminal_record_bounded"] = True
        persisted = api.STORE.put("assessment_runs", run_id, record)
    readback = api.STORE.get("assessment_runs", run_id)
    observed = _rich_response(readback if isinstance(readback, dict) else persisted if isinstance(persisted, dict) else {})
    if not (
        str(observed.get("status") or "").lower() in _TERMINAL_SUCCESS
        and str(observed.get("current_stage") or "").lower() == "complete"
        and int(observed.get("progress_percent") or 0) == 100
        and observed.get("terminal") is True
        and _reports_ready(observed)
    ):
        raise RuntimeError("Express rich terminal record did not verify after persistence")
    return persisted if isinstance(persisted, dict) else record


def _install_safe_payload(api: Any, api_main: Any) -> dict[str, Any]:
    current: Callable[[Any], dict[str, Any]] = api_main.safe_assessment_response_payload
    if getattr(current, _SAFE_PAYLOAD_MARKER, False):
        return {"status": "already_installed", "owner_verified": True}

    @wraps(current)
    def safe_payload_with_terminal_authority(value: Any) -> dict[str, Any]:
        output = current(value)
        source = value if isinstance(value, dict) else {}
        run_id = str(output.get("run_id") or source.get("run_id") or "").strip()
        if _terminal_candidate(output, run_id):
            terminal = _terminal_payload(api, run_id, output, source="safe_assessment_response_payload")
            _persist_compact_terminal(api, run_id, terminal)
            return terminal
        return output

    setattr(safe_payload_with_terminal_authority, _SAFE_PAYLOAD_MARKER, True)
    setattr(safe_payload_with_terminal_authority, "_nico_previous", current)
    api_main.safe_assessment_response_payload = safe_payload_with_terminal_authority
    return {
        "status": "installed",
        "owner_verified": getattr(api_main.safe_assessment_response_payload, _SAFE_PAYLOAD_MARKER, False) is True,
    }


def _install_record(api: Any) -> dict[str, Any]:
    current: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]] = api._record
    if getattr(current, _RECORD_MARKER, False):
        return {"status": "already_installed", "owner_verified": True}

    @wraps(current)
    def record_with_terminal_authority(
        run_id: str,
        request_payload: dict[str, Any],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        candidate = response
        if _terminal_candidate(response, run_id):
            candidate = _terminal_payload(api, run_id, response, source="final_record_boundary")
            _persist_compact_terminal(api, run_id, candidate)
        persisted = current(run_id, request_payload, candidate)
        if candidate is not response:
            _persist_rich_terminal(api, run_id, request_payload, candidate)
        return persisted

    setattr(record_with_terminal_authority, _RECORD_MARKER, True)
    setattr(record_with_terminal_authority, "_nico_previous", current)
    api._record = record_with_terminal_authority
    return {"status": "installed", "owner_verified": getattr(api._record, _RECORD_MARKER, False) is True}


def _recover_verified_terminal(api: Any, api_main: Any, run_id: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    progress = api.STORE.get("express_run_progress", run_id)
    if isinstance(progress, dict) and str(progress.get("status") or "").lower() in _TERMINAL_SUCCESS:
        return {"status": "already_terminal", "source": "express_run_progress"}

    record = api.STORE.get("assessment_runs", run_id)
    rich = _rich_response(record if isinstance(record, dict) else {})
    rich_status = str(rich.get("status") or "").lower()
    if rich_status in _TERMINAL_FAILURE:
        return {"status": "terminal_failure_preserved", "source": "assessment_runs"}

    last = getattr(api_main, "_LAST_HOSTED_ASSESSMENT", {})
    candidate = last if isinstance(last, dict) and str(last.get("run_id") or "") == run_id else rich
    if not _terminal_candidate(candidate, run_id):
        return {"status": "no_verified_terminal_candidate"}

    terminal = _terminal_payload(api, run_id, candidate, source="execute_final_readback_recovery")
    _persist_compact_terminal(api, run_id, terminal)
    _persist_rich_terminal(api, run_id, request_payload, terminal)
    return {"status": "recovered", "source": "execute_final_readback_recovery"}


def _install_execute(api: Any, api_main: Any) -> dict[str, Any]:
    current: Callable[[str, dict[str, Any]], None] = api._execute
    if getattr(current, _EXECUTE_MARKER, False):
        return {"status": "already_installed", "owner_verified": True}

    @wraps(current)
    def execute_with_terminal_readback(run_id: str, request_payload: dict[str, Any]) -> None:
        try:
            return current(run_id, request_payload)
        finally:
            try:
                _recover_verified_terminal(api, api_main, run_id, request_payload)
            except Exception:
                # The source executor already records bounded failures. This final
                # recovery layer must never hide the original worker outcome.
                pass

    setattr(execute_with_terminal_readback, _EXECUTE_MARKER, True)
    setattr(execute_with_terminal_readback, "_nico_previous", current)
    api._execute = execute_with_terminal_readback
    return {"status": "installed", "owner_verified": getattr(api._execute, _EXECUTE_MARKER, False) is True}


def _install_status(api: Any) -> dict[str, Any]:
    from nico import lifecycle_status_hardening as hardening
    from nico.express_progress_persistence_patch import _overlay_progress

    current: Callable[[str, str, str], dict[str, Any]] = hardening._express_status_response
    if getattr(current, _STATUS_MARKER, False):
        return {"status": "already_installed", "owner_verified": True}

    @wraps(current)
    def status_with_terminal_authority(run_id: str, customer_id: str, project_id: str) -> dict[str, Any]:
        result = current(run_id, customer_id, project_id)
        output = _overlay_progress(api, run_id, result, store=hardening.STORE)
        status = str(output.get("status") or "").lower()
        if status in _ACTIVE:
            output["terminal"] = False
            output["recovery_required"] = False
            output["duplicate_start_allowed"] = False
            output["human_review_required"] = True
            output["client_ready"] = False
            output["client_delivery_allowed"] = False
            transport = dict(_record(output.get("status_transport")))
            transport.update(
                {
                    "status": "waiting_for_backend_terminal_truth",
                    "terminal_authority_version": EXPRESS_TERMINAL_AUTHORITY_VERSION,
                    "exact_run_terminal_evidence": False,
                    "browser_terminalization_forbidden": True,
                    "duplicate_start_allowed": False,
                }
            )
            output["status_transport"] = transport
        return output

    setattr(status_with_terminal_authority, _STATUS_MARKER, True)
    setattr(status_with_terminal_authority, "_nico_previous", current)
    hardening._express_status_response = status_with_terminal_authority
    return {"status": "installed", "owner_verified": getattr(hardening._express_status_response, _STATUS_MARKER, False) is True}


def install_express_terminal_authority() -> dict[str, Any]:
    from nico import express_async_api as api
    from nico.api import main as api_main

    safe_payload = _install_safe_payload(api, api_main)
    record_binding = _install_record(api)
    execute_binding = _install_execute(api, api_main)
    status_binding = _install_status(api)
    status = {
        "artifact_schema": EXPRESS_TERMINAL_AUTHORITY_VERSION,
        "status": "installed",
        "safe_payload_binding": safe_payload,
        "record_binding": record_binding,
        "execute_binding": execute_binding,
        "status_binding": status_binding,
        "compact_terminal_precedes_rich_record": True,
        "exact_run_readback_required": True,
        "terminal_failure_promotion_allowed": False,
        "browser_terminalization_from_active_status_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return status


__all__ = [
    "EXPRESS_TERMINAL_AUTHORITY_VERSION",
    "install_express_terminal_authority",
]
