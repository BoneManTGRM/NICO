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
    "No production/default/protected branch is changed automatically.",
    "Test plan is specific and starts with the smallest failing test.",
    "Rollback plan is specific.",
    "Risk level and confidence are stated.",
    "Human approval is required before draft PR creation.",
]


def severity_from_text(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["production down", "data loss", "critical", "payment broken", "security exposure"]):
        return "high"
    if any(word in lower for word in ["failing", "error", "broken", "timeout", "missing dependency", "unavailable", "regression"]):
        return "medium"
    return "low"


def confidence_from_evidence(evidence: list[str], affected_files: list[str]) -> str:
    if len(evidence) >= 3 and affected_files:
        return "high"
    if evidence or affected_files:
        return "medium"
    return "low"


def repair_strategy(issue: str) -> dict[str, Any]:
    lower = issue.lower()
    if "missing dependency" in lower or "module not found" in lower or "requires" in lower or "multipart" in lower:
        return {
            "strategy": "dependency_or_runtime_contract_fix",
            "root_cause_hypothesis": "A new import, endpoint, or runtime path depends on a package that is not installed in the CI/runtime environment.",
            "summary": "Add or pin the missing runtime/test dependency, then rerun compile, the smallest failing test, and the full test suite.",
            "patch_steps": [
                "Identify the exact import or framework feature that triggered the missing dependency.",
                "Add the smallest required package to requirements.txt or package.json.",
                "Prefer a pinned or bounded version when deployment reproducibility matters.",
                "Add or update a regression test that imports the affected endpoint/module.",
            ],
            "test_plan": "Install dependencies, compile affected modules, run the failing test file, then run the full test suite and deployment smoke check.",
            "rollback_plan": "Remove the dependency change and revert any related endpoint/import change if CI or deploy breaks.",
        }
    if "type" in lower or "validation" in lower or "schema" in lower or "pydantic" in lower:
        return {
            "strategy": "interface_contract_fix",
            "root_cause_hypothesis": "The request/response contract changed or accepts data that is not represented by the model/schema/tests.",
            "summary": "Tighten request/response typing and add regression tests around the failing API or module contract.",
            "patch_steps": [
                "Identify the exact model, field, or endpoint contract that failed.",
                "Make the model explicit and backwards-compatible where possible.",
                "Add negative and positive test cases.",
                "Update docs or frontend payload shape if the API changed.",
            ],
            "test_plan": "Run unit tests for the affected endpoint/module, schema validation tests, and a frontend/backend payload smoke check.",
            "rollback_plan": "Revert the schema or typing change and restore the previous contract.",
        }
    if "timeout" in lower or "slow" in lower or "long-running" in lower or "blocking" in lower:
        return {
            "strategy": "background_job_or_timeout_fix",
            "root_cause_hypothesis": "Long-running work is being handled synchronously or without bounded timeout/status tracking.",
            "summary": "Move long-running work to a background job and return a job ID with status polling and clear unavailable/error states.",
            "patch_steps": [
                "Create a job record before work starts.",
                "Return job_id immediately.",
                "Track queued/running/complete/failed states.",
                "Apply per-task and total time limits.",
            ],
            "test_plan": "Run worker status tests, timeout tests, and API smoke tests for the job polling path.",
            "rollback_plan": "Disable the worker path and return the prior synchronous behavior only if safe.",
        }
    if "ui" in lower or "dropdown" in lower or "how to use" in lower or "section" in lower:
        return {
            "strategy": "guided_user_experience_fix",
            "root_cause_hypothesis": "Users need clearer step-by-step guidance at the point of action.",
            "summary": "Add inline help, expandable details, examples, and section-specific warnings without hiding the core workflow.",
            "patch_steps": [
                "Add a reusable help/details component.",
                "Place it directly inside each workflow section.",
                "Include step-by-step use, required evidence, good output, and common mistakes.",
                "Keep warnings visible for authorization and human review.",
            ],
            "test_plan": "Run frontend build or TypeScript compile and visually verify every details block opens and closes on mobile and desktop.",
            "rollback_plan": "Remove the helper component and return sections to previous static text.",
        }
    return {
        "strategy": "evidence_first_minimal_patch",
        "root_cause_hypothesis": "The evidence points to a repair opportunity, but more context may be needed before changing code.",
        "summary": "Collect the failing evidence, isolate the smallest reproducible case, then propose the smallest reversible patch.",
        "patch_steps": [
            "Collect exact error, failing test, report section, or customer evidence.",
            "Identify affected files or systems.",
            "Change only what is needed to resolve the verified issue.",
            "Add or update a regression test when possible.",
            "Create an approval item before any draft PR path.",
        ],
        "test_plan": "Run the smallest relevant regression test, then the full test suite and deployment smoke check.",
        "rollback_plan": "Revert the patch branch and leave production/default branches unchanged.",
    }


def build_patch_prompt(issue: str, strategy: dict[str, Any], affected_files: list[str]) -> str:
    files = "\n".join(f"- {item}" for item in affected_files) if affected_files else "- Unknown; identify before patching."
    steps = "\n".join(f"- {item}" for item in strategy["patch_steps"])
    return f"""Create a minimal, reviewable repair proposal for this NICO/customer issue.

Issue:
{issue}

Root-cause hypothesis:
{strategy['root_cause_hypothesis']}

Affected files/systems:
{files}

Patch strategy:
{steps}

Rules:
- Do not push to main.
- Do not deploy automatically.
- Do not claim the fix is verified until tests pass.
- Include evidence, rationale, test plan, and rollback plan.
- Produce a draft patch or PR description for human approval.
""".strip()


def suggest_repair(payload: dict[str, Any]) -> dict[str, Any]:
    issue = payload.get("issue") or payload.get("finding") or "Unspecified issue"
    evidence = payload.get("evidence") or []
    affected_files = payload.get("affected_files") or []
    strategy = repair_strategy(issue)
    risk_level = payload.get("risk_level") or severity_from_text(issue)
    confidence = confidence_from_evidence(evidence, affected_files)
    suggestion_id = f"repair_{uuid4().hex[:16]}"
    result = {
        "status": "complete",
        "suggestion_id": suggestion_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "issue": issue,
        "risk_level": risk_level,
        "confidence": confidence,
        "strategy": strategy["strategy"],
        "root_cause_hypothesis": strategy["root_cause_hypothesis"],
        "suggested_fix_summary": strategy["summary"],
        "patch_steps": strategy["patch_steps"],
        "affected_files_or_systems": affected_files,
        "evidence": evidence,
        "proposed_patch_policy": "NICO may draft a proposed diff, but it remains a recommendation until a human approves it.",
        "patch_prompt": build_patch_prompt(issue, strategy, affected_files),
        "test_plan": payload.get("test_plan") or strategy["test_plan"],
        "rollback_plan": payload.get("rollback_plan") or strategy["rollback_plan"],
        "quality_checklist": REPAIR_QUALITY_CHECKLIST,
        "next_step": "Create an approval item if the customer wants NICO to prepare a draft repair branch or PR.",
        "human_review_required": True,
        "created_at": now_iso(),
    }
    STORE.put("repairs", suggestion_id, result)
    STORE.audit("repair.suggested", {"suggestion_id": suggestion_id, "strategy": result["strategy"], "confidence": confidence}, customer_id=result["customer_id"], project_id=result["project_id"])
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
            "Every suggested repair must include evidence, risk, confidence, test plan, and rollback plan.",
            "Prefer the smallest reversible patch that can be tested.",
        ],
        "quality_checklist": REPAIR_QUALITY_CHECKLIST,
    }
