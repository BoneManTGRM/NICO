from __future__ import annotations

from typing import Any

from nico.approval_queue import create_approval, list_approvals, transition_approval
from nico.storage import STORE

CLIENT_ACCEPTANCE_ACTION = "client_acceptance_signoff"
CLIENT_ACCEPTANCE_STATES = {"approved", "needs_more_evidence", "rejected"}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _artifact_available(bundle: dict[str, Any], name: str) -> bool:
    artifacts = bundle.get("artifacts") if isinstance(bundle.get("artifacts"), dict) else {}
    item = artifacts.get(name) if isinstance(artifacts.get(name), dict) else {}
    return bool(item.get("available") and item.get("sha256"))


def _bundle(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("evidence_artifact_bundle")
    return value if isinstance(value, dict) else {}


def _unavailable_inventory(result: dict[str, Any]) -> list[dict[str, Any]]:
    bundle = _bundle(result)
    inventory = bundle.get("unavailable_inventory") if isinstance(bundle.get("unavailable_inventory"), list) else []
    if inventory:
        return [item if isinstance(item, dict) else {"scope": "unknown", "note": str(item)} for item in inventory]
    rows: list[dict[str, Any]] = []
    for section in _safe_list(result.get("sections")):
        if not isinstance(section, dict):
            continue
        for item in _safe_list(section.get("unavailable")):
            rows.append({"scope": section.get("label") or section.get("id") or "section", "note": str(item)})
    for item in _safe_list(result.get("unavailable_data_notes")):
        rows.append({"scope": "global", "note": str(item)})
    return rows


def _approval_records(run_id: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    records = []
    for item in list_approvals(customer_id=customer_id, project_id=project_id):
        if not isinstance(item, dict) or item.get("requested_action") != CLIENT_ACCEPTANCE_ACTION:
            continue
        if item.get("run_id") == run_id or any(str(ev).find(run_id) >= 0 for ev in item.get("evidence", []) or []):
            records.append(item)
    records.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return records


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


def build_client_acceptance_gate(result: dict[str, Any]) -> dict[str, Any]:
    bundle = _bundle(result)
    findings = _safe_list(result.get("findings"))
    unavailable = _unavailable_inventory(result)
    blockers: list[str] = []
    checklist: list[dict[str, Any]] = []

    checks = [
        ("evidence_bundle_present", bool(bundle.get("bundle_hash")), "Evidence bundle with bundle hash exists."),
        ("markdown_hash_present", _artifact_available(bundle, "markdown"), "Markdown report hash exists."),
        ("html_hash_present", _artifact_available(bundle, "html"), "HTML report hash exists."),
        ("raw_evidence_hash_present", _artifact_available(bundle, "raw_evidence_json"), "Raw evidence JSON hash exists."),
        ("unavailable_inventory_present", _artifact_available(bundle, "unavailable_inventory_json"), "Unavailable-data inventory hash exists."),
        ("sections_present", bool(_safe_list(result.get("sections"))), "Scored report sections exist."),
        ("human_review_required", bool(result.get("human_review_required", True)), "Human review is explicitly required."),
    ]
    for key, passed, label in checks:
        checklist.append({"id": key, "passed": bool(passed), "label": label})
        if not passed:
            blockers.append(label)

    if blockers:
        status = "blocked_missing_evidence"
    elif unavailable or findings:
        status = "ready_for_human_signoff_with_disclosures"
    else:
        status = "ready_for_human_signoff"

    return {
        "status": status,
        "client_delivery_allowed": False,
        "automation_finality": "not_final",
        "rule": "NICO may prepare evidence, but client delivery is not accepted until required human signoffs are approved.",
        "required_signoffs": [
            {"role": "technical_reviewer", "required": True, "status": "pending"},
            {"role": "client_or_authorized_representative", "required": True, "status": "pending"},
        ],
        "checklist": checklist,
        "blockers": blockers,
        "disclosures": {
            "unavailable_count": len(unavailable),
            "finding_count": len(findings),
            "unavailable_inventory": unavailable[:50],
            "findings": [str(item) for item in findings[:50]],
        },
        "evidence_bundle_hash": bundle.get("bundle_hash") or "",
        "human_review_required": True,
    }


def attach_client_acceptance_gate(result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    output["client_acceptance"] = build_client_acceptance_gate(output)
    output["human_review_required"] = True
    return output


def client_acceptance_status(run_id: str, customer_id: str = "default_customer", project_id: str = "default_project") -> dict[str, Any]:
    approvals = _approval_records(run_id, customer_id, project_id)
    latest = approvals[0] if approvals else None
    assessment = _assessment_for_run(run_id, customer_id, project_id)
    gate = assessment.get("client_acceptance") if isinstance(assessment.get("client_acceptance"), dict) else build_client_acceptance_gate(assessment) if assessment else {}
    accepted = bool(latest and latest.get("status") == "approved")
    status = "accepted" if accepted else latest.get("status") if latest else gate.get("status", "missing")
    return {
        "status": "ok",
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "acceptance_status": status,
        "client_delivery_allowed": accepted,
        "approval_id": latest.get("approval_id") if latest else "",
        "approver": latest.get("approver") if latest else "",
        "approval_count": len(approvals),
        "client_acceptance": gate,
        "approvals": approvals,
        "rule": "Client delivery is allowed only after client_acceptance_signoff is approved.",
    }


def request_client_acceptance(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or payload.get("report_id") or "").strip()
    if not run_id:
        return {"status": "blocked", "error": "run_id or report_id is required"}
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")
    assessment = _assessment_for_run(run_id, customer_id, project_id)
    gate = assessment.get("client_acceptance") if isinstance(assessment.get("client_acceptance"), dict) else build_client_acceptance_gate(assessment) if assessment else {}
    evidence = [
        f"Client acceptance requested for run_id={run_id}.",
        f"Acceptance gate status={gate.get('status', 'unavailable')} bundle_hash={gate.get('evidence_bundle_hash', 'unavailable')}.",
        f"Disclosures: unavailable={gate.get('disclosures', {}).get('unavailable_count', 0)} findings={gate.get('disclosures', {}).get('finding_count', 0)}.",
    ]
    for item in payload.get("evidence") or []:
        evidence.append(str(item))
    approval = create_approval({
        "customer_id": customer_id,
        "project_id": project_id,
        "requested_action": CLIENT_ACCEPTANCE_ACTION,
        "issue": "Client acceptance and report delivery signoff",
        "suggested_fix_summary": "Approve report delivery, request more evidence, or reject delivery.",
        "evidence": evidence,
        "affected_files_or_systems": [assessment.get("repository") or payload.get("repository") or "report"],
        "risk_level": payload.get("risk_level") or "client_delivery_review",
        "test_plan": payload.get("test_plan") or "Human reviewer must verify report content, evidence bundle hashes, findings, unavailable-data inventory, and client delivery notes.",
        "rollback_plan": payload.get("rollback_plan") or "If not accepted, transition to needs_more_evidence or rejected and regenerate the report after fixes.",
        "requester": payload.get("requester") or "nico",
    })
    approval["run_id"] = run_id
    approval["client_acceptance_snapshot"] = gate
    STORE.put("approvals", approval["approval_id"], approval)
    STORE.audit("client_acceptance.requested", {"approval_id": approval["approval_id"], "run_id": run_id}, customer_id=customer_id, project_id=project_id)
    return {"status": "pending_acceptance", "approval": approval, "acceptance": client_acceptance_status(run_id, customer_id, project_id)}


def transition_client_acceptance(approval_id: str, state: str, actor: str = "human_reviewer", note: str = "") -> dict[str, Any]:
    normalized = "approved" if state == "accepted" else state
    if normalized not in CLIENT_ACCEPTANCE_STATES:
        return {"status": "blocked", "error": f"Invalid client acceptance state: {state}"}
    item = STORE.get("approvals", approval_id)
    if not item:
        return {"status": "not_found", "approval_id": approval_id}
    if item.get("requested_action") != CLIENT_ACCEPTANCE_ACTION:
        return {"status": "blocked", "error": "approval is not a client acceptance signoff", "approval_id": approval_id}
    updated = transition_approval(approval_id, normalized, actor=actor, note=note)
    STORE.audit("client_acceptance.transition", {"approval_id": approval_id, "state": normalized, "actor": actor}, customer_id=updated.get("customer_id"), project_id=updated.get("project_id"))
    run_id = str(updated.get("run_id") or "")
    return {"status": "ok", "approval": updated, "acceptance": client_acceptance_status(run_id, updated.get("customer_id") or "default_customer", updated.get("project_id") or "default_project") if run_id else {}}
