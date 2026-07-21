from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class HardeningScenario(str, Enum):
    CLEAN = "clean"
    VULNERABLE = "vulnerable"
    PARTIAL_ACCESS = "partial_access"
    TIMEOUT = "timeout"
    PROVIDER_OUTAGE = "provider_outage"
    REVOKED_APPROVAL = "revoked_approval"
    INTERRUPTED_RUN = "interrupted_run"
    LARGE_REPOSITORY = "large_repository"
    LARGE_EVIDENCE_PACKET = "large_evidence_packet"
    ACCESSIBILITY = "accessibility"
    PSEUDO_LOCALIZATION = "pseudo_localization"


@dataclass(frozen=True)
class PerformanceBudget:
    max_runtime_seconds: float
    max_peak_memory_mb: float
    max_artifact_bytes: int


@dataclass(frozen=True)
class HardeningObservation:
    scenario: HardeningScenario
    exact_sha: str
    status: str
    terminal: bool
    human_review_required: bool
    client_delivery_allowed: bool
    runtime_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    artifact_bytes: int = 0
    evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class HardeningVerdict:
    scenario: HardeningScenario
    passed: bool
    issues: tuple[str, ...]


REQUIRED_SCENARIOS: tuple[HardeningScenario, ...] = tuple(HardeningScenario)


def _truthy(mapping: Mapping[str, Any], key: str) -> bool:
    return mapping.get(key) is True


def evaluate_observation(
    observation: HardeningObservation,
    *,
    expected_sha: str,
    budget: PerformanceBudget | None = None,
) -> HardeningVerdict:
    issues: list[str] = []
    evidence = observation.evidence or {}
    if not observation.exact_sha or observation.exact_sha != expected_sha:
        issues.append("hardening_exact_sha_mismatch")
    if not observation.human_review_required:
        issues.append("hardening_human_review_must_remain_required")
    if observation.client_delivery_allowed:
        issues.append("hardening_client_delivery_must_remain_blocked")

    adverse = {
        HardeningScenario.PARTIAL_ACCESS,
        HardeningScenario.TIMEOUT,
        HardeningScenario.PROVIDER_OUTAGE,
        HardeningScenario.REVOKED_APPROVAL,
        HardeningScenario.INTERRUPTED_RUN,
    }
    if observation.scenario in adverse:
        if observation.status not in {"blocked", "partial", "failed", "interrupted", "review_required"}:
            issues.append("hardening_adverse_scenario_must_fail_closed")
        if observation.client_delivery_allowed:
            issues.append("hardening_adverse_delivery_forbidden")
    else:
        if not observation.terminal:
            issues.append("hardening_success_scenario_must_terminalize")
        if observation.status not in {"complete", "passed", "human_review_pending"}:
            issues.append("hardening_success_status_invalid")

    if observation.scenario is HardeningScenario.REVOKED_APPROVAL:
        if not _truthy(evidence, "approval_revoked"):
            issues.append("hardening_revoked_approval_evidence_required")
        if _truthy(evidence, "delivery_available"):
            issues.append("hardening_revocation_must_remove_delivery")

    if observation.scenario is HardeningScenario.INTERRUPTED_RUN:
        if not _truthy(evidence, "restart_identity_preserved"):
            issues.append("hardening_restart_identity_proof_required")
        if not _truthy(evidence, "idempotent_continuation"):
            issues.append("hardening_idempotent_continuation_required")

    if observation.scenario is HardeningScenario.ACCESSIBILITY:
        required = (
            "keyboard",
            "screen_reader",
            "contrast",
            "reduced_motion",
            "semantic_headings",
            "focus_order",
        )
        for key in required:
            if not _truthy(evidence, key):
                issues.append(f"hardening_accessibility_missing:{key}")

    if observation.scenario is HardeningScenario.PSEUDO_LOCALIZATION:
        for key in ("route_parity", "translation_key_parity", "long_string_layout", "no_untranslated_copy"):
            if not _truthy(evidence, key):
                issues.append(f"hardening_localization_missing:{key}")

    if budget is not None:
        if observation.runtime_seconds > budget.max_runtime_seconds:
            issues.append("hardening_runtime_budget_exceeded")
        if observation.peak_memory_mb > budget.max_peak_memory_mb:
            issues.append("hardening_memory_budget_exceeded")
        if observation.artifact_bytes > budget.max_artifact_bytes:
            issues.append("hardening_artifact_budget_exceeded")

    return HardeningVerdict(observation.scenario, not issues, tuple(issues))


def evaluate_matrix(
    observations: Iterable[HardeningObservation],
    *,
    expected_sha: str,
    budgets: Mapping[HardeningScenario, PerformanceBudget] | None = None,
) -> dict[str, Any]:
    by_scenario: dict[HardeningScenario, HardeningObservation] = {}
    duplicates: list[str] = []
    for observation in observations:
        if observation.scenario in by_scenario:
            duplicates.append(observation.scenario.value)
        by_scenario[observation.scenario] = observation

    verdicts: list[HardeningVerdict] = []
    missing: list[str] = []
    for scenario in REQUIRED_SCENARIOS:
        observation = by_scenario.get(scenario)
        if observation is None:
            missing.append(scenario.value)
            continue
        verdicts.append(
            evaluate_observation(
                observation,
                expected_sha=expected_sha,
                budget=(budgets or {}).get(scenario),
            )
        )

    passed = not missing and not duplicates and all(item.passed for item in verdicts)
    return {
        "status": "passed" if passed else "failed",
        "expected_sha": expected_sha,
        "required_scenarios": [item.value for item in REQUIRED_SCENARIOS],
        "missing_scenarios": missing,
        "duplicate_scenarios": duplicates,
        "verdicts": [
            {
                "scenario": item.scenario.value,
                "passed": item.passed,
                "issues": list(item.issues),
            }
            for item in verdicts
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "HardeningObservation",
    "HardeningScenario",
    "HardeningVerdict",
    "PerformanceBudget",
    "REQUIRED_SCENARIOS",
    "evaluate_matrix",
    "evaluate_observation",
]
