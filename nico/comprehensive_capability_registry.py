from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES, EXPRESS_STAGES

VERSION = "nico.comprehensive_capability_registry.v1"

# Customer-facing Comprehensive has one contract, while existing internal modules are
# migrated behind stable stage identifiers. Strings avoid eager imports and allow
# deployment-specific adapters to resolve capabilities safely.
CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "authorization_and_scope": {"capability": "authorization", "required": True, "sources": ["hosted_assessment"]},
    "immutable_repository_snapshot": {"capability": "snapshot", "required": True, "sources": ["hosted_assessment", "assessment_recovery"]},
    "repository_and_delivery_evidence": {"capability": "repository_evidence", "required": True, "sources": ["hosted_assessment"]},
    "dependency_security_static_analysis": {"capability": "scanner_suite", "required": True, "sources": ["scanner_worker"]},
    "ci_cd_architecture_complexity_velocity": {"capability": "technical_analysis", "required": True, "sources": ["assessment_quality"]},
    "evidence_reconciliation_and_scoring": {"capability": "canonical_scoring", "required": True, "sources": ["assessment_quality"]},
    "decision_report_generation": {"capability": "report_generation", "required": True, "sources": ["assessment_quality"]},
    "deep_scanner_triage": {"capability": "scanner_triage", "required": True, "sources": ["mid_review_enforcement"]},
    "functional_qa": {"capability": "functional_qa", "required": True, "sources": ["mid_review_enforcement"]},
    "platform_parity": {"capability": "platform_parity", "required": True, "sources": ["mid_review_enforcement"]},
    "deployment_and_infrastructure": {"capability": "deployment_review", "required": True, "sources": ["mid_delivery_access"]},
    "architecture_and_data_flow": {"capability": "architecture_data_flow", "required": True, "sources": ["assessment_quality"]},
    "developer_delivery_process": {"capability": "delivery_process", "required": True, "sources": ["hosted_assessment"]},
    "stakeholder_and_business_alignment": {"capability": "stakeholder_alignment", "required": True, "sources": ["mid_review_enforcement"]},
    "requirements_traceability": {"capability": "requirements_traceability", "required": True, "sources": ["mid_review_enforcement"]},
    "historical_trends_and_change_failure": {"capability": "historical_trends", "required": True, "sources": ["assessment_recovery"]},
    "six_month_roadmap": {"capability": "roadmap", "required": True, "sources": ["mid_review_enforcement"]},
    "staffing_sequencing_and_cost": {"capability": "resourcing", "required": True, "sources": ["mid_review_enforcement"]},
    "risk_reduction_and_executive_briefing": {"capability": "executive_briefing", "required": True, "sources": ["assessment_quality"]},
    "cross_format_truth_verification": {"capability": "cross_format_verification", "required": True, "sources": ["assessment_quality"]},
    "human_review_request": {"capability": "human_review", "required": True, "sources": ["mid_review_enforcement"]},
    "client_acceptance_pending": {"capability": "acceptance_gate", "required": True, "sources": ["mid_delivery_access"]},
}


def comprehensive_capability_registry() -> dict[str, dict[str, Any]]:
    return deepcopy(CAPABILITY_REGISTRY)


def validate_capability_registry(registry: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    candidate = registry or CAPABILITY_REGISTRY
    missing = [stage for stage in COMPREHENSIVE_STAGES if stage not in candidate]
    unknown = [stage for stage in candidate if stage not in COMPREHENSIVE_STAGES]
    invalid: list[str] = []
    for stage, item in candidate.items():
        if not isinstance(item, dict):
            invalid.append(stage)
            continue
        if not str(item.get("capability") or "").strip():
            invalid.append(stage)
        if item.get("required") is not True:
            invalid.append(stage)
        if not [source for source in item.get("sources") or [] if str(source).strip()]:
            invalid.append(stage)
    express_prefix = list(candidate)[: len(EXPRESS_STAGES)] == list(EXPRESS_STAGES)
    return {
        "status": "valid" if not (missing or unknown or invalid) and express_prefix else "invalid",
        "artifact_schema": VERSION,
        "missing_stages": missing,
        "unknown_stages": unknown,
        "invalid_stages": sorted(set(invalid)),
        "express_stages_first": express_prefix,
        "stage_count": len(candidate),
        "expected_stage_count": len(COMPREHENSIVE_STAGES),
        "customer_service_id": "comprehensive",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def execution_plan() -> list[dict[str, Any]]:
    registry = comprehensive_capability_registry()
    return [{"order": index + 1, "stage_id": stage, **registry[stage]} for index, stage in enumerate(COMPREHENSIVE_STAGES)]


__all__ = ["CAPABILITY_REGISTRY", "VERSION", "comprehensive_capability_registry", "execution_plan", "validate_capability_registry"]
