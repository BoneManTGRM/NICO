from __future__ import annotations

from typing import Any

from nico.approval_queue import create_approval, list_approvals, transition_approval
from nico.reports import get_report
from nico.storage import STORE

FINAL_REVIEW_ACTION = "final_report_approval"
FINAL_REVIEW_STATES = {"approved", "needs_more_evidence", "rejected"}


def _safe_score(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    return str(value)


def _report_for_run(run_id: str) -> dict[str, Any]:
    report = get_report(run_id)
    return report if isinstance(report, dict) and report.get("status") != "not_found" else {}


def _assessment_for_run(run_id: str, customer_id: str = "", project_id: str = "") -> dict[str, Any]:
    for row in STORE.list("assessment_runs", customer_id=customer_id or None, project_id=project_id or None):
        if not isinstance(row, dict):
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        candidates = {
            str(row.get("id") or ""),
            str(row.get("run_id") or ""),
            str(payload.get("run_id") or ""),
            str(payload.get("assessment_id") or ""),
            str(payload.get("generated_at") or "").replace(":", "_"),
        }
        if run_id in candidates:
            return payload
    return {}


def _payload_snapshot(run_id: str, customer_id: str, project_id: str, report_id: str = "") -> dict[str, Any]:
    report = _report_for_run(report_id or run_id)
    report_payload = (report.get("formats") or {}).get("json") if isinstance(report.get("formats"), dict) else None
    payload = report_payload if isinstance(report_payload, dict) else _assessment_for_run(run_id, customer_id, project_id)
    maturity = payload.get("maturity_signal") if isinstance(payload, dict) else {}
    readiness = payload.get("release_readiness") if isinstance(payload, dict) else {}
    acceptance = payload.get("client_acceptance") if isinstance(payload, dict) else {}
    return {
        "run_id": run_id,
        "report_id": report.get("report_id") or report_id or "",
        "repository": payload.get("repository") or payload.get("source_scope") or report.get("repository") or "",
        "maturity_level": (maturity or {}).get("level"),
        "maturity_score": (maturity or {}).get("score"),
        "release_readiness_status": (readiness or {}).get("status"),
        "acceptance_status_before_review": (acceptance or {}).get("status"),
        "generated_at": payload.get("generated_at") or report.get("created_at") or "",
    }


def final_review_status(run_id: str, customer_id: str = "default_customer", project_id: str = "default_project") -> dict[str, Any]:
    approvals = [
        item for item in list_approvals(customer_id=customer_id, project_id=project_id)
        if isinstance(item, dict)
        and item.get("requested_action") == FINAL_REVIEW_ACTION
        and (item.get("run_id") == run_id or any(str(ev).find(run_id) >= 0 for ev in item.get("evidence", []) or []))
    ]
    approvals.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    latest = approvals[0] if approvals else None
    return {
        "status": "ok",
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "review_status": latest.get("status") if latest else "missing",
        "approval_id": latest.get("approval_id") if latest else "",
        "approver": latest.get("approver") if latest else "",
        "approval_count": len(approvals),
        "approvals": approvals,
        "rule": "Final review status is sourced from same-customer/same-project final_report_approval records only.",
    }


def request_final_review(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or payload.get("report_id") or "").strip()
    if not run_id:
        return {"status": "blocked", "error": "run_id or report_id is required"}
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")
    report_id = str(payload.get("report_id") or "")
    snapshot = _payload_snapshot(run_id, customer_id, project_id, report_id)
    evidence = [
        f"Final review requested for run_id={run_id} report_id={snapshot.get('report_id') or report_id or 'unavailable'}.",
        f"Snapshot: repository={snapshot.get('repository') or 'unavailable'} score={_safe_score(snapshot.get('maturity_score'))} release_readiness={snapshot.get('release_readiness_status') or 'unavailable'}.",
    ]
    for item in payload.get("evidence") or []:
        evidence.append(str(item))
    approval = create_approval({
        "customer_id": customer_id,
        "project_id": project_id,
        "requested_action": FINAL_REVIEW_ACTION,
        "issue": "Final report review and acceptance",
        "suggested_fix_summary": "Approve final report delivery or request more evidence.",
        "evidence": evidence,
        "affected_files_or_systems": [snapshot.get("repository") or payload.get("repository") or "report"],
        "risk_level": payload.get("risk_level") or "delivery_review",
        "test_plan": payload.get("test_plan") or "Human reviewer must verify the final report, evidence, score, and unavailable-data notes before acceptance.",
        "rollback_plan": payload.get("rollback_plan") or "If not accepted, transition the final review to needs_more_evidence or rejected and rerun the report after fixes.",
        "requester": payload.get("requester") or "nico",
    })
    approval["run_id"] = run_id
    approval["report_id"] = snapshot.get("report_id") or report_id
    approval["review_snapshot"] = snapshot
    STORE.put("approvals", approval["approval_id"], approval)
    STORE.audit("final_review.requested", {"approval_id": approval["approval_id"], "run_id": run_id}, customer_id=customer_id, project_id=project_id)
    return {"status": "pending_review", "approval": approval, "review": final_review_status(run_id, customer_id, project_id)}


def transition_final_review(approval_id: str, state: str, actor: str = "human_reviewer", note: str = "") -> dict[str, Any]:
    if state not in FINAL_REVIEW_STATES:
        return {"status": "blocked", "error": f"Invalid final review state: {state}"}
    item = STORE.get("approvals", approval_id)
    if not item:
        return {"status": "not_found", "approval_id": approval_id}
    if item.get("requested_action") != FINAL_REVIEW_ACTION:
        return {"status": "blocked", "error": "approval is not a final report review", "approval_id": approval_id}
    updated = transition_approval(approval_id, state, actor=actor, note=note)
    STORE.audit("final_review.transition", {"approval_id": approval_id, "state": state, "actor": actor}, customer_id=updated.get("customer_id"), project_id=updated.get("project_id"))
    return {"status": "ok", "approval": updated}
