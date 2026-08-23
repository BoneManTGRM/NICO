from __future__ import annotations

from typing import Any, Mapping

from nico import comprehensive_native_providers_v4 as scoring
from nico.provider_control_objective_parity_v1 import (
    install_provider_control_objective_parity,
)

VERSION = "nico.comprehensive-score-truth-scope.v5"


def _safe_sync_score_container(
    container: dict[str, Any],
    technical: int,
    adjusted: int,
) -> int:
    """Synchronize only assessment/report score aliases, never section contracts."""

    score_keys = {
        "technical_score": technical,
        "canonical_technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "canonical_evidence_adjusted_score": adjusted,
    }
    looks_like_score_container = bool(
        set(container) & set(score_keys)
        or isinstance(container.get("maturity_signal"), Mapping)
    )
    if not looks_like_score_container:
        return 0

    touched = 0
    for key, value in score_keys.items():
        if key in container or key in {
            "technical_score",
            "canonical_evidence_adjusted_score",
        }:
            if container.get(key) != value:
                touched += 1
            container[key] = value

    maturity = container.get("maturity_signal")
    if isinstance(maturity, dict):
        for key in ("score", "source_score", "presented_score", "technical_score"):
            if maturity.get(key) != technical:
                touched += 1
            maturity[key] = technical
        for key in (
            "evidence_adjusted_score",
            "canonical_evidence_adjusted_score",
            "evidence_readiness_score",
        ):
            if maturity.get(key) != adjusted:
                touched += 1
            maturity[key] = adjusted

    contract = container.get("score_contract")
    if isinstance(contract, dict):
        if contract.get("technical_score") != technical:
            touched += 1
        if contract.get("evidence_adjusted_score") != adjusted:
            touched += 1
        contract["technical_score"] = technical
        contract["evidence_adjusted_score"] = adjusted
    return touched


def install_score_truth_scope() -> dict[str, Any]:
    control_objective_parity = install_provider_control_objective_parity()
    scoring._sync_score_container = _safe_sync_score_container
    return {
        "version": VERSION,
        "bound": (
            scoring._sync_score_container is _safe_sync_score_container
            and control_objective_parity.get("bound") is True
        ),
        "section_score_contracts_preserved": True,
        "overall_score_aliases_synchronized": True,
        "provider_neutral_control_objectives": (
            control_objective_parity.get("provider_neutral_control_objectives") is True
        ),
        "unavailable_or_unassessed_capability_treated_as_failed": (
            control_objective_parity.get(
                "unavailable_or_unassessed_capability_treated_as_failed"
            )
            is False
        ),
        "mutable_operational_history_affects_technical_score": False,
        "control_objective_parity": control_objective_parity,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_score_truth_scope",
]
