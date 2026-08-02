from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from nico.comprehensive_canonical_projection_truth_v55 import (
    normalize_final_projection,
)

VERSION = "nico.comprehensive_final_publication_truth.v58"
_MARKER = "_nico_comprehensive_final_publication_truth_v58"


def _score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 100 else None


def _authoritative_scores(canonical: Mapping[str, Any]) -> tuple[int | None, int | None]:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    reconciliation = (
        assessment.get("score_reconciliation")
        if isinstance(assessment.get("score_reconciliation"), Mapping)
        else {}
    )
    canonical_contract = (
        assessment.get("canonical_score_contract")
        if isinstance(assessment.get("canonical_score_contract"), Mapping)
        else {}
    )
    comprehensive_truth = (
        assessment.get("comprehensive_score_truth")
        if isinstance(assessment.get("comprehensive_score_truth"), Mapping)
        else {}
    )
    maturity = (
        assessment.get("maturity_signal")
        if isinstance(assessment.get("maturity_signal"), Mapping)
        else {}
    )
    technical = next(
        (
            score
            for value in (
                reconciliation.get("technical_score"),
                canonical_contract.get("technical_score"),
                comprehensive_truth.get("technical_score"),
                assessment.get("technical_score"),
                maturity.get("technical_score"),
                maturity.get("score"),
            )
            if (score := _score(value)) is not None
        ),
        None,
    )
    adjusted = next(
        (
            score
            for value in (
                reconciliation.get("canonical_evidence_adjusted_score"),
                canonical_contract.get("evidence_adjusted_score"),
                comprehensive_truth.get("canonical_evidence_adjusted_score"),
                comprehensive_truth.get("evidence_adjusted_score"),
                assessment.get("canonical_evidence_adjusted_score"),
                assessment.get("evidence_adjusted_score"),
                maturity.get("canonical_evidence_adjusted_score"),
                maturity.get("evidence_adjusted_score"),
            )
            if (score := _score(value)) is not None
        ),
        None,
    )
    return technical, adjusted


def _synchronize_score_contract(canonical: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(canonical)
    assessment = (
        deepcopy(dict(output.get("assessment")))
        if isinstance(output.get("assessment"), Mapping)
        else {}
    )
    technical, adjusted = _authoritative_scores(output)
    if technical is None or adjusted is None:
        output["assessment"] = assessment
        return output

    score_contract = (
        deepcopy(dict(assessment.get("score_contract")))
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )
    prior_adjusted = _score(score_contract.get("evidence_adjusted_score"))
    prior_penalty = _score(score_contract.get("assurance_penalty"))
    canonical_penalty = max(0, technical - adjusted)
    if prior_adjusted is not None and prior_adjusted != adjusted:
        score_contract["pre_reconciliation_evidence_adjusted_score"] = prior_adjusted
    if prior_penalty is not None and prior_penalty != canonical_penalty:
        score_contract["pre_reconciliation_assurance_penalty"] = prior_penalty
    score_contract.update(
        {
            "technical_score": technical,
            "evidence_adjusted_score": adjusted,
            "canonical_evidence_adjusted_score": adjusted,
            "assurance_penalty": canonical_penalty,
            "evidence_penalty_points": canonical_penalty,
            "canonical_score_reconciled": True,
            "canonical_score_source": "assessment.score_reconciliation",
            "score_override_allowed": False,
        }
    )
    assessment["score_contract"] = score_contract
    output["assessment"] = assessment
    return output


def _restore_rich_remediation_register(
    output: dict[str, Any],
    original: Mapping[str, Any] | None,
    *,
    canonical_total: int,
) -> dict[str, Any]:
    """Preserve render-only remediation fields while synchronizing count truth.

    ``normalize_final_projection`` deliberately projects canonical findings into the
    remediation-register surfaces. Those canonical findings contain client acceptance
    criteria but not the register's richer ``verification`` and ``exit_criteria``
    fields consumed by the Markdown and PDF renderers. Keep the already normalized,
    deduplicated register produced by ``client_report_completion_v2._install_register``
    and update only its count summary.
    """

    if not isinstance(original, Mapping):
        return output
    register = deepcopy(dict(original))
    code = [
        item
        for item in register.get("code_findings") or []
        if isinstance(item, Mapping)
    ]
    operational = [
        item
        for item in register.get("operational_findings") or []
        if isinstance(item, Mapping)
    ]
    register_total = len(code) + len(operational)
    if register_total != canonical_total:
        raise ValueError(
            "final remediation register diverged from canonical finding population: "
            f"{register_total} != {canonical_total}"
        )
    summary = (
        deepcopy(dict(register.get("summary")))
        if isinstance(register.get("summary"), Mapping)
        else {}
    )
    summary.update(
        {
            "decision_finding_count": canonical_total,
            "finding_register_count": canonical_total,
            "canonical_finding_count": canonical_total,
            "exact_source_code_finding_count": len(code),
            "operational_or_context_finding_count": len(operational),
            "final_register_count_synchronized_before_render": True,
            "rich_verification_fields_preserved_for_rendering": True,
        }
    )
    register["summary"] = summary
    output["client_finding_remediation_register"] = register
    return output


def synchronize_final_publication_truth(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Finalize count and score aliases before Markdown, HTML, and PDF rendering.

    The final remediation-register rebuild can change the canonical finding population
    after an earlier projection pass. Re-run the canonical projection immediately after
    that rebuild so the top-level unique count and every mirrored count describe the
    exact register that is about to be rendered. Preserve the rich verification fields
    in the already normalized remediation register, and reconcile the legacy score
    contract to the independently recomputable canonical score at the same boundary.
    """

    rich_register = (
        deepcopy(dict(canonical.get("client_finding_remediation_register")))
        if isinstance(canonical.get("client_finding_remediation_register"), Mapping)
        else None
    )
    output = normalize_final_projection(canonical)
    output = _synchronize_score_contract(output)
    findings = [
        item
        for item in output.get("canonical_findings") or []
        if isinstance(item, Mapping)
    ]
    total = len(findings)
    output = _restore_rich_remediation_register(
        output,
        rich_register,
        canonical_total=total,
    )
    output["unique_finding_count"] = total
    output["finding_register_count"] = total
    output["canonical_finding_count"] = total
    contract = (
        deepcopy(dict(output.get("v2_prepublication_contract")))
        if isinstance(output.get("v2_prepublication_contract"), Mapping)
        else {}
    )
    contract.update(
        {
            "version": VERSION,
            "canonical_finding_count": total,
            "final_register_count_synchronized_before_render": True,
            "rich_verification_fields_preserved_for_rendering": True,
            "legacy_score_contract_reconciled_before_render": True,
            "scores_changed_to_satisfy_gate": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    output["v2_prepublication_contract"] = contract
    return output


def install_comprehensive_final_publication_truth_v58() -> dict[str, Any]:
    """Bind the final canonical reconciliation inside the real client finalizer."""

    from nico import client_report_completion_v2 as completion

    current: Callable[[dict[str, Any]], dict[str, Any]] = completion._install_register
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def install_register(canonical: dict[str, Any]) -> dict[str, Any]:
        registered = current(canonical)
        return synchronize_final_publication_truth(registered)

    setattr(install_register, _MARKER, True)
    setattr(install_register, "_nico_previous", current)
    completion._install_register = install_register
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion._install_register is install_register,
        "final_register_count_synchronized_before_render": True,
        "rich_verification_fields_preserved_for_rendering": True,
        "legacy_score_contract_reconciled_before_render": True,
        "final_artifacts_rebuilt_from_reconciled_canonical_truth": True,
        "scores_changed_to_satisfy_gate": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_final_publication_truth_v58",
    "synchronize_final_publication_truth",
]
