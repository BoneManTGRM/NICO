from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import nico.assessment_recovery as recovery

EXPRESS_RECOVERY_VERSION = "nico.express_recovery_compat.v1"
_MARKER = "_nico_express_recovery_v1"
EXPRESS_REQUIRED_OPERATION_ROUTES = {
    "POST /assessment/express-run",
    "POST /assessment/express-run/{run_id}/status",
}


def install_express_recovery_compatibility() -> dict[str, Any]:
    """Include Express lifecycle records in recovery without automatic reruns."""

    current_summary: Callable[[dict[str, Any]], dict[str, Any]] = recovery._safe_run_summary
    if bool(getattr(current_summary, _MARKER, False)):
        return {"status": "already_installed", "version": EXPRESS_RECOVERY_VERSION}

    import nico.operations_readiness as operations_readiness

    original_summary = current_summary
    original_patch = recovery._recovery_patch
    original_valid_resume = recovery._valid_resume_source
    original_inventory = recovery.assessment_recovery_inventory

    recovery.SUPPORTED_WORKFLOWS.add("express")
    recovery.ACTIVE_ASSESSMENT_STATUSES.add("queued")
    recovery.TERMINAL_ASSESSMENT_STATUSES.add("interrupted")
    operations_readiness.REQUIRED_OPERATION_ROUTES.update(EXPRESS_REQUIRED_OPERATION_ROUTES)

    def safe_run_summary(record: dict[str, Any]) -> dict[str, Any]:
        item = original_summary(record)
        if str(record.get("workflow") or "") != "express":
            return item
        response = record.get("response") if isinstance(record.get("response"), dict) else {}
        item["service_tier"] = "express"
        item["report_id"] = str(
            item.get("report_id")
            or response.get("report_id")
            or (response.get("reports") or {}).get("report_id")
            or ""
        )
        recovery_state = deepcopy(item.get("recovery") or {})
        if str(record.get("status") or "") == "interrupted":
            recovery_state.setdefault("state", recovery.RECOVERY_REQUIRED_STATUS)
            recovery_state.setdefault("reason", "express_worker_interrupted")
            recovery_state.setdefault("detected_at", record.get("updated_at"))
        recovery_state["resume_allowed"] = False
        recovery_state["automatic_resume"] = False
        item["recovery"] = recovery_state
        item["human_review_required"] = True
        item["client_delivery_allowed"] = False
        return item

    def recovery_patch(
        record: dict[str, Any],
        *,
        now_text: str,
        age_seconds: float | None,
    ) -> dict[str, Any]:
        patch = original_patch(record, now_text=now_text, age_seconds=age_seconds)
        if str(record.get("workflow") or "") != "express":
            return patch
        state = deepcopy(patch.get("recovery") or {})
        state.update(
            {
                "reason": "stale_express_worker",
                "resume_allowed": False,
                "automatic_resume": False,
                "operator_note": "Review the exact Express run record before starting any replacement run. Automatic or same-ID re-execution is not permitted.",
            }
        )
        patch["recovery"] = state
        return patch

    def valid_resume_source(record: dict[str, Any]) -> tuple[bool, str]:
        if str(record.get("workflow") or "") == "express":
            return False, "express_manual_review_required"
        return original_valid_resume(record)

    def assessment_recovery_inventory(*, store=None, refresh: bool = False, limit: int = 200):
        result = original_inventory(store=store, refresh=refresh, limit=limit)
        active = recovery._store(store)
        bounded_limit = max(1, min(int(limit), recovery.MAX_INVENTORY_LIMIT))
        items = list(result.get("recovery_required") or [])
        known_ids = {str(item.get("run_id") or "") for item in items if isinstance(item, dict)}
        for record in active.list("assessment_runs")[: recovery.MAX_RECONCILE_RECORDS]:
            if not isinstance(record, dict):
                continue
            if str(record.get("workflow") or "") != "express" or str(record.get("status") or "") != "interrupted":
                continue
            run_id = str(record.get("run_id") or record.get("id") or "")
            if not run_id or run_id in known_ids:
                continue
            items.append(safe_run_summary(record))
            known_ids.add(run_id)
        items.sort(key=lambda item: str(item.get("updated_at") or ""))
        items = items[:bounded_limit]

        counts = deepcopy(result.get("counts") or {})
        counts["recovery_required"] = len(items)
        counts["express_recovery_required"] = sum(
            1 for item in items if isinstance(item, dict) and item.get("workflow") == "express"
        )
        result["counts"] = counts
        result["recovery_required"] = items
        result["status"] = "attention_required" if items else "clear"
        result["operator_action"] = (
            "Review saved scope, authorization, run, snapshot, scanner, report, and approval identities before any continuation. "
            "Mid and Full may resume only through their exact-state controls. Interrupted Express records remain manual-review-only; do not start a replacement until the saved worker is confirmed terminal."
        )
        return result

    setattr(safe_run_summary, _MARKER, True)
    setattr(safe_run_summary, "_nico_previous", original_summary)
    setattr(recovery_patch, _MARKER, True)
    setattr(valid_resume_source, _MARKER, True)
    setattr(assessment_recovery_inventory, _MARKER, True)
    recovery._safe_run_summary = safe_run_summary
    recovery._recovery_patch = recovery_patch
    recovery._valid_resume_source = valid_resume_source
    recovery.assessment_recovery_inventory = assessment_recovery_inventory
    return {
        "status": "installed",
        "version": EXPRESS_RECOVERY_VERSION,
        "supported_workflow": "express",
        "required_operations_routes": sorted(EXPRESS_REQUIRED_OPERATION_ROUTES),
        "immediate_interrupted_inventory": True,
        "automatic_resume": False,
        "same_id_resume": False,
        "human_review_required": True,
    }


__all__ = [
    "EXPRESS_RECOVERY_VERSION",
    "EXPRESS_REQUIRED_OPERATION_ROUTES",
    "install_express_recovery_compatibility",
]
