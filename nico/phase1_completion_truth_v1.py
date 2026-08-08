from __future__ import annotations

import sys
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.phase1-completion-truth.v1"
SCORING_MODEL_VERSION = "technical-minus-evidence-completeness-deductions.v1"

_CURRENT_SCORE_EFFECT = (
    "Score effect: assurance-only while authorized human disposition remains pending; "
    "NICO automated technical triage is complete."
)
_LEGACY_SCORE_EFFECTS = (
    "Score effect: assurance-only until triaged.",
    "Score effect: assurance-only until triaged",
    "Assurance-only until triaged.",
    "Assurance-only until triaged",
)
_SCORE_MARKER_V4 = "_nico_phase1_score_truth_v4"
_SCORE_MARKER_V5 = "_nico_phase1_score_truth_v5"
_INSTALL_MARKER = "_nico_phase1_score_truth_install_v1"


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _rewrite_client_truth(value: Any) -> Any:
    """Rewrite only report/scoring text, never scanner/source evidence payloads."""

    if isinstance(value, str):
        output = value
        for legacy in _LEGACY_SCORE_EFFECTS:
            output = output.replace(legacy, _CURRENT_SCORE_EFFECT)
        return output
    if isinstance(value, list):
        return [_rewrite_client_truth(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite_client_truth(item) for item in value)
    if isinstance(value, Mapping):
        return {key: _rewrite_client_truth(item) for key, item in value.items()}
    return value


def _technical_score(assessment: Mapping[str, Any]) -> int:
    maturity = assessment.get("maturity_signal")
    if not isinstance(maturity, Mapping):
        maturity = {}
    return _integer(
        assessment.get("technical_score")
        or maturity.get("technical_score")
        or maturity.get("score")
    )


def normalize_phase1_scoring_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep reviewer workload out of numeric security/readiness scoring.

    Candidate volume, routing classes, clusters, and review work units remain visible
    operational assurance context. Only actual evidence-completeness failures may reduce
    the numeric Evidence-Adjusted score.
    """

    output = deepcopy(dict(payload))
    assessment = output.get("assessment")
    if not isinstance(assessment, Mapping):
        return output

    assessment = deepcopy(dict(assessment))
    technical = _technical_score(assessment)
    coverage = deepcopy(
        dict(assessment.get("evidence_coverage"))
        if isinstance(assessment.get("evidence_coverage"), Mapping)
        else {}
    )
    contract = deepcopy(
        dict(assessment.get("score_contract"))
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )

    payload_penalty = max(
        _integer(coverage.get("missing_raw_payload_penalty")),
        _integer(contract.get("missing_raw_payload_penalty")),
    )
    execution_penalty = max(
        _integer(coverage.get("incomplete_analyzer_penalty")),
        _integer(contract.get("incomplete_analyzer_penalty")),
    )
    evidence_completeness_penalty = payload_penalty + execution_penalty
    evidence_adjusted = max(0, technical - evidence_completeness_penalty)

    by_category = coverage.get("candidate_volume_penalty_by_category")
    if isinstance(by_category, Mapping):
        category_zeroes = {str(key): 0 for key in by_category}
    else:
        category_zeroes = {}

    common_truth = {
        "candidate_volume_penalty": 0,
        "candidate_volume_penalty_by_category": category_zeroes,
        "candidate_volume_increment": 0,
        "candidate_volume_affects_technical_score": False,
        "candidate_volume_affects_evidence_adjusted_score": False,
        "candidate_volume_affects_numeric_score": False,
        "review_workload_affects_numeric_score": False,
        "candidate_volume_affects_assurance_state": True,
        "candidate_volume_penalty_basis": (
            "Candidate volume and reviewer workload are operational review metrics and have no numeric score effect."
        ),
        "missing_raw_payload_penalty": payload_penalty,
        "incomplete_analyzer_penalty": execution_penalty,
        "evidence_completeness_penalty": evidence_completeness_penalty,
        "scoring_model_version": SCORING_MODEL_VERSION,
    }
    coverage.update(common_truth)
    assessment["evidence_coverage"] = coverage

    contract.update(common_truth)
    contract["technical_score"] = technical
    contract["evidence_adjusted_score"] = evidence_adjusted
    contract["assurance_penalty"] = evidence_completeness_penalty
    assessment["score_contract"] = contract

    assessment["technical_score"] = technical
    assessment["canonical_technical_score"] = technical
    assessment["canonical_evidence_adjusted_score"] = evidence_adjusted
    assessment["evidence_adjusted_score"] = evidence_adjusted
    assessment["score_formula"] = (
        f"{technical} - {payload_penalty} - {execution_penalty} = {evidence_adjusted}"
    )

    maturity = deepcopy(
        dict(assessment.get("maturity_signal"))
        if isinstance(assessment.get("maturity_signal"), Mapping)
        else {}
    )
    maturity["canonical_evidence_adjusted_score"] = evidence_adjusted
    maturity["evidence_adjusted_score"] = evidence_adjusted
    maturity["evidence_readiness_score"] = evidence_adjusted
    assessment["maturity_signal"] = maturity

    sections = assessment.get("sections")
    if isinstance(sections, list):
        assessment["sections"] = _rewrite_client_truth(sections)
    assessment["executive_summary"] = (
        f"Exact-SHA technical maturity is {technical}/100. Evidence-Adjusted readiness is "
        f"{evidence_adjusted}/100 after evidence-completeness deductions only. Candidate volume, "
        "technical-triage routing, clustering, and human-review workload are reported separately "
        "and have no numeric score effect."
    )
    output["assessment"] = assessment

    evidence = deepcopy(
        dict(output.get("evidence"))
        if isinstance(output.get("evidence"), Mapping)
        else {}
    )
    evidence.update(common_truth)
    evidence["technical_score"] = technical
    evidence["canonical_technical_score"] = technical
    evidence["evidence_adjusted_score"] = evidence_adjusted
    evidence["canonical_evidence_adjusted_score"] = evidence_adjusted
    evidence["score_formula"] = assessment["score_formula"]
    output["evidence"] = _rewrite_client_truth(evidence)
    output["summary"] = (
        "Canonical scoring completed from exact-SHA technical evidence. Reviewer workload and "
        "candidate volume remain operational assurance context and do not change numeric security "
        "or readiness scores; only actual evidence-completeness failures may reduce Evidence-Adjusted readiness."
    )
    output["phase1_scoring_truth"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "candidate_volume_numeric_score_effect": "none",
        "review_workload_numeric_score_effect": "none",
        "evidence_completeness_penalties_retained": True,
        "technical_triage_distinct_from_human_disposition": True,
        "human_approval_created": False,
        "client_delivery_allowed": False,
    }
    return output


def _replace_aliases(name: str, original: Any, replacement: Any) -> None:
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, name, None) is original:
                setattr(module, name, replacement)
        except Exception:
            continue


def _wrap_score_provider(module: Any, marker: str) -> bool:
    current = module.canonical_scoring_provider
    if getattr(current, marker, False):
        return True

    @wraps(current)
    def score_with_phase1_truth(context):
        return normalize_phase1_scoring_result(current(context))

    setattr(score_with_phase1_truth, marker, True)
    setattr(score_with_phase1_truth, "_nico_previous", current)
    module.canonical_scoring_provider = score_with_phase1_truth
    _replace_aliases("canonical_scoring_provider", current, score_with_phase1_truth)
    return True


def install_phase1_completion_truth_patch() -> dict[str, Any]:
    from nico import comprehensive_native_providers_v4 as v4
    from nico import comprehensive_native_providers_v5 as v5

    v4_bound = _wrap_score_provider(v4, _SCORE_MARKER_V4)
    v5_bound = _wrap_score_provider(v5, _SCORE_MARKER_V5)

    current_install = v5.install_native_comprehensive_providers
    if not getattr(current_install, _INSTALL_MARKER, False):

        @wraps(current_install)
        def install_with_phase1_truth(app):
            providers = current_install(app)
            status = dict(
                getattr(app.state, "nico_native_comprehensive_provider_status", {}) or {}
            )
            status.update(
                {
                    "phase1_completion_truth_bound": True,
                    "phase1_completion_truth_schema": VERSION,
                    "candidate_volume_affects_technical_score": False,
                    "candidate_volume_affects_evidence_adjusted_score": False,
                    "review_workload_affects_numeric_score": False,
                    "candidate_volume_affects_assurance_state": True,
                    "scoring_model_version": SCORING_MODEL_VERSION,
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            )
            app.state.nico_native_comprehensive_provider_status = status
            return providers

        setattr(install_with_phase1_truth, _INSTALL_MARKER, True)
        setattr(install_with_phase1_truth, "_nico_previous", current_install)
        v5.install_native_comprehensive_providers = install_with_phase1_truth
        _replace_aliases(
            "install_native_comprehensive_providers", current_install, install_with_phase1_truth
        )

    return {
        "status": "installed",
        "version": VERSION,
        "scoring_model_version": SCORING_MODEL_VERSION,
        "v4_score_provider_bound": v4_bound,
        "v5_score_provider_bound": v5_bound,
        "v5_installer_bound": getattr(
            v5.install_native_comprehensive_providers, _INSTALL_MARKER, False
        ),
        "candidate_volume_affects_numeric_score": False,
        "review_workload_affects_numeric_score": False,
        "human_approval_created": False,
        "client_delivery_allowed": False,
    }


__all__ = [
    "SCORING_MODEL_VERSION",
    "VERSION",
    "install_phase1_completion_truth_patch",
    "normalize_phase1_scoring_result",
]
