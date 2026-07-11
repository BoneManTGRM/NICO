from __future__ import annotations

from typing import Any

from nico.approved_delivery_verification import approved_delivery_metadata, verify_approved_delivery_artifact
from nico.reports import get_report
from nico.storage import STORE


def _scope_matches(value: dict[str, Any], customer_id: str, project_id: str) -> bool:
    return (
        str(value.get("customer_id") or "default_customer") == str(customer_id or "default_customer")
        and str(value.get("project_id") or "default_project") == str(project_id or "default_project")
    )


def approved_delivery_status(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    *,
    include_pdf: bool = False,
) -> dict[str, Any]:
    """Recover and reverify a persisted approved-delivery artifact by run or report ID."""

    resolved_id = str(run_id or "").strip()
    if not resolved_id:
        return {"status": "blocked", "verified": False, "error": "run_id or report_id is required"}

    report = get_report(resolved_id)
    if not isinstance(report, dict) or report.get("status") == "not_found":
        return {"status": "not_found", "verified": False, "run_id": resolved_id}
    if not _scope_matches(report, customer_id, project_id):
        return {
            "status": "blocked",
            "verified": False,
            "run_id": str(report.get("run_id") or resolved_id),
            "report_id": str(report.get("report_id") or ""),
            "error": "The requested customer/project scope does not match the stored report package.",
        }

    artifact = report.get("approved_delivery") if isinstance(report.get("approved_delivery"), dict) else {}
    if not artifact:
        return {
            "status": "missing",
            "verified": False,
            "run_id": str(report.get("run_id") or resolved_id),
            "report_id": str(report.get("report_id") or ""),
            "client_delivery_allowed": False,
            "message": "No approved-delivery artifact exists for this Full Assessment report.",
        }

    approval_id = str(artifact.get("approval_id") or "")
    approval = STORE.get("approvals", approval_id) if approval_id else None
    approval_value = approval if isinstance(approval, dict) else {}
    if approval_value and not _scope_matches(approval_value, customer_id, project_id):
        return {
            "status": "blocked",
            "verified": False,
            "run_id": str(report.get("run_id") or resolved_id),
            "report_id": str(report.get("report_id") or ""),
            "approval_id": approval_id,
            "error": "The requested customer/project scope does not match the stored approval record.",
        }

    verification = verify_approved_delivery_artifact(report, approval_value)
    verified = bool(verification.get("verified"))
    delivery = approved_delivery_metadata(artifact, include_pdf=include_pdf and verified)
    delivery["client_delivery_allowed"] = verified
    return {
        "status": "verified" if verified else "blocked",
        "verified": verified,
        "run_id": str(report.get("run_id") or resolved_id),
        "report_id": str(report.get("report_id") or ""),
        "approval_id": approval_id,
        "customer_id": str(report.get("customer_id") or "default_customer"),
        "project_id": str(report.get("project_id") or "default_project"),
        "client_delivery_allowed": verified,
        "human_review_required": not verified,
        "client_ready": verified,
        "approved_delivery": delivery,
        "approval": {
            "approval_id": approval_value.get("approval_id") or approval_id,
            "status": approval_value.get("status") or "missing",
            "requested_action": approval_value.get("requested_action") or "",
            "run_id": approval_value.get("run_id") or "",
            "report_id": approval_value.get("report_id") or "",
            "approver": approval_value.get("approver") or "",
            "review_decision": approval_value.get("review_decision") or {},
            "approved_delivery": approval_value.get("approved_delivery") or {},
        },
        "verification": verification,
    }


def attach_verified_approved_delivery(result: dict[str, Any], *, include_pdf: bool = True) -> dict[str, Any]:
    """Attach persisted approved-delivery truth to a Full Assessment response."""

    if not isinstance(result, dict):
        return result
    run_id = str(result.get("run_id") or "").strip()
    if not run_id:
        return result
    customer_id = str(result.get("customer_id") or "default_customer")
    project_id = str(result.get("project_id") or "default_project")
    status = approved_delivery_status(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        include_pdf=include_pdf,
    )
    result["approved_delivery_recovery"] = {
        "status": status.get("status") or "missing",
        "verified": bool(status.get("verified")),
        "verification": status.get("verification") or {},
    }
    if not status.get("verified"):
        return result

    delivery = status.get("approved_delivery") if isinstance(status.get("approved_delivery"), dict) else {}
    approval = status.get("approval") if isinstance(status.get("approval"), dict) else {}
    result["approved_delivery"] = delivery
    if approval:
        existing_approval = result.get("approval") if isinstance(result.get("approval"), dict) else {}
        result["approval"] = {**existing_approval, **approval}
    result["client_ready"] = True
    result["human_review_required"] = False
    result["client_delivery_status"] = "Approved for Client Delivery"
    result["delivery_verdict"] = "approved"
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    if reports:
        reports["client_delivery_allowed"] = True
        reports["human_review_required"] = False
        reports["approved_delivery"] = delivery
    return result
