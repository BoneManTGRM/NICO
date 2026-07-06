from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.approval_queue import create_approval
from nico.storage import STORE


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


REPAIR_QUALITY_CHECKLIST = [
    "Evidence is attached or cited.",
    "Root cause is stated as a hypothesis unless fully verified.",
    "Affected files or systems are listed.",
    "Proposed change is minimal and reversible.",
    "Test plan is specific.",
    "Rollback plan is specific.",
    "Risk level is stated.",
    "Human approval is required before draft PR creation.",
]


def severity_from_text(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["production down", "data loss", "critical", "payment broken"]):
        return "high"
    if any(word in lower for word in ["failing", "error", "broken", "timeout", "missing dependency"]):
        return "medium"
    return "low"


def repair_strategy(issue: str) -> dict[str, str]:
    lower = issue.lower()
    if "missing dependency" in lower or "module not found" in lower or "requires" in lower:
        return {
            "strategy": "dependency_fix",
            "summary": "Add or pin the missing runtime/test dependency, then rerun the smallest failing test first.",
            "test_plan": "Run dependency install, compile affected modules, then run the failing test file and full test suite.",
            "rollback_plan": "Remove the dependency change and revert any related import or endpoint changes.",
        }
    if "type" in lower or "validation" in lower:
        return {
            "strategy": "interface_contract_fix",
            "summary": "Tighten request/response typing and add regression tests around the failing contract.",
            "test_plan": "Run unit tests for the affected endpoint or module plus schema validation tests.",
            "rollback_plan": "Revert the schema or typing change and restore the previous contract.",
        }
    if "timeout" in lower or "slow" in lower:
        return {
            "strategy": "timeout_or_workload_fix",
            "summary": "Move long-running work to a background job and return a job ID with status polling.",
            "test_plan": "Run worker tests, status endpoint tests, and a bounded timeout test.",
            "rollback_plan": "Disable the worker path and return the prior synchronous behavior if safe.",
        }
    return {
        "strategy": "evidence_first_fix",
        "summary": "Collect the failing evidence, isolate the smallest reproducible case, then propose a minimal patch.",
        "test_plan": "Run the smallest relevant regression test, then the full test suite.",
        "rollback_plan": "Revert the patch branch and leave the original code unchanged.",
    }


def suggest_repair(payload: dict[str, Any]) -> dict[str, Any]:
    issue = payload.get("issue") or payload.get("finding") or "Unspecified issue"
    evidence = payload.get("evidence") or []
    affected_files = payload.get("affected_files") or []
    strategy = repair_strategy(issue)
    risk_level = payload.get("risk_level") or severity_from_text(issue)
    suggestion_id = f"repair_{uuid4().hex[:16]}"
    result = {
        "status": "complete",
        "suggestion_id": suggestion_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "issue": issue,
        "risk_level": risk_level,
        "strategy": strategy["strategy"],
        "suggested_fix_summary": strategy["summary"],
        "affected_files_or_systems": affected_files,
        "evidence": evidence,
        "proposed_patch_policy": "NICO may draft a proposed diff, but it remains a recommendation until a human approves it.",
        "test_plan": payload.get("test_plan") or strategy["test_plan"],
        "rollback_plan": payload.get("rollback_plan") or strategy["rollback_plan"],
        "quality_checklist": REPAIR_QUALITY_CHECKLIST,
        "next_step": "Create an approval item if the customer wants NICO to prepare a draft repair branch or PR.",
        "human_review_required": True,
        "created_at": now_iso(),
    }
    STORE.put("repairs", suggestion_id, result)
    STORE.audit("repair.suggested", {"suggestion_id": suggestion_id, "strategy": result["strategy"]}, customer_id=result["customer_id"], project_id=result["project_id"])
    return result


def create_repair_approval(payload: dict[str, Any]) -> dict[str, Any]:
    suggestion = suggest_repair(payload)
    return create_approval({
        "customer_id": suggestion["customer_id"],
        "project_id": suggestion["project_id"],
        "requested_action": "draft_pr",
        "evidence": suggestion.get("evidence") or [suggestion["issue"]],
        "affected_files_or_systems": suggestion.get("affected_files_or_systems") or [],
        "risk_level": suggestion["risk_level"],
        "test_plan": suggestion["test_plan"],
        "rollback_plan": suggestion["rollback_plan"],
        "requester": "nico_repair_intelligence",
    })


def repair_quality_policy() -> dict[str, Any]:
    return {
        "status": "ok",
        "policy": "suggest_diff_approval_pr_review_merge",
        "rules": [
            "Do not edit protected branches automatically.",
            "Do not create draft PRs without an approved approval item.",
            "Do not present a suggestion as verified unless tests or evidence support it.",
            "Every suggested repair must include evidence, risk, test plan, and rollback plan.",
        ],
        "quality_checklist": REPAIR_QUALITY_CHECKLIST,
    }
