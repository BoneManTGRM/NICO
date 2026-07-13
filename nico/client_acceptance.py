from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from nico.approval_queue import create_approval, list_approvals, transition_approval
from nico.storage import STORE

CLIENT_ACCEPTANCE_ACTION = "client_acceptance_signoff"
FINAL_REVIEW_ACTION = "final_report_approval"
CLIENT_ACCEPTANCE_ACTIONS = {CLIENT_ACCEPTANCE_ACTION, FINAL_REVIEW_ACTION}
CLIENT_ACCEPTANCE_STATES = {"approved", "needs_more_evidence", "rejected"}
CLIENT_ACCEPTANCE_TERMINAL_STATES = {"approved", "rejected"}


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


def _matches_acceptance_action(item: dict[str, Any]) -> bool:
    return str(item.get("requested_action") or "") in CLIENT_ACCEPTANCE_ACTIONS


def _same_run(item: dict[str, Any], run_id: str) -> bool:
    if not run_id:
        return True
    if str(item.get("run_id") or "") == run_id:
        return True
    return any(str(ev).find(run_id) >= 0 for ev in item.get("evidence", []) or [])


def _approval_records(run_id: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    records = []
    for item in list_approvals(customer_id=customer_id, project_id=project_id):
        if not isinstance(item, dict) or not _matches_acceptance_action(item):
            continue
        if _same_run(item, run_id):
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


def _acceptance_identity(run_id: str, customer_id: str, project_id: str) -> tuple[str, str]:
    canonical = f"{customer_id}:{project_id}:{run_id}:{CLIENT_ACCEPTANCE_ACTION}"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"client_acceptance_{digest[:24]}", f"client-acceptance:{digest}"


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

    accepted_actions = sorted(CLIENT_ACCEPTANCE_ACTIONS)
    return {
        "status": status,
        "client_delivery_allowed": False,
        "automation_finality": "not_final",
        "rule": "NICO may prepare evidence, but client delivery is allowed only after one same-run authorized human signoff: final report approval or client acceptance signoff.",
        "minimum_approved_signoffs": 1,
        "accepted_signoff_actions": accepted_actions,
        "required_signoffs": [
            {
                "role": "authorized_human_reviewer",
                "required": True,
                "status": "pending",
                "accepted_actions": accepted_actions,
            }
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


def _apply_final_hosted_truth_gate_before_acceptance(result: dict[str, Any]) -> dict[str, Any]:
    """Force final truth/export gates onto the direct API return path."""

    if result.get("status") != "complete":
        return result
    try:
        from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate

        return apply_final_hosted_truth_gate(result)
    except Exception:  # pragma: no cover - defensive guard for report delivery
        result.setdefault("report_quality_guards", {})["final_hosted_truth_gate"] = {
            "status": "failed",
            "guardrail": "Final hosted truth gate failed before client acceptance; human review remains required.",
        }
        result["human_review_required"] = True
        result["client_ready"] = False
        return result


def attach_client_acceptance_gate(result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    output["human_review_required"] = True
    output = _apply_final_hosted_truth_gate_before_acceptance(output)
    output["client_acceptance"] = build_client_acceptance_gate(output)
    output["human_review_required"] = True
    return output


def _resolved_gate(
    gate: dict[str, Any],
    latest: dict[str, Any] | None,
    approved: list[dict[str, Any]],
) -> dict[str, Any]:
    output = deepcopy(gate) if isinstance(gate, dict) else {}
    if not output:
        return output
    signoffs = output.get("required_signoffs") if isinstance(output.get("required_signoffs"), list) else []
    if not signoffs:
        signoffs = [
            {
                "role": "authorized_human_reviewer",
                "required": True,
                "status": "pending",
                "accepted_actions": sorted(CLIENT_ACCEPTANCE_ACTIONS),
            }
        ]
        output["required_signoffs"] = signoffs

    selected = approved[0] if approved else latest
    signoff = signoffs[0] if isinstance(signoffs[0], dict) else {}
    if selected:
        signoff.update(
            {
                "status": "approved" if selected.get("status") == "approved" else str(selected.get("status") or "pending"),
                "approval_id": selected.get("approval_id") or "",
                "approver": selected.get("approver") or "",
                "action": selected.get("requested_action") or "",
            }
        )
        signoffs[0] = signoff

    if approved:
        output["status"] = "accepted"
        output["client_delivery_allowed"] = True
        output["automation_finality"] = "human_approved"
        output["human_review_required"] = False
    elif latest and str(latest.get("status") or "") in {"pending", "needs_more_evidence", "rejected"}:
        output["status"] = str(latest.get("status"))
        output["client_delivery_allowed"] = False
        output["human_review_required"] = True
    return output


def client_acceptance_status(run_id: str, customer_id: str = "default_customer", project_id: str = "default_project") -> dict[str, Any]:
    approvals = _approval_records(run_id, customer_id, project_id)
    approved = [item for item in approvals if item.get("status") == "approved"]
    latest = approved[0] if approved else approvals[0] if approvals else None
    assessment = _assessment_for_run(run_id, customer_id, project_id)
    gate = assessment.get("client_acceptance") if isinstance(assessment.get("client_acceptance"), dict) else build_client_acceptance_gate(assessment) if assessment else {}
    gate = _resolved_gate(gate, latest, approved)
    accepted = bool(approved)
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
        "approved_count": len(approved),
        "total_approval_history_count": len(approvals),
        "total_approved_history_count": len(approved),
        "accepted_actions": sorted(CLIENT_ACCEPTANCE_ACTIONS),
        "client_acceptance": gate,
        "approvals": approvals,
        "rule": "Client delivery is allowed only after one same-run final_report_approval or client_acceptance_signoff is approved.",
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

    default_approval_id, default_idempotency_key = _acceptance_identity(run_id, customer_id, project_id)
    approval_id = str(payload.get("approval_id") or default_approval_id)
    idempotency_key = str(payload.get("idempotency_key") or default_idempotency_key)
    try:
        approval = create_approval(
            {
                "approval_id": approval_id,
                "idempotency_key": idempotency_key,
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
            }
        )
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc), "approval_id": approval_id}

    reused = bool(approval.get("idempotent_reuse"))
    approval["run_id"] = run_id
    approval["client_acceptance_snapshot"] = gate
    approval["acceptance_validation"] = {
        "status": "ready_for_human_decision" if gate and not gate.get("blockers") else "blocked",
        "ready_for_approval": bool(gate) and not bool(gate.get("blockers")),
        "blockers": list(gate.get("blockers") or []) if isinstance(gate, dict) else ["Client acceptance evidence gate is unavailable."],
        "evidence_bundle_hash": gate.get("evidence_bundle_hash") if isinstance(gate, dict) else "",
    }
    STORE.put("approvals", approval["approval_id"], approval)
    STORE.audit(
        "client_acceptance.reused" if reused else "client_acceptance.requested",
        {"approval_id": approval["approval_id"], "run_id": run_id, "idempotency_key": idempotency_key},
        customer_id=customer_id,
        project_id=project_id,
    )
    acceptance = client_acceptance_status(run_id, customer_id, project_id)
    response_status = "accepted" if acceptance.get("client_delivery_allowed") else "pending_acceptance" if approval.get("status") == "pending" else "ok"
    return {
        "status": response_status,
        "approval": approval,
        "acceptance": acceptance,
        "idempotent_reuse": reused,
        "idempotency_key": idempotency_key,
    }


def transition_client_acceptance(approval_id: str, state: str, actor: str = "human_reviewer", note: str = "") -> dict[str, Any]:
    normalized = "approved" if state == "accepted" else str(state or "").strip().lower()
    if normalized not in CLIENT_ACCEPTANCE_STATES:
        return {"status": "blocked", "error": f"Invalid client acceptance state: {state}"}
    item = STORE.get("approvals", approval_id)
    if not item:
        return {"status": "not_found", "approval_id": approval_id}
    if item.get("requested_action") not in CLIENT_ACCEPTANCE_ACTIONS:
        return {"status": "blocked", "error": "approval is not a client acceptance or final review signoff", "approval_id": approval_id}

    actor_name = " ".join(str(actor or "").split())[:160]
    note_text = str(note or "").strip()
    if not actor_name:
        return {"status": "blocked", "error": "A human reviewer identity is required.", "approval_id": approval_id}
    if normalized in {"needs_more_evidence", "rejected"} and not note_text:
        return {"status": "blocked", "error": "A review note is required when requesting more evidence or rejecting delivery.", "approval_id": approval_id}

    current = str(item.get("status") or "pending")
    if current in CLIENT_ACCEPTANCE_TERMINAL_STATES:
        if current == normalized:
            run_id = str(item.get("run_id") or "")
            return {
                "status": "ok",
                "approval": item,
                "acceptance": client_acceptance_status(
                    run_id,
                    item.get("customer_id") or "default_customer",
                    item.get("project_id") or "default_project",
                ) if run_id else {},
                "idempotent_reuse": True,
            }
        return {
            "status": "blocked",
            "error": f"Client acceptance is already terminal with state={current}; create a new run after evidence changes.",
            "approval_id": approval_id,
        }

    run_id = str(item.get("run_id") or "")
    customer_id = str(item.get("customer_id") or "default_customer")
    project_id = str(item.get("project_id") or "default_project")
    assessment = _assessment_for_run(run_id, customer_id, project_id) if run_id else {}
    gate = assessment.get("client_acceptance") if isinstance(assessment.get("client_acceptance"), dict) else build_client_acceptance_gate(assessment) if assessment else {}
    validation = {
        "status": "ready_for_human_decision" if gate and not gate.get("blockers") else "blocked",
        "ready_for_approval": bool(gate) and not bool(gate.get("blockers")),
        "blockers": list(gate.get("blockers") or []) if isinstance(gate, dict) else ["Client acceptance evidence gate is unavailable."],
        "evidence_bundle_hash": gate.get("evidence_bundle_hash") if isinstance(gate, dict) else "",
    }
    if normalized == "approved" and not validation["ready_for_approval"]:
        return {
            "status": "blocked",
            "error": "Client acceptance is blocked because the exact run is missing required evidence or artifact hashes.",
            "approval_id": approval_id,
            "acceptance_validation": validation,
        }

    updated = transition_approval(approval_id, normalized, actor=actor_name, note=note_text)
    updated["acceptance_validation"] = validation
    STORE.put("approvals", approval_id, updated)
    STORE.audit(
        "client_acceptance.transition",
        {"approval_id": approval_id, "state": normalized, "actor": actor_name, "run_id": run_id},
        customer_id=customer_id,
        project_id=project_id,
    )
    return {
        "status": "ok",
        "approval": updated,
        "acceptance": client_acceptance_status(run_id, customer_id, project_id) if run_id else {},
        "idempotent_reuse": False,
    }
