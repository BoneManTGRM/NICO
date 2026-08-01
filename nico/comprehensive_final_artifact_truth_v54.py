from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico.comprehensive_scoring_manifest_v54 import assurance_factor

VERSION = "nico.comprehensive_final_artifact_truth.v54"
_MARKER = "_nico_comprehensive_final_artifact_truth_v54"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 100 else None


def _score_truth(canonical: dict[str, Any]) -> tuple[int | None, int | None]:
    assessment = _dict(canonical.get("assessment"))
    maturity = _dict(assessment.get("maturity_signal"))
    technical = next(
        (
            score
            for raw in (
                assessment.get("technical_score"),
                maturity.get("technical_score"),
                maturity.get("score"),
            )
            if (score := _score(raw)) is not None
        ),
        None,
    )
    adjusted = next(
        (
            score
            for raw in (
                assessment.get("canonical_evidence_adjusted_score"),
                assessment.get("evidence_adjusted_score"),
                maturity.get("canonical_evidence_adjusted_score"),
                maturity.get("evidence_adjusted_score"),
            )
            if (score := _score(raw)) is not None
        ),
        None,
    )
    return technical, adjusted


def weighted_score_diagnostics(canonical: dict[str, Any]) -> dict[str, Any]:
    """Recalculate both scores without treating a missing factor as verified.

    The v53 validator defaulted an absent assurance factor to 1.0. Older production
    score rows retained an assurance label but not the numeric factor, so a valid
    evidence-adjusted score below the technical score was incorrectly rejected.
    """

    assessment = _dict(canonical.get("assessment"))
    reconciliation = _dict(assessment.get("score_reconciliation"))
    source_rows = reconciliation.get("rows") or assessment.get("scoring_weights")
    rows = [row for row in _list(source_rows) if isinstance(row, dict)]
    included = [
        row
        for row in rows
        if row.get("included") is True and _score(row.get("technical_score")) is not None
    ]
    canonical_technical, canonical_adjusted = _score_truth(canonical)
    if not included:
        return {
            "matches": False,
            "reason": "included_scoring_rows_missing",
            "canonical_technical_score": canonical_technical,
            "canonical_evidence_adjusted_score": canonical_adjusted,
            "rows": [],
        }

    denominator = sum(float(row.get("weight") or 0.0) for row in included)
    if denominator <= 0:
        return {
            "matches": False,
            "reason": "included_weight_total_not_positive",
            "canonical_technical_score": canonical_technical,
            "canonical_evidence_adjusted_score": canonical_adjusted,
            "rows": [],
        }

    normalized_rows: list[dict[str, Any]] = []
    technical_numerator = 0.0
    adjusted_numerator = 0.0
    unknown_factor_rows: list[str] = []
    for row in included:
        score = _score(row.get("technical_score"))
        weight = float(row.get("weight") or 0.0)
        explicit = row.get("assurance_factor")
        factor: float | None
        source: str
        if isinstance(explicit, (int, float)) and not isinstance(explicit, bool):
            factor = float(explicit)
            source = "explicit"
        else:
            _, factor = assurance_factor(
                row.get("assurance_status"),
                row.get("assurance"),
                row.get("assurance_label"),
            )
            source = "derived_from_retained_assurance_status"
        if factor is None:
            unknown_factor_rows.append(str(row.get("section_id") or row.get("control") or "unknown"))
            continue
        technical_numerator += score * weight
        adjusted_numerator += score * factor * weight
        normalized_rows.append(
            {
                "section_id": row.get("section_id"),
                "technical_score": score,
                "weight": weight,
                "assurance_factor": factor,
                "assurance_factor_source": source,
            }
        )

    if unknown_factor_rows:
        return {
            "matches": False,
            "reason": "assurance_factor_unresolved",
            "unresolved_rows": unknown_factor_rows,
            "canonical_technical_score": canonical_technical,
            "canonical_evidence_adjusted_score": canonical_adjusted,
            "rows": normalized_rows,
        }

    recalculated_technical = round(technical_numerator / denominator)
    recalculated_adjusted = round(adjusted_numerator / denominator)
    return {
        "matches": (
            recalculated_technical == canonical_technical
            and recalculated_adjusted == canonical_adjusted
        ),
        "reason": "" if (
            recalculated_technical == canonical_technical
            and recalculated_adjusted == canonical_adjusted
        ) else "weighted_score_mismatch",
        "canonical_technical_score": canonical_technical,
        "canonical_evidence_adjusted_score": canonical_adjusted,
        "recalculated_technical_score": recalculated_technical,
        "recalculated_evidence_adjusted_score": recalculated_adjusted,
        "included_weight_total": denominator,
        "rows": normalized_rows,
    }


def validate_final_report_package(package: dict[str, Any]) -> dict[str, Any]:
    from nico.comprehensive_final_artifact_truth_v53 import (
        validate_final_report_package as validate_v53,
    )

    validation = deepcopy(validate_v53(package))
    canonical = _dict(package.get("json"))
    score_diagnostics = weighted_score_diagnostics(canonical)
    checks = _dict(validation.get("checks"))
    checks["weighted_scores_recompute"] = score_diagnostics["matches"] is True
    validation["checks"] = checks
    validation["score_recalculation"] = score_diagnostics
    failed = sorted(name for name, passed in checks.items() if passed is not True)
    validation.update(
        {
            "status": "verified" if not failed else "blocked",
            "version": VERSION,
            "failed_checks": failed,
            "missing_assurance_factor_defaults_to_verified": False,
            "assurance_factor_can_be_derived_from_retained_status": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return validation


def install_comprehensive_final_artifact_truth_v54() -> dict[str, Any]:
    from nico import comprehensive_cross_format_finality_v49 as cross_format
    from nico import comprehensive_native_providers as providers

    current: Callable[[dict[str, Any]], dict[str, Any]] = (
        cross_format.finality_aware_cross_format_verification_provider
    )
    if getattr(current, _MARKER, False):
        providers.cross_format_verification_provider = current
        return {"status": "already_installed", "version": VERSION, "bound": True}

    # Replace the v53 validation wrapper while preserving the original cross-format
    # identity/finality/score-parity provider underneath it.
    base_provider: Callable[[dict[str, Any]], dict[str, Any]] = getattr(
        current, "_nico_previous", current
    )

    @wraps(current)
    def verify(context: dict[str, Any]) -> dict[str, Any]:
        base = base_provider(context)
        final_stage = providers._prior(context, "final_comprehensive_report_generation")
        package, source = cross_format._report_package(final_stage)
        validation = validate_final_report_package(package)
        base_status = str(base.get("status") or "").casefold()
        if base_status in {"blocked", "failed", "error", "unavailable", "timed_out"}:
            output = deepcopy(base)
            output["final_artifact_truth"] = validation
            output["report_package_source"] = source
            return output
        if validation["status"] != "verified":
            return providers._result(
                context,
                "blocked",
                reason="final_artifact_truth_verification_failed",
                summary=(
                    "Final artifact truth verification failed: "
                    + ", ".join(validation["failed_checks"])
                ),
                report_package_source=source,
                final_artifact_truth=validation,
                failed_checks=validation["failed_checks"],
                evidence={
                    "failed_checks": validation["failed_checks"],
                    "score_recalculation": validation["score_recalculation"],
                },
            )
        output = deepcopy(base)
        output["final_artifact_truth"] = validation
        output["report_package_source"] = source
        evidence = _dict(output.get("evidence"))
        evidence.update(validation["checks"])
        evidence["score_recalculation"] = validation["score_recalculation"]
        output["evidence"] = evidence
        return output

    setattr(verify, _MARKER, True)
    setattr(verify, "_nico_previous", base_provider)
    cross_format.finality_aware_cross_format_verification_provider = verify
    providers.cross_format_verification_provider = verify
    return {
        "status": "installed",
        "version": VERSION,
        "bound": (
            cross_format.finality_aware_cross_format_verification_provider is verify
            and providers.cross_format_verification_provider is verify
        ),
        "missing_factor_never_defaults_to_verified": True,
        "retained_assurance_status_recalculation_supported": True,
        "failed_checks_exposed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_final_artifact_truth_v54",
    "validate_final_report_package",
    "weighted_score_diagnostics",
]
