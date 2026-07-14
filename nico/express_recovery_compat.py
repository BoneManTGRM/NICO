from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import nico.assessment_recovery as recovery

EXPRESS_RECOVERY_VERSION = "nico.express_recovery_compat.v1"
_MARKER = "_nico_express_recovery_v1"


def install_express_recovery_compatibility() -> dict[str, Any]:
    """Include Express lifecycle records in recovery without automatic reruns."""

    current_summary: Callable[[dict[str, Any]], dict[str, Any]] = recovery._safe_run_summary
    if bool(getattr(current_summary, _MARKER, False)):
        return {"status": "already_installed", "version": EXPRESS_RECOVERY_VERSION}

    original_summary = current_summary
    original_patch = recovery._recovery_patch
    original_valid_resume = recovery._valid_resume_source
    original_inventory = recovery.assessment_recovery_inventory

    recovery.SUPPORTED_WORKFLOWS.add("express")
    recovery.ACTIVE_ASSESSMENT_STATUSES.add("queued")
    recovery.TERMINAL_ASSESSMENT_STATUSES.add("interrupted")

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
        counts = deepcopy(result.get("counts") or {})
        items = result.get("recovery_required") if isinstance(result.get("recovery_required"), list) else []
        counts["express_recovery_required"] = sum(
            1 for item in items if isinstance(item, dict) and item.get("workflow") == "express"
        )
        result["counts"] = counts
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
        "automatic_resume": False,
        "same_id_resume": False,
        "human_review_required": True,
    }


__all__ = ["EXPRESS_RECOVERY_VERSION", "install_express_recovery_compatibility"]
