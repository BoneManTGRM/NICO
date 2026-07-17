from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

_TAG_FRAGMENT = re.compile(r"<\/?[A-Za-z][^>]{0,200}>")


@dataclass(frozen=True)
class ReportTierContract:
    tier: str
    audience: tuple[str, ...]
    minimum_substantive_pages: int
    target_substantive_pages: tuple[int, int]
    required_sections: tuple[str, ...]
    required_visuals: tuple[str, ...]
    requires_runtime_evidence: bool = False
    requires_business_context: bool = False


REPORT_TIER_CONTRACTS: dict[str, ReportTierContract] = {
    "express": ReportTierContract(
        "express", ("founder", "operator", "investor"), 12, (15, 20),
        ("executive_decision", "repository_profile", "technical_scorecard", "top_risks", "verified_strengths", "evidence_coverage", "priority_repairs", "verification_plan", "integrity_and_approval"),
        ("score_contribution", "risk_matrix", "repair_priority"),
    ),
    "mid": ReportTierContract(
        "mid", ("cto", "engineering_manager", "technical_investor"), 28, (35, 50),
        ("executive_decision", "repository_profile", "technical_scorecard", "evidence_assurance", "seven_technical_dossiers", "architecture_and_dependencies", "security_and_static_analysis", "cicd_classification", "complexity_churn_and_ownership", "score_sensitivity", "phased_repair_roadmap", "human_context_requests", "evidence_appendix", "integrity_and_approval"),
        ("score_radar", "risk_matrix", "evidence_funnel", "architecture_map", "dependency_map", "complexity_heatmap", "repair_impact_matrix"),
    ),
    "full": ReportTierContract(
        "full", ("board", "enterprise", "private_equity", "government", "procurement"), 55, (70, 120),
        ("executive_decision", "board_briefing", "repository_profile", "technical_scorecard", "evidence_assurance", "complete_technical_dossiers", "architecture_and_data_flow", "threat_model", "runtime_and_functional_qa", "platform_parity", "developer_workflow", "historical_trends", "change_failure_analysis", "operational_readiness", "stakeholder_alignment", "business_aligned_roadmap", "risk_reduction_and_roi", "control_mapping", "complete_evidence_appendix", "integrity_and_approval"),
        ("score_radar", "risk_matrix", "evidence_funnel", "architecture_map", "data_flow_map", "dependency_map", "complexity_heatmap", "ownership_map", "cicd_trend", "historical_score_trend", "repair_impact_matrix", "roadmap_timeline"),
        True, True,
    ),
}


def normalize_report_tier(value: Any) -> str:
    tier = str(value or "").strip().lower()
    tier = {"quick": "express", "medium": "mid", "deep": "full", "enterprise": "full"}.get(tier, tier)
    if tier not in REPORT_TIER_CONTRACTS:
        raise ValueError(f"Unsupported report tier: {value!r}")
    return tier


def get_report_tier_contract(value: Any) -> ReportTierContract:
    return REPORT_TIER_CONTRACTS[normalize_report_tier(value)]


def serialize_report_tier_contract(value: Any) -> dict[str, Any]:
    return asdict(get_report_tier_contract(value))


def evaluate_report_product_quality(*, tier: Any, page_count: int | None, rendered_text: str, section_presence: Mapping[str, bool] | None = None, visual_presence: Mapping[str, bool] | None = None, approved: bool = False, evidence_sufficient_for_depth: bool = False) -> dict[str, Any]:
    contract = get_report_tier_contract(tier)
    text = str(rendered_text or "")
    sections = section_presence or {}
    visuals = visual_presence or {}
    defects: list[dict[str, str]] = []

    if _TAG_FRAGMENT.search(text):
        defects.append({"severity": "high", "code": "visible_markup", "message": "Rendered output contains visible tag-shaped markup."})
    if approved and re.search(r"\bDRAFT\b", text, flags=re.IGNORECASE):
        defects.append({"severity": "high", "code": "approved_artifact_marked_draft", "message": "Approved artifact still displays draft wording."})
    if not approved and not re.search(r"human review|required review|review required", text, flags=re.IGNORECASE):
        defects.append({"severity": "high", "code": "missing_review_boundary", "message": "Unapproved artifact does not preserve the human-review boundary."})

    missing_sections = [name for name in contract.required_sections if not sections.get(name)]
    missing_visuals = [name for name in contract.required_visuals if not visuals.get(name)]
    if missing_sections:
        defects.append({"severity": "medium", "code": "missing_required_sections", "message": ", ".join(missing_sections)})
    if missing_visuals:
        defects.append({"severity": "medium", "code": "missing_required_visuals", "message": ", ".join(missing_visuals)})
    if evidence_sufficient_for_depth and page_count is not None and int(page_count) < contract.minimum_substantive_pages:
        defects.append({"severity": "medium", "code": "insufficient_substantive_depth", "message": f"{page_count} pages is below the {contract.minimum_substantive_pages}-page minimum for {contract.tier}."})

    return {
        "tier": contract.tier,
        "contract": asdict(contract),
        "page_count": page_count,
        "missing_sections": missing_sections,
        "missing_visuals": missing_visuals,
        "defects": defects,
        "release_blocked": any(item["severity"] == "high" for item in defects),
        "product_ready": not defects,
    }


__all__ = ["REPORT_TIER_CONTRACTS", "ReportTierContract", "evaluate_report_product_quality", "get_report_tier_contract", "normalize_report_tier", "serialize_report_tier_contract"]
