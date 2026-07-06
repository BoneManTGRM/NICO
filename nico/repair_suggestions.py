from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.storage import STORE


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def severity_from_score(score: int | None) -> str:
    if score is None:
        return "medium"
    if score < 45:
        return "high"
    if score < 75:
        return "medium"
    return "low"


def category_from_text(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ["dependency", "package", "lockfile", "requirements", "npm", "pip", "osv"]):
        return "dependencies"
    if any(token in lower for token in ["secret", "token", "key", "credential"]):
        return "secret_handling"
    if any(token in lower for token in ["ci", "workflow", "actions", "build", "test", "lint"]):
        return "ci_cd"
    if any(token in lower for token in ["architecture", "debt", "module", "scalability"]):
        return "architecture"
    if any(token in lower for token in ["qa", "parity", "roadmap", "stakeholder"]):
        return "product_quality"
    return "general_repair"


def templates_for_category(category: str) -> dict[str, Any]:
    library: dict[str, dict[str, Any]] = {
        "dependencies": {
            "summary": "Tighten dependency evidence and make dependency repair reproducible.",
            "recommended_fix": "Add or refresh lockfiles, pin ambiguous dependencies where appropriate, run dependency review tools in CI, and document upgrade decisions in the report appendix.",
            "patch_strategy": ["Add lockfile generation to the project workflow.", "Add dependency review command to CI.", "Record unavailable scanners instead of claiming clean results."],
            "test_plan": ["Run dependency scanner locally or in worker.", "Run test suite after upgrades.", "Confirm build still passes."],
            "rollback_plan": ["Revert dependency changes and lockfile updates as one commit if tests fail."],
        },
        "secret_handling": {
            "summary": "Reduce exposure risk and improve secret-handling evidence.",
            "recommended_fix": "Move sensitive values to environment variables or managed secret storage, rotate exposed values if confirmed, and add secret-pattern checks to CI.",
            "patch_strategy": ["Replace hardcoded sensitive placeholders with environment lookups.", "Add .env.example without real values.", "Add CI check for secret-pattern detection."],
            "test_plan": ["Confirm app starts using environment values.", "Confirm no real sensitive values are printed in logs.", "Run CI secret-pattern check."],
            "rollback_plan": ["Revert code-only changes; do not restore exposed secrets."],
        },
        "ci_cd": {
            "summary": "Improve delivery reliability by making CI evidence complete and enforceable.",
            "recommended_fix": "Ensure lint, tests, build, dependency review, and report generation are present in CI with clear failure signals.",
            "patch_strategy": ["Add missing workflow steps.", "Fail CI on broken tests/builds.", "Upload machine-readable test results as artifacts."],
            "test_plan": ["Run workflow on pull request branch.", "Confirm artifacts upload.", "Confirm failure paths fail visibly."],
            "rollback_plan": ["Disable only the failing new CI step while keeping previous CI behavior intact."],
        },
        "architecture": {
            "summary": "Reduce technical debt by separating responsibilities and documenting boundaries.",
            "recommended_fix": "Keep API, storage, reports, worker jobs, evidence handling, and approvals in separate modules with tests for each boundary.",
            "patch_strategy": ["Move large logic into focused modules.", "Add tests around module contracts.", "Document unavailable features honestly."],
            "test_plan": ["Run unit tests for each module.", "Run API smoke tests.", "Confirm hosted deployment imports cleanly."],
            "rollback_plan": ["Revert module extraction commit if import or deployment breaks."],
        },
        "product_quality": {
            "summary": "Strengthen Mid/Retainer evidence quality and client usefulness.",
            "recommended_fix": "Require QA notes, parity notes, stakeholder context, roadmap constraints, and known risks before generating strong conclusions.",
            "patch_strategy": ["Add structured intake fields.", "Show evidence readiness score.", "Mark blank sections unavailable."],
            "test_plan": ["Submit complete and incomplete evidence examples.", "Confirm missing evidence is marked unavailable.", "Confirm report text does not invent conclusions."],
            "rollback_plan": ["Return to previous intake layout if customers cannot complete the new form."],
        },
        "general_repair": {
            "summary": "Convert the finding into a safe, testable repair plan.",
            "recommended_fix": "Create a small patch with clear evidence, rationale, tests, and rollback notes before requesting human approval.",
            "patch_strategy": ["Identify affected files.", "Make the smallest safe change.", "Add tests or verification notes."],
            "test_plan": ["Run existing tests.", "Add a regression test when possible.", "Confirm report evidence matches the patch."],
            "rollback_plan": ["Revert the repair branch or close the draft PR if tests fail."],
        },
    }
    return library.get(category, library["general_repair"])


def build_suggestion(source: dict[str, Any], index: int) -> dict[str, Any]:
    label = source.get("label") or source.get("id") or source.get("title") or f"Finding {index + 1}"
    summary = source.get("summary") or source.get("finding") or source.get("description") or str(source)
    score = source.get("score") if isinstance(source.get("score"), int) else None
    category = category_from_text(f"{label} {summary}")
    template = templates_for_category(category)
    suggestion_id = f"suggestion_{uuid4().hex[:12]}"
    return {
        "suggestion_id": suggestion_id,
        "title": f"Repair suggestion: {label}",
        "category": category,
        "severity": severity_from_score(score),
        "source_summary": summary,
        "recommended_fix": template["recommended_fix"],
        "why_this_matters": template["summary"],
        "patch_strategy": template["patch_strategy"],
        "safe_code_change_policy": "Recommendation only. Create a draft branch/PR after human approval; never push to main or production automatically.",
        "test_plan": template["test_plan"],
        "rollback_plan": template["rollback_plan"],
        "approval_required": True,
        "client_wording": "NICO recommends this repair based on supplied evidence. A human reviewer must validate context, tests, and rollout before code changes are made.",
    }


def collect_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for section in payload.get("sections", []) or []:
        if isinstance(section, dict):
            sources.append(section)
    for finding in payload.get("findings", []) or []:
        sources.append({"label": "Finding", "summary": finding})
    for repair in payload.get("repairs", []) or []:
        sources.append({"label": "Repair", "summary": repair})
    if not sources:
        sources.append({"label": "General repair planning", "summary": "No assessment findings were provided. Generate only general repair guidance and mark evidence unavailable."})
    return sources


def build_repair_suggestions(payload: dict[str, Any]) -> dict[str, Any]:
    suggestions = [build_suggestion(source, index) for index, source in enumerate(collect_sources(payload))]
    result = {
        "status": "complete",
        "generated_at": now_iso(),
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": payload.get("repository") or "",
        "suggestions": suggestions,
        "human_review_required": True,
        "code_replacement_policy": "Suggest fixes, patch strategies, tests, and rollback plans. Create draft PRs only through the approval queue. Never edit production/main automatically.",
        "unavailable_data_notes": [] if payload.get("sections") or payload.get("findings") or payload.get("repairs") else ["No assessment evidence was supplied; suggestions are generic."],
    }
    STORE.audit("repair_suggestions.generated", {"count": len(suggestions), "repository": result["repository"]}, customer_id=result["customer_id"], project_id=result["project_id"])
    return result
