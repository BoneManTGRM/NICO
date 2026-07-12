from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from nico.final_review_workflow import request_final_review
from nico.scanner_worker import get_scan
from nico.storage import STORE, StorageAdapter

TERMINAL_SCAN_STATUSES = {"complete", "failed", "error", "blocked", "not_found"}
RUNNING_SCAN_STATUSES = {"queued", "running"}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _progress_index(result: dict[str, Any], step: str) -> int | None:
    progress = result.get("progress") if isinstance(result.get("progress"), list) else []
    for index, item in enumerate(progress):
        if isinstance(item, dict) and item.get("step") == step:
            return index
    return None


def _set_progress(result: dict[str, Any], step: str, status: str, message: str, evidence: dict[str, Any]) -> None:
    progress = result.setdefault("progress", [])
    item = {"step": step, "status": status, "message": message, "evidence": evidence}
    index = _progress_index(result, step)
    if index is None:
        progress.append(item)
    else:
        progress[index] = item


def _recompute_status(result: dict[str, Any]) -> None:
    progress = result.get("progress") if isinstance(result.get("progress"), list) else []
    statuses = [str(item.get("status") or "") for item in progress if isinstance(item, dict)]
    if any(status in {"failed", "blocked"} for status in statuses):
        result["status"] = "failed"
    elif any(status in {"queued", "running", "pending"} for status in statuses):
        result["status"] = "running"
    elif statuses and all(status in {"complete", "skipped"} for status in statuses):
        result["status"] = "complete"
    else:
        result["status"] = "planned"


def _same_run(scan: dict[str, Any], run_id: str) -> bool:
    scan_run_id = str(scan.get("run_id") or "")
    return not scan_run_id or scan_run_id == run_id


def plan_full_assessment_continuation(
    payload: dict[str, Any],
    record: dict[str, Any] | None,
    *,
    auto_continue: bool,
    desired_reports: bool | None = None,
    desired_review: bool | None = None,
    scan_loader: Callable[[str], dict[str, Any]] = get_scan,
) -> dict[str, Any]:
    """Plan safe continuation after a scanner reaches a terminal state.

    Saved run intent remains the default, but an explicit status request may upgrade a
    previously skipped report or review stage. This lets an operator repair an older run
    whose intent was accidentally downgraded by polling without re-running its scanner.
    """

    planned_payload = deepcopy(payload)
    run_id = str(planned_payload.get("run_id") or "")
    scan_id = str(planned_payload.get("scan_id") or (record or {}).get("scan_id") or "")
    request = dict((record or {}).get("request") or {})
    saved_reports = bool(request.get("build_reports", True))
    saved_review = bool(request.get("create_final_review_request", True))
    reports_requested = (
        saved_reports or bool(planned_payload.get("build_reports"))
        if desired_reports is None
        else bool(desired_reports)
    )
    review_requested = (
        saved_review or bool(planned_payload.get("create_final_review_request"))
        if desired_review is None
        else bool(desired_review)
    )
    report_id = str((record or {}).get("report_id") or "")
    approval_id = str((record or {}).get("approval_id") or "")

    scan = scan_loader(scan_id) if scan_id else {"status": "not_started", "scan_id": ""}
    scan_status = str(scan.get("status") or "unknown")
    same_run = _same_run(scan, run_id)

    planned_payload["build_reports"] = False
    planned_payload["create_final_review_request"] = False

    reason = "Automatic continuation is disabled for this refresh."
    should_continue = False
    reuse_report = False
    reuse_approval = False
    request_review_from_existing_report = False

    if auto_continue and scan_id and same_run and scan_status == "complete":
        should_continue = True
        if reports_requested and not report_id:
            planned_payload["build_reports"] = True
        elif reports_requested and report_id:
            reuse_report = True

        if review_requested and not approval_id:
            if report_id:
                request_review_from_existing_report = True
            else:
                planned_payload["create_final_review_request"] = True
        elif review_requested and approval_id:
            reuse_approval = True
        reason = "Completed same-run scanner evidence can continue into scoring, reports, and final review according to the effective run intent."
    elif not auto_continue:
        reason = "Automatic continuation was explicitly disabled."
    elif not scan_id:
        reason = "No scanner run is bound to this full-run."
    elif not same_run:
        reason = "Scanner run_id does not match this full-run; continuation is blocked."
    elif scan_status in RUNNING_SCAN_STATUSES:
        reason = "Scanner is still running; downstream steps remain pending."
    elif scan_status in TERMINAL_SCAN_STATUSES:
        reason = f"Scanner finished with non-continuable status: {scan_status}."
    else:
        reason = f"Scanner status is not continuable: {scan_status}."

    return {
        "payload": planned_payload,
        "run_id": run_id,
        "scan_id": scan_id,
        "scan": scan,
        "scan_status": scan_status,
        "same_run": same_run,
        "auto_continue": auto_continue,
        "desired_reports": reports_requested,
        "desired_review": review_requested,
        "should_continue": should_continue,
        "reuse_report": reuse_report,
        "reuse_approval": reuse_approval,
        "request_review_from_existing_report": request_review_from_existing_report,
        "report_id": report_id,
        "approval_id": approval_id,
        "reason": reason,
    }


def _reports_response(report: dict[str, Any], report_id: str) -> dict[str, Any]:
    formats = report.get("formats") if isinstance(report.get("formats"), dict) else {}
    return {
        "report_id": report.get("report_id") or report_id,
        "markdown": formats.get("markdown") or "",
        "html": formats.get("html") or "",
        "pdf_base64": "",
        "pdf_filename": "nico-assessment.pdf",
        "pdf_error": "PDF export is not stored in this Full Assessment report package path.",
    }


def apply_full_assessment_continuation(
    result: dict[str, Any],
    plan: dict[str, Any],
    *,
    store: StorageAdapter | None = None,
    review_requester: Callable[[dict[str, Any]], dict[str, Any]] = request_final_review,
) -> dict[str, Any]:
    """Reuse saved artifacts and finish approval creation without duplicating completed work."""

    active = _store(store)
    result["auto_continuation"] = {
        "enabled": bool(plan.get("auto_continue")),
        "continued": bool(plan.get("should_continue")),
        "scan_id": plan.get("scan_id") or "",
        "scanner_status": plan.get("scan_status") or "unknown",
        "same_run": bool(plan.get("same_run")),
        "desired_reports": bool(plan.get("desired_reports")),
        "desired_review": bool(plan.get("desired_review")),
        "reason": plan.get("reason") or "",
    }

    if not plan.get("should_continue"):
        return result

    report_id = str(plan.get("report_id") or "")
    if plan.get("reuse_report") and report_id:
        report = active.get("reports", report_id) or {}
        if report:
            result.setdefault("reports", {}).update(_reports_response(report, report_id))
            _set_progress(
                result,
                "reports",
                "complete",
                "Existing same-run report package was reused; no duplicate report was created.",
                {"run_id": plan.get("run_id"), "report_id": report_id, "reused": True},
            )

    approval_id = str(plan.get("approval_id") or "")
    if plan.get("reuse_approval") and approval_id:
        approval = active.get("approvals", approval_id) or {}
        if approval:
            result["approval"] = {
                "approval_id": approval.get("approval_id") or approval_id,
                "status": approval.get("status") or "pending",
                "requested_action": approval.get("requested_action") or "final_report_approval",
                "run_id": approval.get("run_id") or plan.get("run_id"),
                "report_id": approval.get("report_id") or report_id,
            }
            _set_progress(
                result,
                "approval_request",
                "complete",
                "Existing same-run final-review request was reused; no duplicate approval was created.",
                {"run_id": plan.get("run_id"), "report_id": report_id, "approval_id": approval_id, "reused": True},
            )

    if plan.get("request_review_from_existing_report") and report_id:
        review = review_requester(
            {
                "customer_id": result.get("customer_id") or "default_customer",
                "project_id": result.get("project_id") or "default_project",
                "run_id": plan.get("run_id"),
                "report_id": report_id,
                "repository": result.get("repository") or "",
                "requester": "nico-full-run-auto-continuation",
                "risk_level": "delivery_review",
                "evidence": [
                    f"Automatic continuation reused report_id={report_id} for run_id={plan.get('run_id')}.",
                    "Client delivery remains blocked until a human reviewer approves the final report.",
                ],
            }
        )
        approval = review.get("approval") if isinstance(review.get("approval"), dict) else {}
        if review.get("status") == "blocked":
            _set_progress(
                result,
                "approval_request",
                "blocked",
                "Final review request was blocked; human investigation is required.",
                {"run_id": plan.get("run_id"), "report_id": report_id},
            )
        else:
            result["approval"] = {
                "approval_id": approval.get("approval_id") or "",
                "status": approval.get("status") or review.get("status") or "pending_review",
                "requested_action": approval.get("requested_action") or "final_report_approval",
                "run_id": approval.get("run_id") or plan.get("run_id"),
                "report_id": approval.get("report_id") or report_id,
            }
            _set_progress(
                result,
                "approval_request",
                "complete",
                "Final human-review request was created from the existing same-run report package.",
                {
                    "run_id": plan.get("run_id"),
                    "report_id": report_id,
                    "approval_id": approval.get("approval_id") or "",
                },
            )

    _recompute_status(result)
    return result
