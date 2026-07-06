from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EXPRESS_SCOPE = [
    "Code audit and recent development activity",
    "Library/dependency ecosystem health",
    "CI/CD reliability and release process",
    "Architecture and technical debt",
    "Maturity semaphore by audit area",
    "Velocity and complexity signal",
    "Strategic quick wins and medium-term action plan",
    "Resourcing recommendation",
]

ABA_EVIDENCE_PATTERNS = {
    "no_verified_picks": "No verified picks were available in the product artifact.",
    "current_provider_gate": "Current provider gate blocked publishable output.",
    "provider_not_matched": "Provider data did not match a live/current provider row.",
    "data_unavailable": "Odds/confidence/edge/EV or other market metrics were unavailable.",
    "research_only": "Final recommendation was research-only rather than client-publishable.",
    "lineup_injury_unverified": "Lineup or injury evidence was not verified.",
    "snapshot_missing": "Live team snapshot evidence was not returned.",
}


def _contains(text: str, *needles: str) -> bool:
    value = text.lower()
    return any(needle.lower() in value for needle in needles)


def quote_facts(quote_text: str) -> dict[str, Any]:
    text = quote_text or ""
    facts = {
        "service_detected": "Express Technical Health Assessment" if _contains(text, "express technical health assessment") else "Unknown",
        "timeline": "2 weeks" if _contains(text, "2 weeks", "2 semanas") else "not detected",
        "price": "$4,500.00 USD + IVA" if _contains(text, "$4,500", "4500") else "not detected",
        "payment_terms": "50% upfront / 50% on final report" if _contains(text, "50%", "2,250") else "not detected",
        "client_responsibilities": [],
    }
    if _contains(text, "read-only", "solo lectura"):
        facts["client_responsibilities"].append("Read-only repository access")
    if _contains(text, "ci/cd", "pipelines"):
        facts["client_responsibilities"].append("CI/CD configuration and logs")
    if _contains(text, "documentación técnica", "technical documentation"):
        facts["client_responsibilities"].append("Technical documentation")
    if _contains(text, "q&a"):
        facts["client_responsibilities"].append("Q&A session with development or technical leadership")
    if _contains(text, "pm/lead"):
        facts["client_responsibilities"].append("Assigned PM or technical lead")
    return facts


def product_artifact_findings(product_evidence_text: str) -> list[dict[str, str]]:
    text = product_evidence_text or ""
    findings: list[dict[str, str]] = []
    checks = {
        "no_verified_picks": ("no verified picks",),
        "current_provider_gate": ("current provider gate",),
        "provider_not_matched": ("provider not matched", "not matched to a live provider"),
        "data_unavailable": ("data unavailable", "odds status", "no verified buyer picks"),
        "research_only": ("research only",),
        "lineup_injury_unverified": ("no verified lineup", "verify lineup", "injury update"),
        "snapshot_missing": ("no live team snapshot",),
    }
    for key, needles in checks.items():
        if _contains(text, *needles):
            findings.append({"id": key, "finding": ABA_EVIDENCE_PATTERNS[key], "severity": "high" if key in {"no_verified_picks", "current_provider_gate", "research_only"} else "medium"})
    return findings


def deliverable_checklist(assessment: dict[str, Any] | None, scanner_attached: bool) -> list[dict[str, str]]:
    assessment = assessment or {}
    sections = {str(item.get("id") or item.get("label") or "").lower(): item for item in assessment.get("sections", []) if isinstance(item, dict)}
    unavailable_notes = assessment.get("unavailable_data_notes") or []
    def status_for(*keys: str) -> str:
        if not assessment:
            return "needs_evidence"
        if any(key in sections for key in keys):
            return "complete_with_review"
        if unavailable_notes:
            return "limited"
        return "needs_evidence"
    return [
        {"deliverable": "Code audit", "status": status_for("code_audit", "code audit"), "required_evidence": "Repository metadata, files, PR/commit patterns"},
        {"deliverable": "Library/dependency health", "status": "complete_with_review" if scanner_attached else status_for("dependency_health", "library ecosystem"), "required_evidence": "pip-audit, npm audit, lockfiles, dependency manifests"},
        {"deliverable": "CI/CD analysis", "status": status_for("ci_cd", "ci/cd"), "required_evidence": "Workflow files, logs, check history, deployment signals"},
        {"deliverable": "Architecture and technical debt", "status": status_for("architecture", "technical debt"), "required_evidence": "Repo structure, modules, report pipeline, API boundaries"},
        {"deliverable": "Product/report pipeline review", "status": "needs_human_review", "required_evidence": "Generated reports, provider-gate behavior, stale data checks"},
        {"deliverable": "Maturity semaphore", "status": "needs_human_review", "required_evidence": "NICO sections plus verified/unavailable evidence"},
        {"deliverable": "Action plan and quick wins", "status": "draftable", "required_evidence": "Findings ranked by impact and confidence"},
        {"deliverable": "Resourcing recommendation", "status": "draftable", "required_evidence": "Risk concentration, execution complexity, roadmap needs"},
        {"deliverable": "Client-ready package", "status": "human_review_required", "required_evidence": "Final factual review and signoff"},
    ]


def provider_gate_root_cause_prompts() -> list[str]:
    return [
        "Confirm API keys are loaded and health checks pass without exposing secrets.",
        "Trace buyer-pick gate rules and log why each candidate row is rejected.",
        "Check whether saved rows are stale, duplicated, or disconnected from current provider data.",
        "Verify odds, market availability, lineup/injury, and team snapshot enrichments before export.",
        "Ensure report exports drop unavailable sections or mark them unavailable instead of publishing placeholders.",
        "Add evidence IDs for provider source, timestamp, market, and rejection reason.",
    ]


def build_client_job_package(payload: dict[str, Any]) -> dict[str, Any]:
    quote_text = str(payload.get("quote_text") or "")
    product_evidence_text = str(payload.get("product_evidence_text") or "")
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    scanner_attached = bool(
        assessment.get("worker_evidence_attachment", {}).get("status") == "complete"
        or assessment.get("evidence_readiness", {}).get("scanner_worker_attached")
        or assessment.get("evidence_readiness", {}).get("existing_worker_evidence_attached")
    )
    findings = product_artifact_findings(product_evidence_text)
    return {
        "status": "ok",
        "mode": "client_job_mode_v7",
        "client_name": payload.get("client_name") or "Client",
        "project_name": payload.get("project_name") or "Project",
        "repository": payload.get("repository") or "",
        "service_scope": "Express Technical Health Assessment",
        "scope_remap_note": "For non-mobile products, map the quoted iOS/Android audit categories to the real backend, frontend, CI/CD, data-provider, and report-export surfaces.",
        "quote_facts": quote_facts(quote_text),
        "express_scope": EXPRESS_SCOPE,
        "product_artifact_findings": findings,
        "provider_gate_root_cause_prompts": provider_gate_root_cause_prompts() if findings else [],
        "deliverable_checklist": deliverable_checklist(assessment, scanner_attached),
        "report_outline": [
            "Executive Summary",
            "Technical Maturity Semaphore",
            "Evidence Sources and Limitations",
            "Code Audit",
            "Library / Dependency Health",
            "CI/CD Analysis",
            "Architecture and Technical Debt",
            "Product Report Pipeline Findings",
            "Verified / Unverified Claims",
            "Unavailable Evidence",
            "Quick Wins",
            "30/60/90-Day Action Plan",
            "Resourcing Recommendation",
            "Human Review Required",
        ],
        "human_review_required": True,
        "delivery_verdict": "draft_ready_for_human_review" if assessment else "needs_scanner_express_evidence",
    }
