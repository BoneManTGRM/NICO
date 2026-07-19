from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_run_record_integrity.v1"
_PATCH_MARKER = "_nico_express_run_record_integrity_v1"
_TERMINAL_SUCCESS = {"complete", "completed"}
_TERMINAL_FAILURE = {"blocked", "failed", "error", "interrupted", "rejected"}
_RICH_FIELDS = (
    "reports",
    "sections",
    "maturity_signal",
    "technical_score",
    "assessment_completion",
    "express_completion",
    "evidence_artifact_bundle",
    "evidence_ledger",
    "client_acceptance",
)


def _response(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    value = record.get("response") if isinstance(record.get("response"), dict) else record.get("payload")
    return deepcopy(value) if isinstance(value, dict) else {}


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return value is not None


def reconcile_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Preserve exact-run terminal truth and rich completion evidence.

    Heartbeats, stage projections, and late compatibility wrappers may arrive
    after a richer record. They may add evidence, but cannot revive a terminal
    run, erase generated artifacts, or claim a complete stage for a failed run.
    """

    output = deepcopy(incoming)
    prior = _response(existing)
    prior_status = str(prior.get("status") or existing.get("status") or "").lower()
    incoming_status = str(output.get("status") or "").lower()

    for field in _RICH_FIELDS:
        if not _nonempty(output.get(field)) and _nonempty(prior.get(field)):
            output[field] = deepcopy(prior[field])

    if prior_status in _TERMINAL_SUCCESS and incoming_status not in _TERMINAL_SUCCESS:
        for field in (
            "status",
            "current_stage",
            "progress_percent",
            "report_generation_status",
            "human_review_required",
            "client_ready",
            "client_delivery_allowed",
            "delivery_status",
        ):
            if field in prior:
                output[field] = deepcopy(prior[field])
        output["status_regression_prevented"] = True

    status = str(output.get("status") or incoming_status or prior_status).lower()
    if status in _TERMINAL_SUCCESS:
        output["status"] = "complete"
        output["current_stage"] = "complete"
        output["progress_percent"] = 100
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False
        output["delivery_status"] = "blocked_pending_human_review"
    elif status in _TERMINAL_FAILURE:
        if str(output.get("current_stage") or "").lower() == "complete":
            output["current_stage"] = status if status in {"blocked", "failed", "interrupted"} else "failed"
            output["terminal_stage_contradiction_repaired"] = True
        output["progress_percent"] = 100
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False

    return output


def install_express_run_record_integrity() -> dict[str, Any]:
    from nico import express_async_api
    from nico.storage import STORE

    current: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]] = express_async_api._record
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    @wraps(current)
    def integrity_record(run_id: str, request_payload: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
        existing = STORE.get("assessment_runs", run_id) or {}
        reconciled = reconcile_record(existing if isinstance(existing, dict) else {}, response)
        return current(run_id, request_payload, reconciled)

    setattr(integrity_record, _PATCH_MARKER, True)
    setattr(integrity_record, "_nico_previous", current)
    express_async_api._record = integrity_record
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "terminal_status_regression_prevented": True,
        "rich_completion_fields_preserved": True,
        "failed_complete_stage_contradictions_repaired": True,
        "human_review_boundary_preserved": True,
    }


__all__ = ["PATCH_VERSION", "install_express_run_record_integrity", "reconcile_record"]
