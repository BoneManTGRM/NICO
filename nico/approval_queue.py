from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.storage import STORE

VALID_STATES = {"pending", "approved", "rejected", "needs_more_evidence", "expired", "executed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_approval(payload: dict[str, Any]) -> dict[str, Any]:
    approval_id = f"approval_{uuid4().hex[:16]}"
    item = {
        "approval_id": approval_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "status": "pending",
        "requested_action": payload.get("requested_action") or "draft_pr",
        "issue": payload.get("issue", ""),
        "root_cause_hypothesis": payload.get("root_cause_hypothesis", ""),
        "confidence": payload.get("confidence", ""),
        "suggested_fix_summary": payload.get("suggested_fix_summary", ""),
        "patch_steps": payload.get("patch_steps") or [],
        "patch_prompt": payload.get("patch_prompt", ""),
        "evidence": payload.get("evidence") or [],
        "affected_files_or_systems": payload.get("affected_files_or_systems") or [],
        "risk_level": payload.get("risk_level") or "unknown",
        "test_plan": payload.get("test_plan") or "Human reviewer must define or approve the test plan before execution.",
        "rollback_plan": payload.get("rollback_plan") or "Human reviewer must define or approve the rollback plan before execution.",
        "requester": payload.get("requester") or "nico",
        "approver": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "audit_log": [],
    }
    item["audit_log"].append({"timestamp": now_iso(), "action": "created", "actor": item["requester"]})
    STORE.put("approvals", approval_id, item)
    STORE.audit("approval.created", {"approval_id": approval_id, "requested_action": item["requested_action"]}, customer_id=item["customer_id"], project_id=item["project_id"])
    return item


def list_approvals(customer_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
    return STORE.list("approvals", customer_id=customer_id, project_id=project_id)


def transition_approval(approval_id: str, state: str, actor: str = "human_reviewer", note: str = "") -> dict[str, Any]:
    if state not in VALID_STATES:
        return {"status": "blocked", "error": f"Invalid approval state: {state}"}
    item = STORE.get("approvals", approval_id)
    if not item:
        return {"status": "not_found", "approval_id": approval_id}
    item["status"] = state
    item["updated_at"] = now_iso()
    if state == "approved":
        item["approver"] = actor
    item.setdefault("audit_log", []).append({"timestamp": now_iso(), "action": state, "actor": actor, "note": note})
    STORE.put("approvals", approval_id, item)
    STORE.audit("approval.transition", {"approval_id": approval_id, "state": state, "actor": actor}, customer_id=item.get("customer_id"), project_id=item.get("project_id"))
    return item


def draft_pr_request(payload: dict[str, Any]) -> dict[str, Any]:
    approval_id = payload.get("approval_id") or ""
    item = STORE.get("approvals", approval_id)
    if not item:
        return {"status": "blocked", "error": "approval item not found", "approval_id": approval_id}
    if item.get("status") != "approved":
        return {"status": "blocked", "error": "draft PR creation requires approved approval item", "approval_status": item.get("status")}
    record_id = f"draftpr_{uuid4().hex[:16]}"
    record = {
        "draft_pr_id": record_id,
        "customer_id": item.get("customer_id"),
        "project_id": item.get("project_id"),
        "approval_id": approval_id,
        "status": "unavailable",
        "repository": payload.get("repository"),
        "branch_name": payload.get("branch_name") or f"nico/proposed-repair-{record_id[-6:]}",
        "title": payload.get("title") or "NICO proposed repair",
        "body": payload.get("body") or "Draft PR creation is approval-gated. GitHub write integration is not enabled in this safe MVP.",
        "evidence": item.get("evidence", []),
        "test_plan": item.get("test_plan"),
        "rollback_plan": item.get("rollback_plan"),
        "unavailable_data_notes": ["GitHub write integration is not enabled yet. No branch, commit, or PR was created."],
        "created_at": now_iso(),
    }
    STORE.put("draft_pr_records", record_id, record)
    STORE.audit("draft_pr.requested", {"draft_pr_id": record_id, "approval_id": approval_id}, customer_id=record.get("customer_id"), project_id=record.get("project_id"))
    return record
