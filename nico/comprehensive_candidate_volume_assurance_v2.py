from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-candidate-volume-assurance.v3"
MODEL = "review-workload-observability-v3"
PENALTY_CAP = 0
_PENALTY_MARKER = "__nico_candidate_volume_penalty_v3__"
_PROVIDER_MARKER = "__nico_candidate_volume_provider_v3__"
_CLEANUP_MARKER = "__nico_candidate_volume_cleanup_v3__"


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _volume_band(total_review: int) -> str:
    if total_review <= 0:
        return "none"
    if total_review <= 99:
        return "1-99"
    if total_review <= 999:
        return "100-999"
    if total_review <= 9_999:
        return "1,000-9,999"
    return "10,000+"


def calibrated_candidate_volume_penalty(
    register: Mapping[str, Any],
) -> tuple[int, dict[str, int]]:
    """Compatibility API: candidate/reviewer workload has no numeric score effect.

    Phase 1 treats candidate volume, clustering and reviewer work units as operational
    workload/assurance context. The categories are still returned so downstream
    consumers retain deterministic shape, but every numeric score deduction is zero.
    """

    summary = (
        register.get("summary_by_category")
        if isinstance(register.get("summary_by_category"), Mapping)
        else {}
    )
    return 0, {str(category): 0 for category in summary}


def expose_candidate_workload_basis(result: Mapping[str, Any]) -> dict[str, Any]:
    """Expose candidate workload without translating it into a security/readiness score."""

    output = deepcopy(dict(result))
    assessment = (
        deepcopy(dict(output.get("assessment") or {}))
        if isinstance(output.get("assessment"), Mapping)
        else {}
    )
    contract = (
        deepcopy(dict(assessment.get("score_contract") or {}))
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )
    register = (
        assessment.get("canonical_scanner_finding_register")
        if isinstance(assessment.get("canonical_scanner_finding_register"), Mapping)
        else {}
    )
    summary = (
        register.get("summary_by_category")
        if isinstance(register.get("summary_by_category"), Mapping)
        else {}
    )
    active_categories = sorted(
        str(category)
        for category, values in summary.items()
        if isinstance(values, Mapping) and _integer(values.get("review_required")) > 0
    )
    totals = register.get("totals") if isinstance(register.get("totals"), Mapping) else {}
    review_required = _integer(totals.get("review_required"))
    confirmed_material = _integer(totals.get("material"))
    band = _volume_band(review_required)
    zeroes = {str(category): 0 for category in summary}
    basis = (
        "Candidate volume and reviewer workload are operational review metrics and have no "
        "numeric technical-maturity or Evidence-Adjusted score effect."
    )

    contract.update(
        {
            "candidate_volume_penalty_model": MODEL,
            "candidate_volume_penalty_cap": 0,
            "candidate_volume_penalty": 0,
            "candidate_volume_penalty_by_category": zeroes,
            "candidate_volume_review_required_total": review_required,
            "candidate_volume_confirmed_material_total": confirmed_material,
            "candidate_volume_active_review_categories": active_categories,
            "candidate_volume_active_category_count": len(active_categories),
            "candidate_volume_band": band,
            "candidate_volume_increment": 0,
            "candidate_volume_penalty_basis": basis,
            "candidate_volume_penalty_arithmetic_verified": True,
            "candidate_volume_is_triage_workload_not_defect_severity": True,
            "candidate_volume_affects_technical_score": False,
            "candidate_volume_affects_evidence_adjusted_score": False,
            "candidate_volume_affects_numeric_score": False,
            "review_workload_affects_numeric_score": False,
            "candidate_volume_affects_assurance_state": True,
        }
    )
    assessment["score_contract"] = contract

    coverage = (
        deepcopy(dict(assessment.get("evidence_coverage") or {}))
        if isinstance(assessment.get("evidence_coverage"), Mapping)
        else {}
    )
    coverage.update(
        {
            "candidate_volume_penalty_model": MODEL,
            "candidate_volume_penalty": 0,
            "candidate_volume_penalty_by_category": zeroes,
            "candidate_volume_review_required_total": review_required,
            "candidate_volume_band": band,
            "candidate_volume_increment": 0,
            "candidate_volume_penalty_basis": basis,
            "candidate_volume_is_triage_workload_not_defect_severity": True,
            "candidate_volume_affects_technical_score": False,
            "candidate_volume_affects_evidence_adjusted_score": False,
            "candidate_volume_affects_numeric_score": False,
            "review_workload_affects_numeric_score": False,
            "candidate_volume_affects_assurance_state": True,
        }
    )
    assessment["evidence_coverage"] = coverage

    technical = _integer(assessment.get("technical_score"))
    adjusted = _integer(assessment.get("evidence_adjusted_score"))
    assessment["executive_summary"] = (
        "Technical maturity remains based on exact-commit technical controls. "
        f"Evidence-Adjusted readiness is {adjusted}/100 versus technical maturity {technical}/100. "
        f"NICO retains {review_required} review-required candidates and {confirmed_material} confirmed "
        "material findings as explicit review context. Candidate volume, clustering and reviewer workload "
        "do not change numeric security or readiness scores."
    )
    output["assessment"] = assessment
    output["summary"] = assessment["executive_summary"]

    evidence = (
        deepcopy(dict(output.get("evidence") or {}))
        if isinstance(output.get("evidence"), Mapping)
        else {}
    )
    evidence.update(
        {
            "candidate_volume_penalty_model": MODEL,
            "candidate_volume_penalty": 0,
            "candidate_volume_review_required_total": review_required,
            "candidate_volume_confirmed_material_total": confirmed_material,
            "candidate_volume_active_category_count": len(active_categories),
            "candidate_volume_band": band,
            "candidate_volume_increment": 0,
            "candidate_volume_penalty_basis": basis,
            "candidate_volume_is_triage_workload_not_defect_severity": True,
            "candidate_volume_affects_numeric_score": False,
            "review_workload_affects_numeric_score": False,
        }
    )
    output["evidence"] = evidence
    return output


def _augment_contract(result: dict[str, Any]) -> dict[str, Any]:
    return expose_candidate_workload_basis(result)


def install_candidate_volume_assurance_v2() -> dict[str, Any]:
    from nico import comprehensive_final_six_client_report_cleanup_v1 as cleanup
    from nico import comprehensive_native_providers_v5 as providers

    current_penalty = providers._candidate_volume_penalty
    if not getattr(current_penalty, _PENALTY_MARKER, False):
        setattr(calibrated_candidate_volume_penalty, _PENALTY_MARKER, True)
        setattr(calibrated_candidate_volume_penalty, "_nico_previous", current_penalty)
        providers._candidate_volume_penalty = calibrated_candidate_volume_penalty

    if not getattr(cleanup.expose_candidate_penalty_basis, _CLEANUP_MARKER, False):
        replacement = expose_candidate_workload_basis
        setattr(replacement, _CLEANUP_MARKER, True)
        setattr(replacement, "_nico_previous", cleanup.expose_candidate_penalty_basis)
        cleanup.expose_candidate_penalty_basis = replacement

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
        "penalty_cap": 0,
        "penalty_bound": getattr(providers._candidate_volume_penalty, _PENALTY_MARKER, False),
        "provider_bound": getattr(providers.canonical_scoring_provider, _PROVIDER_MARKER, False),
        "cleanup_bound": getattr(cleanup.expose_candidate_penalty_basis, _CLEANUP_MARKER, False),
        "candidate_volume_affects_technical_score": False,
        "candidate_volume_affects_evidence_adjusted_score": False,
        "candidate_volume_affects_numeric_score": False,
        "review_workload_affects_numeric_score": False,
        "candidate_volume_affects_assurance_state": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MODEL",
    "PENALTY_CAP",
    "VERSION",
    "calibrated_candidate_volume_penalty",
    "expose_candidate_workload_basis",
    "install_candidate_volume_assurance_v2",
]
