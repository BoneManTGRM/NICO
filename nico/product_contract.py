"""Canonical customer-facing product identity and maturity targets for NICO.

This module is intentionally small and dependency-free so API, CLI, frontend
contract tests, reporting, and release checks can share one product definition.
Legacy route or storage aliases may continue to exist internally during migration,
but they must not create a second customer-facing assessment product.
"""

from __future__ import annotations

from typing import Final

PRODUCT_NAME: Final = "NICO Comprehensive Technical Assessment"
CUSTOMER_FACING_ASSESSMENT: Final = "comprehensive"

INTERNAL_COMPLEXITY_CLASSES: Final[tuple[str, ...]] = (
    "small",
    "standard",
    "complex",
    "enterprise",
)

RETIRED_PUBLIC_TIER_LABELS: Final[tuple[str, ...]] = (
    "express",
    "mid",
    "full",
    "basic",
    "premium",
)

MATURE_AUTOMATION_TARGETS: Final[dict[str, float]] = {
    "evidence_collection_and_normalization": 0.98,
    "repeatable_technical_analysis_minimum": 0.95,
    "repeatable_technical_analysis_goal": 0.98,
    "finding_and_recommendation_preparation": 0.95,
    "report_production": 0.99,
    "cross_format_invariant_compliance": 0.995,
    "material_claim_evidence_support": 1.0,
    "remediation_planning": 0.95,
    "routine_case_progression": 0.95,
    "continuing_assurance": 0.95,
    "eligible_patch_development": 0.80,
}


def normalized_complexity(value: str) -> str:
    """Return a validated internal complexity classification."""

    normalized = str(value or "").strip().lower()
    if normalized not in INTERNAL_COMPLEXITY_CLASSES:
        allowed = ", ".join(INTERNAL_COMPLEXITY_CLASSES)
        raise ValueError(f"unsupported assessment complexity {value!r}; expected one of: {allowed}")
    return normalized


def maturity_target(name: str) -> float:
    """Return one declared target without allowing an unknown metric silently."""

    try:
        return MATURE_AUTOMATION_TARGETS[name]
    except KeyError as exc:
        raise KeyError(f"unknown NICO maturity target: {name}") from exc
