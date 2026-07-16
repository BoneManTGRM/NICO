from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

MID_TRUTH_IDENTITY_TRANSPORT_VERSION = "nico.mid_truth_identity_transport.v3"
_TERMINAL_MARKER = "_nico_mid_truth_identity_read_only_terminal_v3"
_STATUS_MARKER = "_nico_mid_truth_identity_post_repair_v3"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _scope_matches(record: dict[str, Any], customer_id: str, project_id: str) -> bool:
    request = _dict(record.get("request"))
    stored_customer = str(record.get("customer_id") or request.get("customer_id") or "default_customer")
    stored_project = str(record.get("project_id") or request.get("project_id") or "default_project")
    return stored_customer == customer_id and stored_project == project_id


def _scoped_repairable(
    record: Any,
    customer_id: str,
    project_id: str,
    store: Any,
    repairable: Callable[[dict[str, Any], Any], bool],
) -> bool:
    return (
        isinstance(record, dict)
        and _scope_matches(record, customer_id, project_id)
        and repairable(record, store)
    )


async def _request_scope(request: Any) -> tuple[str, str]:
    payload: dict[str, Any] = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}
    query = getattr(request, "query_params", {})
    customer_id = str(payload.get("customer_id") or query.get("customer_id") or "default_customer")[:120]
    project_id = str(payload.get("project_id") or query.get("project_id") or "default_project")[:120]
    return customer_id, project_id


def _set_progress_step(response: dict[str, Any], message: str) -> None:
    progress = [deepcopy(item) for item in _list(response.get("progress")) if isinstance(item, dict)]
    replacement = {
        "step": "approval_request",
        "status": "running",
        "message": message,
        "evidence": {
            "same_run_identity_preserved": True,
            "repository_recaptured": False,
            "scanner_rerun": False,
            "score_recomputed": False,
            "replacement_run_created": False,
            "duplicate_start_allowed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }
    for index, item in enumerate(progress):
        if str(item.get("step") or "") == "approval_request":
            progress[index] = replacement
            response["progress"] = progress
            return
    progress.append(replacement)
    response["progress"] = progress


def project_stale_mid_approval_repair(record: dict[str, Any]) -> dict[str, Any]:
    response = deepcopy(_dict(record.get("response")))
    run_id = str(record.get("run_id") or response.get("run_id") or "")
    response["run_id"] = run_id
    response["customer_id"] = str(record.get("customer_id") or response.get("customer_id") or "default_customer")
    response["project_id"] = str(record.get("project_id") or response.get("project_id") or "default_project")
    response["repository"] = str(record.get("repository") or response.get("repository") or "")
    response["status"] = "running"
    response["current_stage"] = "approval_request"
    response["progress_percent"] = max(99, int(response.get("progress_percent") or 0))
    response["approval_request_status"] = "repair_pending"
    response["continuation_required"] = True
    response["recovery_required"] = False
    response["status_refresh"] = True
    response["same_run_approval_repair"] = {
        "status": "pending_post_continuation",
        "version": MID_TRUTH_IDENTITY_TRANSPORT_VERSION,
        "same_run_id": run_id,
        "live_status_read_only": True,
        "post_continuation_required": True,
        "tenant_scope_required": True,
        "repository_recaptured": False,
        "scanner_rerun": False,
        "score_recomputed": False,
        "replacement_run_created": False,
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    _set_progress_step(
        response,
        "NICO retained the completed Mid run and will rebuild only the report/review identity chain through the scoped canonical POST continuation.",
    )
    response["human_review_required"] = True
    response["client_ready"] = False
    return response


def install_mid_truth_identity_transport() -> dict[str, Any]:
    from nico import mid_terminal_truth_patch as terminal
    from nico.mid_truth_identity_consistency import _repairable_stale_record, repair_stale_mid_approval
    from nico.storage import STORE

    current_terminal: Callable[[dict[str, Any]], dict[str, Any] | None] = terminal._terminal_retained_response
    terminal_installed = False
    if not getattr(current_terminal, _TERMINAL_MARKER, False):
        read_only_previous = getattr(current_terminal, "_nico_previous", current_terminal)

        @wraps(read_only_previous)
        def read_only_terminal(record: dict[str, Any]) -> dict[str, Any] | None:
            if isinstance(record, dict) and _repairable_stale_record(record, STORE):
                return project_stale_mid_approval_repair(record)
            return read_only_previous(record)

        setattr(read_only_terminal, _TERMINAL_MARKER, True)
        setattr(read_only_terminal, "_nico_previous", read_only_previous)
        terminal._terminal_retained_response = read_only_terminal
        terminal_installed = True

    current_status: Callable[..., Any] = terminal.mid_status_endpoint
    status_installed = False
    if not getattr(current_status, _STATUS_MARKER, False):
        @wraps(current_status)
        async def post_status_with_same_run_repair(run_id: str, request: Any) -> dict[str, Any]:
            record = STORE.get("assessment_runs", run_id)
            customer_id, project_id = await _request_scope(request)
            if _scoped_repairable(
                record,
                customer_id,
                project_id,
                STORE,
                _repairable_stale_record,
            ):
                repaired = repair_stale_mid_approval(record, store=STORE)
                if isinstance(repaired, dict):
                    repaired["status_read_path"] = {
                        "version": MID_TRUTH_IDENTITY_TRANSPORT_VERSION,
                        "mode": "same_run_approval_identity_post_repair",
                        "read_only": False,
                        "post_continuation": True,
                        "tenant_scope_validated": True,
                        "repository_recaptured": False,
                        "scanner_rerun": False,
                        "score_recomputed": False,
                        "replacement_run_created": False,
                    }
                    return repaired
            return await current_status(run_id, request)

        setattr(post_status_with_same_run_repair, _STATUS_MARKER, True)
        setattr(post_status_with_same_run_repair, "_nico_previous", current_status)
        terminal.mid_status_endpoint = post_status_with_same_run_repair
        status_installed = True

    return {
        "status": "installed" if terminal_installed or status_installed else "already_installed",
        "version": MID_TRUTH_IDENTITY_TRANSPORT_VERSION,
        "live_status_mutates_storage": False,
        "live_status_projects_continuation": True,
        "post_status_performs_same_run_repair": True,
        "post_repair_requires_exact_tenant_scope": True,
        "post_repair_scope_validated_before_mutation": True,
        "wrong_scope_repair_possible": False,
        "cross_tenant_run_existence_disclosed": False,
        "repository_recaptured": False,
        "scanner_rerun": False,
        "score_recomputed": False,
        "replacement_run_created": False,
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_TRUTH_IDENTITY_TRANSPORT_VERSION",
    "_scope_matches",
    "_scoped_repairable",
    "install_mid_truth_identity_transport",
    "project_stale_mid_approval_repair",
]
