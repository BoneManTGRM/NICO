from __future__ import annotations

from copy import deepcopy
from typing import Any

VERSION = "nico.service_catalog.v1"

EXPRESS = "express"
COMPREHENSIVE = "comprehensive"
MONITOR_EXECUTE = "monitor_execute"

CUSTOMER_ASSESSMENT_SERVICES = (EXPRESS, COMPREHENSIVE)
CUSTOMER_SERVICE_ORDER = (EXPRESS, COMPREHENSIVE, MONITOR_EXECUTE)

_ALIAS_MAP = {
    "express": EXPRESS,
    "rapid": EXPRESS,
    "baseline": EXPRESS,
    "mid": COMPREHENSIVE,
    "full": COMPREHENSIVE,
    "deep": COMPREHENSIVE,
    "comprehensive": COMPREHENSIVE,
    "retainer": MONITOR_EXECUTE,
    "monitor": MONITOR_EXECUTE,
    "execute": MONITOR_EXECUTE,
    "monitor_execute": MONITOR_EXECUTE,
    "monitor+execute": MONITOR_EXECUTE,
}

SERVICE_CATALOG: dict[str, dict[str, Any]] = {
    EXPRESS: {
        "id": EXPRESS,
        "customer_name": "NICO Express Technical Assessment",
        "category": "assessment",
        "customer_selectable": True,
        "summary": "Fast, evidence-bound technical baseline and prioritized risk report.",
        "coverage_target": "90-95%",
        "internal_execution_profiles": ["express"],
        "stages": [
            "repository_and_delivery_evidence",
            "dependency_security_static_analysis",
            "architecture_complexity_velocity",
            "decision_report_and_human_review",
        ],
    },
    COMPREHENSIVE: {
        "id": COMPREHENSIVE,
        "customer_name": "NICO Comprehensive Technical Assessment",
        "category": "assessment",
        "customer_selectable": True,
        "summary": "Complete technical diligence, QA, operating-model, roadmap, and resourcing assessment.",
        "coverage_target": "75-85% initially; increase with connected QA, stakeholder, and production evidence",
        "internal_execution_profiles": ["mid", "full"],
        "stages": [
            "core_technical_scan",
            "deep_evidence_analysis",
            "functional_qa_and_platform_parity",
            "deployment_and_infrastructure_review",
            "stakeholder_and_business_alignment",
            "developer_delivery_process_review",
            "six_month_roadmap_and_resourcing",
            "human_review_and_final_delivery",
        ],
    },
    MONITOR_EXECUTE: {
        "id": MONITOR_EXECUTE,
        "customer_name": "NICO Monitor + Execute",
        "category": "recurring_operations",
        "customer_selectable": False,
        "summary": "Ongoing oversight, approved remediation, release verification, and roadmap execution.",
        "coverage_target": "Measured from connected operating evidence",
        "internal_execution_profiles": ["monitor", "retainer", "execute"],
        "stages": [
            "continuous_monitoring",
            "approved_repair_execution",
            "release_verification",
            "roadmap_delivery",
            "human_approval_and_audit_log",
        ],
    },
}


def normalize_service_id(value: Any, *, default: str = EXPRESS) -> str:
    key = str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")
    return _ALIAS_MAP.get(key, default)


def customer_assessment_catalog() -> list[dict[str, Any]]:
    return [deepcopy(SERVICE_CATALOG[service_id]) for service_id in CUSTOMER_ASSESSMENT_SERVICES]


def full_customer_catalog() -> list[dict[str, Any]]:
    return [deepcopy(SERVICE_CATALOG[service_id]) for service_id in CUSTOMER_SERVICE_ORDER]


def apply_customer_service_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the canonical customer-facing service identity without deleting legacy execution profiles.

    Existing Mid and Full identifiers remain available as internal execution profiles and API aliases.
    Customer-facing outputs receive one Comprehensive identity so historical endpoints and retained
    records can migrate safely without presenting three overlapping assessment products.
    """

    source = payload.get("internal_execution_profile") or payload.get("assessment_type") or payload.get("service_tier")
    canonical = normalize_service_id(source)
    service = SERVICE_CATALOG[canonical]

    source_text = str(source or canonical).strip().casefold()
    if canonical == COMPREHENSIVE and source_text in {"mid", "full", "deep"}:
        payload.setdefault("internal_execution_profile", source_text)
    else:
        payload.setdefault("internal_execution_profile", canonical)

    payload["service_id"] = canonical
    payload["service_tier"] = canonical
    payload["customer_service_name"] = service["customer_name"]
    payload["customer_service_category"] = service["category"]
    payload["customer_selectable_assessment"] = canonical in CUSTOMER_ASSESSMENT_SERVICES
    payload["service_catalog_version"] = VERSION
    payload["legacy_service_alias_preserved"] = source_text != canonical
    return payload


__all__ = [
    "COMPREHENSIVE",
    "CUSTOMER_ASSESSMENT_SERVICES",
    "EXPRESS",
    "MONITOR_EXECUTE",
    "SERVICE_CATALOG",
    "VERSION",
    "apply_customer_service_identity",
    "customer_assessment_catalog",
    "full_customer_catalog",
    "normalize_service_id",
]
