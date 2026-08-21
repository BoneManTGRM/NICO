from __future__ import annotations

from typing import Any

from nico.approved_delivery_verification import approved_delivery_metadata, verify_approved_delivery_artifact
from nico.reports import get_report
from nico.storage import STORE

_PLACEHOLDER_CUSTOMER_ID = "default_customer"
_PLACEHOLDER_PROJECT_ID = "default_project"


def _required_scope(customer_id: Any, project_id: Any) -> tuple[str, str] | None:
    customer = str(customer_id or "").strip()
    project = str(project_id or "").strip()
    if (
        not customer
        or not project
        or customer == _PLACEHOLDER_CUSTOMER_ID
        or project == _PLACEHOLDER_PROJECT_ID
    ):
        return None
    return customer, project


def _scope_blocked(run_id: str, error: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "verified": False,
        "run_id": run_id,
        "client_delivery_allowed": False,
        "human_review_required": True,
        "client_ready": False,
        "error": error,
    }


def approved_delivery_status(
    run_id: str,
    customer_id: str = "",
    project_id: str = "",
    *,
    include_pdf: bool = False,
) -> dict[str, Any]:
    """Recover and reverify a persisted approved-delivery artifact by run or report ID."""

    resolved_id = str(run_id or "").strip()
    if not resolved_id:
        return {
            "status": "blocked",
            "verified": False,
            "client_delivery_allowed": False,
            "human_review_required": True,
            "client_ready": False,
            "error": "run_id or report_id is required",
        }

    requested_scope = _required_scope(customer_id, project_id)
    if requested_scope is None:
        return _scope_blocked(
            resolved_id,
            "Explicit non-placeholder customer_id and project_id are required for approved delivery.",
        )
    customer_id, project_id = requested_scope

    report = get_report(resolved_id)
    if not isinstance(report, dict) or report.get("status") == "not_found":
        return {
            "status": "not_found",
            "verified": False,
            "run_id": resolved_id,
            "client_delivery_allowed": False,
            "human_review_required": True,
            "client_ready": False,
        }

    stored_report_scope = _required_scope(report.get("customer_id"), report.get("project_id"))
    if stored_report_scope is None:
        return _scope_blocked(
            str(report.get("run_id") or resolved_id),
            "The stored report package is missing mandatory customer/project identity.",
        )
    if stored_report_scope != requested_scope:
        return {
            **_scope_blocked(
                str(report.get("run_id") or resolved_id),
                "The requested customer/project scope does not match the stored report package.",
            ),
            "report_id": str(report.get("report_id") or ""),
        }

    artifact = report.get("approved_delivery") if isinstance(report.get("approved_delivery"), dict) else {}
    if not artifact:
        return {
            "status": "missing",
            "verified": False,
            "run_id": str(report.get("run_id") or resolved_id),
            "report_id": str(report.get("report_id") or ""),
            "client_delivery_allowed": False,
            "human_review_required": True,
            "client_ready": False,
            "message": "No approved-delivery artifact exists for this Comprehensive report.",
        }

    approval_id = str(artifact.get("approval_id") or "")
    approval = STORE.get("approvals", approval_id) if approval_id else None
    approval_value = approval if isinstance(approval, dict) else {}
    if approval_value:
        stored_approval_scope = _required_scope(
            approval_value.get("customer_id"),
            approval_value.get("project_id"),
        )
        if stored_approval_scope is None:
            return {
                **_scope_blocked(
                    str(report.get("run_id") or resolved_id),
                    "The stored approval record is missing mandatory customer/project identity.",
                ),
                "report_id": str(report.get("report_id") or ""),
                "approval_id": approval_id,
            }
        if stored_approval_scope != requested_scope:
            return {
                **_scope_blocked(
                    str(report.get("run_id") or resolved_id),
                    "The requested customer/project scope does not match the stored approval record.",
                ),
                "report_id": str(report.get("report_id") or ""),
                "approval_id": approval_id,
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
        "customer_id": stored_report_scope[0],
        "project_id": stored_report_scope[1],
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
    """Attach persisted approved-delivery truth to a Comprehensive response."""

    if not isinstance(result, dict):
        return result
    run_id = str(result.get("run_id") or "").strip()
    customer_id = str(result.get("customer_id") or "").strip()
    project_id = str(result.get("project_id") or "").strip()
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
        "error": status.get("error") or "",
    }
    if not status.get("verified"):
        result["client_ready"] = False
        result["client_delivery_allowed"] = False
        result["human_review_required"] = True
        result["client_delivery_status"] = "Client Delivery Blocked"
        result["delivery_verdict"] = "blocked"
        result.pop("approved_delivery", None)
        reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
        if reports:
            reports["client_delivery_allowed"] = False
            reports["human_review_required"] = True
            reports.pop("approved_delivery", None)
        return result

    delivery = status.get("approved_delivery") if isinstance(status.get("approved_delivery"), dict) else {}
    approval = status.get("approval") if isinstance(status.get("approval"), dict) else {}
    result["approved_delivery"] = delivery
    if approval:
        existing_approval = result.get("approval") if isinstance(result.get("approval"), dict) else {}
        result["approval"] = {**existing_approval, **approval}
    result["client_ready"] = True
    result["client_delivery_allowed"] = True
    result["human_review_required"] = False
    result["client_delivery_status"] = "Approved for Client Delivery"
    result["delivery_verdict"] = "approved"
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    if reports:
        reports["client_delivery_allowed"] = True
        reports["human_review_required"] = False
        reports["approved_delivery"] = delivery
    return result
