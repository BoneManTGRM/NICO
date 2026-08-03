from __future__ import annotations

import math
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-candidate-volume-assurance.v2"
MODEL = "triage-workload-logarithmic-v2"
PENALTY_CAP = 6
_PENALTY_MARKER = "__nico_candidate_volume_penalty_v2__"
_PROVIDER_MARKER = "__nico_candidate_volume_provider_v2__"


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def calibrated_candidate_volume_penalty(
    register: Mapping[str, Any],
) -> tuple[int, dict[str, int]]:
    """Measure unresolved triage workload without implying defect severity.

    Each active candidate category contributes one assurance point because it
    requires a distinct review workflow. Total volume contributes only a bounded
    logarithmic increment after the population passes the next order-of-magnitude
    threshold. This avoids counting hundreds of untriaged candidates as hundreds
    of confirmed defects while still distinguishing a large queue from a small one.
    """

    summary = (
        register.get("summary_by_category")
        if isinstance(register.get("summary_by_category"), Mapping)
        else {}
    )
    review_by_category = {
        str(category): _integer(raw.get("review_required"))
        for category, raw in summary.items()
        if isinstance(raw, Mapping) and _integer(raw.get("review_required")) > 0
    }
    if not review_by_category:
        return 0, {str(category): 0 for category in summary}

    penalties = {category: 1 for category in review_by_category}
    total_review = sum(review_by_category.values())
    volume_increment = min(
        3,
        max(0, math.ceil(math.log10(total_review + 1)) - 2),
    )
    if volume_increment:
        largest = max(
            review_by_category,
            key=lambda category: (review_by_category[category], category),
        )
        penalties[largest] += volume_increment

    penalty = min(PENALTY_CAP, sum(penalties.values()))
    if penalty < sum(penalties.values()):
        overflow = sum(penalties.values()) - penalty
        for category in sorted(
            penalties,
            key=lambda item: (penalties[item], review_by_category[item]),
            reverse=True,
        ):
            reducible = max(0, penalties[category] - 1)
            reduction = min(reducible, overflow)
            penalties[category] -= reduction
            overflow -= reduction
            if overflow == 0:
                break

    return penalty, {
        str(category): penalties.get(str(category), 0)
        for category in summary
    }


def _augment_contract(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    assessment = (
        deepcopy(dict(output.get("assessment") or {}))
        if isinstance(output.get("assessment"), dict)
        else {}
    )
    contract = (
        deepcopy(dict(assessment.get("score_contract") or {}))
        if isinstance(assessment.get("score_contract"), dict)
        else {}
    )
    register = (
        assessment.get("canonical_scanner_finding_register")
        if isinstance(assessment.get("canonical_scanner_finding_register"), dict)
        else {}
    )
    totals = register.get("totals") if isinstance(register.get("totals"), dict) else {}
    review_required = _integer(totals.get("review_required"))
    confirmed_material = _integer(totals.get("material"))
    penalty = _integer(contract.get("candidate_volume_penalty"))

    contract.update(
        {
            "candidate_volume_penalty_model": MODEL,
            "candidate_volume_penalty_cap": PENALTY_CAP,
            "candidate_volume_review_required_total": review_required,
            "candidate_volume_confirmed_material_total": confirmed_material,
            "candidate_volume_is_triage_workload_not_defect_severity": True,
            "candidate_volume_penalty_rationale": (
                "One assurance point per active candidate category plus a bounded "
                "logarithmic workload increment; candidate count does not imply "
                "confirmed defect severity or technical deterioration."
            ),
        }
    )
    assessment["score_contract"] = contract

    coverage = (
        deepcopy(dict(assessment.get("evidence_coverage") or {}))
        if isinstance(assessment.get("evidence_coverage"), dict)
        else {}
    )
    coverage.update(
        {
            "candidate_volume_penalty_model": MODEL,
            "candidate_volume_penalty": penalty,
            "candidate_volume_is_triage_workload_not_defect_severity": True,
        }
    )
    assessment["evidence_coverage"] = coverage

    technical = assessment.get("technical_score")
    adjusted = assessment.get("evidence_adjusted_score")
    assessment["executive_summary"] = (
        "Technical maturity remains based on exact-commit technical controls. "
        f"Evidence-adjusted readiness is {adjusted}/100 versus technical maturity "
        f"{technical}/100 after a {penalty}-point candidate-triage workload penalty, "
        f"with {review_required} review-required candidates and "
        f"{confirmed_material} confirmed material findings. Candidate volume affects "
        "assurance only and is not evidence that the repository materially worsened."
    )
    output["assessment"] = assessment
    output["summary"] = assessment["executive_summary"]

    evidence = (
        deepcopy(dict(output.get("evidence") or {}))
        if isinstance(output.get("evidence"), dict)
        else {}
    )
    evidence.update(
        {
            "candidate_volume_penalty_model": MODEL,
            "candidate_volume_penalty": penalty,
            "candidate_volume_review_required_total": review_required,
            "candidate_volume_confirmed_material_total": confirmed_material,
            "candidate_volume_is_triage_workload_not_defect_severity": True,
        }
    )
    output["evidence"] = evidence
    return output


def install_candidate_volume_assurance_v2() -> dict[str, Any]:
    from nico import comprehensive_native_providers_v5 as providers

    current_penalty = providers._candidate_volume_penalty
    if not getattr(current_penalty, _PENALTY_MARKER, False):
        setattr(calibrated_candidate_volume_penalty, _PENALTY_MARKER, True)
        setattr(calibrated_candidate_volume_penalty, "_nico_previous", current_penalty)
        providers._candidate_volume_penalty = calibrated_candidate_volume_penalty

    current_provider = providers.canonical_scoring_provider
    if not getattr(current_provider, _PROVIDER_MARKER, False):

        @wraps(current_provider)
        def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
            return _augment_contract(current_provider(context))

        setattr(canonical_scoring_provider, _PROVIDER_MARKER, True)
        setattr(canonical_scoring_provider, "_nico_previous", current_provider)
        providers.canonical_scoring_provider = canonical_scoring_provider

    return {
        "status": "installed",
        "version": VERSION,
        "model": MODEL,
        "penalty_cap": PENALTY_CAP,
        "penalty_bound": getattr(
            providers._candidate_volume_penalty,
            _PENALTY_MARKER,
            False,
        ),
        "provider_bound": getattr(
            providers.canonical_scoring_provider,
            _PROVIDER_MARKER,
            False,
        ),
        "candidate_volume_affects_technical_score": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MODEL",
    "PENALTY_CAP",
    "VERSION",
    "calibrated_candidate_volume_penalty",
    "install_candidate_volume_assurance_v2",
]
