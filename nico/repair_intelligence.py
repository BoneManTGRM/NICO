from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.approval_queue import create_approval
from nico.code_repair_suggestions import REPORT_ONLY_CODE_POLICY, build_code_suggestion
from nico.storage import STORE


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


REPAIR_QUALITY_CHECKLIST = [
    "Evidence is attached or cited.",
    "Root cause is stated as a hypothesis unless fully verified.",
    "Affected files or systems are listed.",
    "Proposed change is minimal and reversible.",
    "No assessed repository file is changed automatically.",
    "No production/default/protected branch is changed automatically.",
    "Suggested code is labeled report-only and unverified until tests pass.",
    "Test plan is specific and starts with the smallest failing test.",
    "Rollback plan is specific.",
    "Risk level and confidence are stated.",
    "Human approval is required before any draft branch or pull request creation.",
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


def category_from_issue(issue: str) -> str:
    lower = issue.lower()
    if any(value in lower for value in ("secret", "credential", "private key", "token exposed")):
        return "secret_exposure"
    if any(value in lower for value in ("eval(", "unsafe eval", "dynamic execution")):
        return "unsafe_eval"
    if any(value in lower for value in ("shell=true", "shell = true", "os.system")):
        return "command_execution"
    if "yaml.load" in lower:
        return "unsafe_yaml_load"
    if any(value in lower for value in ("missing dependency", "module not found", "multipart", "dependency")):
        return "dependency_risk"
    if any(value in lower for value in ("debug=true", "debug mode")):
        return "debug_mode"
    if "webhook" in lower and "signature" in lower:
        return "insecure_webhook"
    if "rate limit" in lower:
        return "missing_rate_limit"
    if "upload" in lower and any(value in lower for value in ("unsafe", "validate", "path")):
        return "unsafe_file_upload"
    if any(value in lower for value in ("innerhtml", "dangerouslysetinnerhtml", "xss")):
        return "cross_site_scripting"
    if any(value in lower for value in ("verify=false", "tls verification", "rejectunauthorized")):
        return "tls_verify_disabled"
    if any(value in lower for value in ("patch module", "compatibility module", "install-time patch")):
        return "runtime_patch_surface"
    if "documentation" in lower and any(value in lower for value in ("drift", "commit", "outdated")):
        return "documentation_drift"
    return "technical_risk"


def repair_strategy(issue: str) -> dict[str, Any]:
    lower = issue.lower()
    if "missing dependency" in lower or "module not found" in lower or "requires" in lower or "multipart" in lower:
        return {"strategy":"dependency_or_runtime_contract_fix","root_cause_hypothesis":"A new import, endpoint, or runtime path depends on a package that is not installed in the CI/runtime environment.","summary":"Add or pin the missing runtime/test dependency, then rerun compile, the smallest failing test, and the full test suite.","patch_steps":["Identify the exact import or framework feature that triggered the missing dependency.","Resolve the minimum compatible package version from primary package and advisory evidence.","Place the proposed manifest change in the report only.","Add or update a regression test that imports the affected endpoint/module."],"test_plan":"Install dependencies in an isolated branch or fixture, compile affected modules, run the failing test file, then run the full test suite and deployment smoke check.","rollback_plan":"Do not apply the proposed manifest change if compatibility or security verification fails."}
    if "type" in lower or "validation" in lower or "schema" in lower or "pydantic" in lower:
        return {"strategy":"interface_contract_fix","root_cause_hypothesis":"The request/response contract changed or accepts data that is not represented by the model/schema/tests.","summary":"Tighten request/response typing and add regression tests around the failing API or module contract.","patch_steps":["Identify the exact model, field, or endpoint contract that failed.","Prepare a backwards-compatible candidate schema where possible.","Add negative and positive test cases.","Update docs or frontend payload shape if the API changed."],"test_plan":"Run unit tests for the affected endpoint/module, schema validation tests, and a frontend/backend payload smoke check.","rollback_plan":"Reject or revert the proposed schema change if compatibility tests fail."}
    if "timeout" in lower or "slow" in lower or "long-running" in lower or "blocking" in lower:
        return {"strategy":"background_job_or_timeout_fix","root_cause_hypothesis":"Long-running work is being handled synchronously or without bounded timeout/status tracking.","summary":"Prepare a background-job design with a job ID, status polling, bounded timeouts, and explicit unavailable/error states.","patch_steps":["Create a job record before work starts.","Return job_id immediately.","Track queued/running/complete/failed states.","Apply per-task and total time limits."],"test_plan":"Run worker status tests, timeout tests, and API smoke tests for the job polling path.","rollback_plan":"Keep the current safe behavior if the proposed worker path fails verification."}
    if "ui" in lower or "dropdown" in lower or "how to use" in lower or "section" in lower:
        return {"strategy":"guided_user_experience_fix","root_cause_hypothesis":"Users need clearer step-by-step guidance at the point of action.","summary":"Prepare inline help, expandable details, examples, and section-specific warnings without hiding the core workflow.","patch_steps":["Identify the exact workflow state and user decision that lacks guidance.","Prepare a reusable help/details component candidate.","Include required evidence, good output, and common mistakes.","Keep authorization and human-review warnings visible."],"test_plan":"Run frontend build or TypeScript compile and visually verify every proposed details block on mobile and desktop.","rollback_plan":"Do not adopt the UI candidate if it obscures or changes the canonical workflow."}
    return {"strategy":"evidence_first_minimal_patch","root_cause_hypothesis":"The evidence points to a repair opportunity, but more context may be needed before changing code.","summary":"Collect the failing evidence, isolate the smallest reproducible case, then place the smallest reversible repair candidate in the report.","patch_steps":["Collect the exact error, failing test, report section, or customer evidence.","Identify affected files or systems.","Prepare only the code or configuration needed to resolve the verified issue.","Add or update a regression test when possible.","Require human approval before any implementation path."],"test_plan":"Run the smallest relevant regression test, then the full test suite and deployment smoke check in an isolated review branch.","rollback_plan":"Do not apply the candidate if verification fails or required context remains unavailable."}


def build_patch_prompt(issue: str, strategy: dict[str, Any], affected_files: list[str]) -> str:
    files = "\n".join(f"- {item}" for item in affected_files) if affected_files else "- Unknown; identify before proposing exact replacement code."
    steps = "\n".join(f"- {item}" for item in strategy["patch_steps"])
    return f"""Prepare a report-only, reviewable repair proposal for this NICO/customer issue.

Issue:
{issue}

Root-cause hypothesis:
{strategy['root_cause_hypothesis']}

Affected files/systems:
{files}

Repair strategy:
{steps}

Rules:
- Do not edit the assessed repository.
- Do not create a branch, commit, pull request, or deployment.
- Do not claim the candidate is verified until the exact tests pass.
- Include evidence, rationale, applicability conditions, test plan, and rollback plan.
- Put any replacement code or diff only inside the report for human review.
""".strip()


def suggest_repair(payload: dict[str, Any]) -> dict[str, Any]:
    issue = payload.get("issue") or payload.get("finding") or "Unspecified issue"
    evidence = [str(item) for item in (payload.get("evidence") or [])]
    affected_files = [str(item) for item in (payload.get("affected_files") or [])]
    strategy = repair_strategy(issue)
    risk_level = payload.get("risk_level") or severity_from_text(issue)
    confidence = confidence_from_evidence(evidence, affected_files)
    category = str(payload.get("category") or category_from_issue(issue))
    suggestion_id = f"repair_{uuid4().hex[:16]}"
    code_suggestion = build_code_suggestion(
        category=category,
        issue=issue,
        evidence=evidence,
        affected_files=affected_files,
    )
    result = {
        "status": "complete",
        "suggestion_id": suggestion_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "issue": issue,
        "category": category,
        "risk_level": risk_level,
        "confidence": confidence,
        "strategy": strategy["strategy"],
        "root_cause_hypothesis": strategy["root_cause_hypothesis"],
        "suggested_fix_summary": strategy["summary"],
        "patch_steps": strategy["patch_steps"],
        "affected_files_or_systems": affected_files,
        "evidence": evidence,
        "code_suggestion": code_suggestion,
        "proposed_patch_policy": (
            "NICO may include a proposed code snippet or diff in the report. It does not edit the assessed repository, "
            "and the candidate remains unverified until human review and tests pass."
        ),
        "patch_prompt": build_patch_prompt(issue, strategy, affected_files),
        "test_plan": payload.get("test_plan") or strategy["test_plan"],
        "rollback_plan": payload.get("rollback_plan") or strategy["rollback_plan"],
        "quality_checklist": REPAIR_QUALITY_CHECKLIST,
        "next_step": "Review the report candidate and run its tests in an isolated human-controlled branch if the client approves implementation.",
        "mode": "report_only",
        "code_change_applied": False,
        "automatic_application_allowed": False,
        "automatic_commit_allowed": False,
        "automatic_pull_request_allowed": False,
        "human_review_required": True,
        "verified_fix": False,
        "accuracy_statement": REPORT_ONLY_CODE_POLICY["accuracy_statement"],
        "created_at": now_iso(),
    }
    STORE.put("repairs", suggestion_id, result)
    STORE.audit(
        "repair.suggested",
        {
            "suggestion_id": suggestion_id,
            "strategy": result["strategy"],
            "confidence": confidence,
            "mode": "report_only",
            "code_change_applied": False,
        },
        customer_id=result["customer_id"],
        project_id=result["project_id"],
    )
    return result


def create_repair_approval(payload: dict[str, Any]) -> dict[str, Any]:
    suggestion = suggest_repair(payload)
    return create_approval({
        "customer_id": suggestion["customer_id"],
        "project_id": suggestion["project_id"],
        "requested_action": "review_report_repair_candidate",
        "issue": suggestion["issue"],
        "root_cause_hypothesis": suggestion["root_cause_hypothesis"],
        "confidence": suggestion["confidence"],
        "suggested_fix_summary": suggestion["suggested_fix_summary"],
        "patch_steps": suggestion["patch_steps"],
        "patch_prompt": suggestion["patch_prompt"],
        "code_suggestion": suggestion["code_suggestion"],
        "evidence": suggestion.get("evidence") or [suggestion["issue"]],
        "affected_files_or_systems": suggestion.get("affected_files_or_systems") or [],
        "risk_level": suggestion["risk_level"],
        "test_plan": suggestion["test_plan"],
        "rollback_plan": suggestion["rollback_plan"],
        "requester": "nico_repair_intelligence",
        "automatic_application_allowed": False,
    })


def repair_quality_policy() -> dict[str, Any]:
    return {
        "status": "ok",
        "policy": "report_only_suggestion_review_test_optional_implementation",
        "rules": [
            "Do not edit the assessed repository automatically.",
            "Do not create branches or pull requests from a report suggestion automatically.",
            "Do not present a code candidate as verified unless the exact tests pass.",
            "Every suggested repair must include evidence, risk, confidence, applicability conditions, tests, and rollback guidance.",
            "Return no code candidate when the available context is insufficient for a conservative template.",
            "Prefer the smallest reversible candidate and preserve human review.",
        ],
        "code_suggestion_policy": dict(REPORT_ONLY_CODE_POLICY),
        "quality_checklist": REPAIR_QUALITY_CHECKLIST,
    }
