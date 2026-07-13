from __future__ import annotations

from typing import Any


_INSTALLED = False


def _blocked_result(step: str, run_id: str, upstream_status: str) -> dict[str, Any]:
    label = step.replace("_", " ")
    return {
        "status": "blocked",
        "message": (
            f"{label.capitalize()} is blocked because required upstream evidence "
            f"is {upstream_status or 'not available'}; this step was not skipped by request."
        ),
        "evidence": {
            "run_id": run_id,
            "blocked_by_upstream": True,
            "upstream_status": upstream_status or "not_available",
        },
    }


def install_full_blocked_state_truth() -> None:
    """Distinguish intentional skips from downstream evidence blockers.

    Full-run handlers may intentionally skip reports or review requests only
    when the requester disabled those stages. Enabled stages remain planned
    while required upstream work is pending, and become blocked only after the
    required upstream evidence is unavailable, failed, skipped, or blocked.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    from nico import full_assessment_orchestrator as orchestrator

    original_scoring = orchestrator._scoring_handler
    original_reports = orchestrator._reports_handler
    original_approval = orchestrator._approval_request_handler

    def truthful_scoring(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        result = original_scoring(context, outputs)
        if result.get("status") != "planned":
            return result
        attachment = outputs.get("evidence_attachment") if isinstance(outputs.get("evidence_attachment"), dict) else {}
        upstream_status = str(attachment.get("status") or "not_attached")
        if upstream_status in {"pending", "queued", "running"}:
            return result
        return _blocked_result("scoring", str(context.get("run_id") or ""), upstream_status)

    def truthful_reports(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        result = original_reports(context, outputs)
        if not context.get("build_reports") or result.get("status") != "planned":
            return result
        scoring = outputs.get("scoring") if isinstance(outputs.get("scoring"), dict) else {}
        upstream_status = str(scoring.get("status") or "not_available")
        if upstream_status in {"planned", "pending", "queued", "running"}:
            return result
        return _blocked_result("reports", str(context.get("run_id") or ""), upstream_status)

    def truthful_approval(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        result = original_approval(context, outputs)
        if not context.get("create_final_review_request") or result.get("status") != "planned":
            return result
        reports = outputs.get("reports") if isinstance(outputs.get("reports"), dict) else {}
        upstream_status = str(reports.get("status") or "not_available")
        if upstream_status in {"planned", "pending", "queued", "running"}:
            return result
        return _blocked_result("approval_request", str(context.get("run_id") or ""), upstream_status)

    orchestrator._scoring_handler = truthful_scoring
    orchestrator._reports_handler = truthful_reports
    orchestrator._approval_request_handler = truthful_approval
    _INSTALLED = True
