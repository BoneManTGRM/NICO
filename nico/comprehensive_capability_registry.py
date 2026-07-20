from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES, EXPRESS_STAGES

VERSION = "nico.comprehensive_capability_registry.v2"

CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "authorization_and_scope": {"capability": "authorization", "required": True, "sources": ["hosted_assessment"]},
    "immutable_repository_snapshot": {"capability": "snapshot", "required": True, "sources": ["repository_snapshot"]},
    "repository_and_delivery_evidence": {"capability": "repository_evidence", "required": True, "sources": ["snapshot_repository_evidence"]},
    "dependency_security_static_analysis": {"capability": "scanner_suite", "required": True, "sources": ["snapshot_scanner_worker"]},
    "ci_cd_architecture_complexity_velocity": {"capability": "technical_analysis", "required": True, "sources": ["snapshot_repository_evidence", "full_assessment_complexity_evidence"]},
    "evidence_reconciliation_and_scoring": {"capability": "canonical_scoring", "required": True, "sources": ["assessment_quality"]},
    "decision_report_generation": {"capability": "report_generation", "required": True, "sources": ["comprehensive_report_package"]},
    "deep_scanner_triage": {"capability": "scanner_triage", "required": True, "sources": ["snapshot_scanner_worker"]},
    "functional_qa": {"capability": "functional_qa", "required": True, "sources": ["snapshot_repository_evidence"]},
    "platform_parity": {"capability": "platform_parity", "required": True, "sources": ["snapshot_repository_evidence"]},
    "deployment_and_infrastructure": {"capability": "deployment_review", "required": True, "sources": ["snapshot_repository_evidence"]},
    "architecture_and_data_flow": {"capability": "architecture_data_flow", "required": True, "sources": ["snapshot_repository_evidence"]},
    "developer_delivery_process": {"capability": "delivery_process", "required": True, "sources": ["snapshot_repository_evidence"]},
    "stakeholder_and_business_alignment": {"capability": "stakeholder_alignment", "required": True, "sources": ["human_context_boundary"]},
    "requirements_traceability": {"capability": "requirements_traceability", "required": True, "sources": ["snapshot_repository_evidence", "human_context_boundary"]},
    "historical_trends_and_change_failure": {"capability": "historical_trends", "required": True, "sources": ["snapshot_repository_evidence"]},
    "six_month_roadmap": {"capability": "roadmap", "required": True, "sources": ["comprehensive_repair_intelligence"]},
    "staffing_sequencing_and_cost": {"capability": "resourcing", "required": True, "sources": ["comprehensive_repair_intelligence"]},
    "risk_reduction_and_executive_briefing": {"capability": "executive_briefing", "required": True, "sources": ["comprehensive_repair_intelligence"]},
    "final_comprehensive_report_generation": {"capability": "final_report_generation", "required": True, "sources": ["comprehensive_report_package"]},
    "cross_format_truth_verification": {"capability": "cross_format_verification", "required": True, "sources": ["comprehensive_report_package"]},
    "human_review_request": {"capability": "human_review", "required": True, "sources": ["comprehensive_review_request"]},
    "client_acceptance_pending": {"capability": "acceptance_gate", "required": True, "sources": ["comprehensive_review_request"]},
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
