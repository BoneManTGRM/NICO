from __future__ import annotations

from typing import Any

from nico.approval_queue import list_approvals

ACCEPTANCE_ACTIONS = {
    "client_acceptance",
    "client_acceptance_signoff",
    "client_report_acceptance",
    "final_report_approval",
    "human_review_acceptance",
    "report_approval",
}


def _project_id(result: dict[str, Any]) -> str:
    return str(result.get("project_id") or result.get("project", {}).get("project_id") or "default_project")


def _customer_id(result: dict[str, Any]) -> str:
    return str(result.get("customer_id") or result.get("customer", {}).get("customer_id") or "default_customer")


def _matches_acceptance_action(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return normalized in ACCEPTANCE_ACTIONS or ("accept" in normalized and "report" in normalized)


def _approval_note(item: dict[str, Any]) -> str:
    audit_log = item.get("audit_log") or []
    if isinstance(audit_log, list):
        for event in reversed(audit_log):
            if not isinstance(event, dict):
                continue
            if event.get("action") == "approved" and event.get("note"):
                return str(event.get("note"))
    return ""


def _find_section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next((item for item in result.get("sections", []) or [] if isinstance(item, dict) and item.get("id") == section_id), None)


def _acceptance_section(evidence: dict[str, Any]) -> dict[str, Any]:
    accepted = evidence.get("status") == "accepted"
    return {
        "id": "client_acceptance",
        "label": "Client / Human Acceptance",
        "score": 96 if accepted else 0,
        "status": "green" if accepted else "gray",
        "summary": (
            "Final report acceptance is supported by an approved same-project review or client-acceptance record."
            if accepted
            else "Final report acceptance is not scored until an approved same-project review record exists."
        ),
        "evidence": list(evidence.get("notes") or []),
        "findings": [] if accepted else ["Client/human acceptance evidence is unavailable for final delivery scoring."],
        "unavailable": [] if accepted else ["No approved final report/client acceptance approval record was found for this project."],
    }


def acceptance_evidence(result: dict[str, Any]) -> dict[str, Any]:
    project_id = _project_id(result)
    customer_id = _customer_id(result)
    run_id = str(result.get("run_id") or result.get("assessment_id") or "")
    approvals = list_approvals(customer_id=customer_id, project_id=project_id)
    approved = []
    pending = []
    for item in approvals:
        if not isinstance(item, dict):
            continue
        if not _matches_acceptance_action(item.get("requested_action")):
            continue
        # Prefer same-run approval records when run_id exists, but keep the legacy
        # same-project behavior for older records that did not store a run_id.
        item_run_id = str(item.get("run_id") or "")
        evidence_text = "\n".join(str(ev) for ev in item.get("evidence", []) or [])
        if run_id and item_run_id and item_run_id != run_id and run_id not in evidence_text:
            continue
        if item.get("status") == "approved":
            approved.append(item)
        else:
            pending.append(item)
    approved.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    latest = approved[0] if approved else None
    status = "accepted" if latest else "missing"
    notes = []
    if latest:
        evidence_count = len(latest.get("evidence") or [])
        note = _approval_note(latest)
        action = latest.get("requested_action") or "acceptance"
        notes.append(
            f"Client/human acceptance evidence: approved {action} record {latest.get('approval_id')} by {latest.get('approver') or 'human_reviewer'}; evidence items={evidence_count}."
        )
        if latest.get("run_id"):
            notes.append(f"Acceptance run binding: run_id={latest.get('run_id')}.")
        if note:
            notes.append(f"Acceptance reviewer note: {note[:240]}")
    else:
        notes.append(
            "Client/human acceptance evidence unavailable: no approved final report/client acceptance approval record was found for this project."
        )
    return {
        "status": status,
        "project_id": project_id,
        "customer_id": customer_id,
        "run_id": run_id,
        "approved_count": len(approved),
        "pending_count": len(pending),
        "latest_approval_id": latest.get("approval_id") if latest else "",
        "approver": latest.get("approver") if latest else "",
        "approved_at": latest.get("updated_at") if latest else "",
        "notes": notes,
        "rule": "Client acceptance is credited only from an approved report/client-acceptance approval record for the same customer and project, preferring same-run records when run_id exists.",
    }


def apply_client_acceptance_evidence(result: dict[str, Any]) -> dict[str, Any]:
    evidence = acceptance_evidence(result)
    result["client_acceptance"] = evidence
    sections = result.setdefault("sections", [])
    acceptance = _find_section(result, "client_acceptance")
    replacement = _acceptance_section(evidence)
    if acceptance is None:
        sections.append(replacement)
    else:
        acceptance.update(replacement)
    velocity = _find_section(result, "velocity_complexity")
    if velocity is None:
        return result
    velocity.setdefault("evidence", [])
    for note in evidence.get("notes", []):
        if note not in velocity["evidence"]:
            velocity["evidence"].append(note)
    project_trend = result.get("project_trend_evidence") or {}
    release_ready = (result.get("release_readiness") or {}).get("status") == "provisionally_ready_for_human_review"
    if evidence.get("status") == "accepted" and release_ready and project_trend.get("non_regressing"):
        velocity["score"] = max(int(velocity.get("score") or 0), 96)
        velocity["status"] = "green"
        velocity["summary"] = "Work-vs-expected signal uses velocity, PR traceability, source footprint, release-readiness evidence, retained non-regressing project history, and approved client/human acceptance evidence."
        extra = "Approved client/human acceptance evidence supports final Work-vs-Expected readiness; NICO still keeps final delivery human-review-bound."
        if extra not in velocity["evidence"]:
            velocity["evidence"].append(extra)
    return result
