from __future__ import annotations

import base64
from typing import Any

from nico.approval_queue import create_approval, list_approvals, transition_approval
from nico.reports import get_report
from nico.storage import STORE

FINAL_REVIEW_ACTION = "final_report_approval"
FINAL_REVIEW_STATES = {"approved", "needs_more_evidence", "rejected"}
FINAL_REVIEW_TERMINAL_STATES = {"approved", "rejected"}


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


def _valid_pdf_base64(value: Any) -> bool:
    encoded = str(value or "").strip()
    if not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception:
        return False
    return decoded.startswith(b"%PDF")


def final_review_validation(approval: dict[str, Any]) -> dict[str, Any]:
    """Validate the exact run-bound Full Assessment draft before human approval."""

    run_id = str(approval.get("run_id") or "").strip()
    report_id = str(approval.get("report_id") or "").strip()
    report = _report_for_run(report_id or run_id)
    formats = report.get("formats") if isinstance(report.get("formats"), dict) else {}
    report_payload = formats.get("json") if isinstance(formats.get("json"), dict) else {}
    gate = report.get("export_truth_gate") if isinstance(report.get("export_truth_gate"), dict) else {}
    if not gate and isinstance(report_payload.get("export_truth_gate"), dict):
        gate = report_payload.get("export_truth_gate") or {}

    checks = [
        {
            "id": "report_exists",
            "passed": bool(report),
            "message": "The exact report package exists.",
        },
        {
            "id": "report_id_matches",
            "passed": bool(report and report_id and str(report.get("report_id") or "") == report_id),
            "message": "The approval is bound to the exact report ID.",
        },
        {
            "id": "run_id_matches",
            "passed": bool(report and run_id and str(report.get("run_id") or "") == run_id),
            "message": "The report package is bound to the exact Full Assessment run.",
        },
        {
            "id": "full_assessment_identity",
            "passed": str(report_payload.get("report_path") or "") == "full_run",
            "message": "The report identifies itself as a Full Assessment.",
        },
        {
            "id": "pdf_integrity",
            "passed": _valid_pdf_base64(formats.get("pdf")),
            "message": "The stored draft PDF is present and begins with a valid PDF header.",
        },
        {
            "id": "export_truth_gate_passed",
            "passed": str(gate.get("status") or "") == "passed",
            "message": "The Export Truth Gate passed without unresolved rendered-output contradictions.",
        },
    ]
    blockers = [item["message"] for item in checks if not item["passed"]]
    return {
        "status": "ready_for_human_decision" if not blockers else "blocked",
        "ready_for_approval": not blockers,
        "run_id": run_id,
        "report_id": report_id,
        "checks": checks,
        "blockers": blockers,
        "rule": "Approval is allowed only for the exact run-bound Full Assessment package with a valid draft PDF and a passed Export Truth Gate.",
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
        "review_validation": latest.get("review_validation") if latest else {},
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
        "approval_id": payload.get("approval_id") or "",
        "idempotency_key": payload.get("idempotency_key") or "",
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
    reused = bool(approval.get("idempotent_reuse"))
    approval["run_id"] = run_id
    approval["report_id"] = snapshot.get("report_id") or report_id
    approval["review_snapshot"] = snapshot
    approval["review_validation"] = final_review_validation(approval)
    STORE.put("approvals", approval["approval_id"], approval)
    audit_action = "final_review.reused" if reused else "final_review.requested"
    STORE.audit(audit_action, {"approval_id": approval["approval_id"], "run_id": run_id, "report_id": approval.get("report_id"), "idempotency_key": approval.get("idempotency_key") or ""}, customer_id=customer_id, project_id=project_id)
    response_status = "pending_review" if approval.get("status") == "pending" else "ok"
    return {
        "status": response_status,
        "approval": approval,
        "review": final_review_status(run_id, customer_id, project_id),
        "idempotent_reuse": reused,
        "idempotency_key": approval.get("idempotency_key") or "",
    }


def transition_final_review(approval_id: str, state: str, actor: str = "human_reviewer", note: str = "") -> dict[str, Any]:
    normalized_state = str(state or "").strip().lower()
    if normalized_state not in FINAL_REVIEW_STATES:
        return {"status": "blocked", "error": f"Invalid final review state: {state}"}
    item = STORE.get("approvals", approval_id)
    if not item:
        return {"status": "not_found", "approval_id": approval_id}
    if item.get("requested_action") != FINAL_REVIEW_ACTION:
        return {"status": "blocked", "error": "approval is not a final report review", "approval_id": approval_id}

    actor_name = str(actor or "").strip()
    note_text = str(note or "").strip()
    if not actor_name:
        return {"status": "blocked", "error": "A human reviewer identity is required.", "approval_id": approval_id}
    if normalized_state in {"needs_more_evidence", "rejected"} and not note_text:
        return {"status": "blocked", "error": "A review note is required when requesting more evidence or rejecting a report.", "approval_id": approval_id}

    current_state = str(item.get("status") or "pending")
    if current_state in FINAL_REVIEW_TERMINAL_STATES:
        if current_state == normalized_state:
            return {
                "status": "ok",
                "approval": item,
                "idempotent_reuse": True,
                "review": final_review_status(str(item.get("run_id") or ""), item.get("customer_id") or "default_customer", item.get("project_id") or "default_project"),
            }
        return {
            "status": "blocked",
            "error": f"Final review is already terminal with state={current_state}; create a new report and review request for a different decision.",
            "approval_id": approval_id,
        }

    validation = final_review_validation(item)
    if normalized_state == "approved" and not validation.get("ready_for_approval"):
        return {
            "status": "blocked",
            "error": "Final review approval is blocked because the exact Full Assessment package failed pre-approval validation.",
            "approval_id": approval_id,
            "review_validation": validation,
        }

    updated = transition_approval(approval_id, normalized_state, actor=actor_name, note=note_text)
    updated["review_validation"] = validation
    updated["review_decision"] = {
        "state": normalized_state,
        "actor": actor_name,
        "note": note_text,
        "decided_at": updated.get("updated_at") or "",
        "client_delivery_allowed": normalized_state == "approved",
    }
    STORE.put("approvals", approval_id, updated)
    STORE.audit(
        "final_review.transition",
        {"approval_id": approval_id, "state": normalized_state, "actor": actor_name, "run_id": updated.get("run_id") or "", "report_id": updated.get("report_id") or ""},
        customer_id=updated.get("customer_id"),
        project_id=updated.get("project_id"),
    )
    return {
        "status": "ok",
        "approval": updated,
        "idempotent_reuse": False,
        "review": final_review_status(str(updated.get("run_id") or ""), updated.get("customer_id") or "default_customer", updated.get("project_id") or "default_project"),
    }
