from __future__ import annotations

from copy import deepcopy
from typing import Any

VERSION = "nico.comprehensive_orchestration_contract.v2"

EXPRESS_STAGES = (
    "authorization_and_scope",
    "immutable_repository_snapshot",
    "repository_and_delivery_evidence",
    "dependency_security_static_analysis",
    "ci_cd_architecture_complexity_velocity",
    "evidence_reconciliation_and_scoring",
    "decision_report_generation",
)

COMPREHENSIVE_ONLY_STAGES = (
    "deep_scanner_triage",
    "functional_qa",
    "platform_parity",
    "deployment_and_infrastructure",
    "architecture_and_data_flow",
    "developer_delivery_process",
    "stakeholder_and_business_alignment",
    "requirements_traceability",
    "historical_trends_and_change_failure",
    "six_month_roadmap",
    "staffing_sequencing_and_cost",
    "risk_reduction_and_executive_briefing",
    "final_comprehensive_report_generation",
)

TERMINAL_STAGES = (
    "cross_format_truth_verification",
    "human_review_request",
    "client_acceptance_pending",
)

COMPREHENSIVE_STAGES = EXPRESS_STAGES + COMPREHENSIVE_ONLY_STAGES + TERMINAL_STAGES


def build_comprehensive_contract(*, repository: str, authorized: bool, commit_sha: str | None = None) -> dict[str, Any]:
    blockers: list[str] = []
    if not repository.strip():
        blockers.append("repository_required")
    if not authorized:
        blockers.append("explicit_authorization_required")
    if commit_sha is not None and not commit_sha.strip():
        blockers.append("commit_sha_must_not_be_blank")

    stages = [
        {
            "id": stage,
            "status": "blocked" if blockers else "pending",
            "required": True,
            "customer_visible": True,
        }
        for stage in COMPREHENSIVE_STAGES
    ]

    return {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "customer_service_name": "NICO Comprehensive Technical Assessment",
        "repository": repository.strip(),
        "commit_sha": commit_sha.strip() if isinstance(commit_sha, str) else None,
        "authorized": bool(authorized),
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "one_snapshot": True,
        "one_run_id": True,
        "one_evidence_ledger": True,
        "one_canonical_score": True,
        "one_final_report_package": True,
        "includes_everything_in_express": tuple(COMPREHENSIVE_STAGES[: len(EXPRESS_STAGES)]) == EXPRESS_STAGES,
        "stages": stages,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def validate_comprehensive_contract(contract: dict[str, Any]) -> dict[str, Any]:
    stage_ids = [str(item.get("id")) for item in contract.get("stages") or [] if isinstance(item, dict)]
    missing_express = [stage for stage in EXPRESS_STAGES if stage not in stage_ids]
    missing_comprehensive = [stage for stage in COMPREHENSIVE_ONLY_STAGES if stage not in stage_ids]
    missing_terminal = [stage for stage in TERMINAL_STAGES if stage not in stage_ids]
    duplicate_stages = sorted({stage for stage in stage_ids if stage_ids.count(stage) > 1})

    violations: list[str] = []
    if contract.get("service_id") != "comprehensive":
        violations.append("service_id_must_be_comprehensive")
    if missing_express:
        violations.append("missing_express_stages")
    if missing_comprehensive:
        violations.append("missing_comprehensive_stages")
    if missing_terminal:
        violations.append("missing_terminal_stages")
    if duplicate_stages:
        violations.append("duplicate_stages")
    if contract.get("human_review_required") is not True:
        violations.append("human_review_required")
    if contract.get("client_delivery_allowed") is not False:
        violations.append("client_delivery_must_remain_blocked")
    for field in ("one_snapshot", "one_run_id", "one_evidence_ledger", "one_canonical_score", "one_final_report_package"):
        if contract.get(field) is not True:
            violations.append(f"{field}_required")

    return {
        "status": "valid" if not violations else "invalid",
        "artifact_schema": "nico.comprehensive_orchestration_validation.v2",
        "violations": violations,
        "missing_express_stages": missing_express,
        "missing_comprehensive_stages": missing_comprehensive,
        "missing_terminal_stages": missing_terminal,
        "duplicate_stages": duplicate_stages,
        "stage_count": len(stage_ids),
        "expected_stage_count": len(COMPREHENSIVE_STAGES),
    }


def stage_contract(contract: dict[str, Any], stage_id: str) -> dict[str, Any] | None:
    for item in contract.get("stages") or []:
        if isinstance(item, dict) and item.get("id") == stage_id:
            return deepcopy(item)
    return None


__all__ = [
    "COMPREHENSIVE_ONLY_STAGES",
    "COMPREHENSIVE_STAGES",
    "EXPRESS_STAGES",
    "TERMINAL_STAGES",
    "VERSION",
    "build_comprehensive_contract",
    "stage_contract",
    "validate_comprehensive_contract",
]
