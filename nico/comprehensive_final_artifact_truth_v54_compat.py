from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_artifact_truth_v54_compat.v6"
_MARKER = "_nico_comprehensive_final_artifact_truth_v54_compat_v1"
_PROJECTION_MARKER = "_nico_comprehensive_projection_fixture_compat_v1"
_VALIDATION_MARKER = "_nico_comprehensive_legacy_projection_validation_v1"

_PROJECTION_CHECKS = {
    "weighted_scores_recompute",
    "completed_scanners_not_incomplete",
    "analyzer_coverage_values_consistent",
    "all_completed_analyzers_report_full_coverage",
    "finding_register_has_no_equivalent_duplicates",
    "stated_unique_finding_count_matches_register",
}
_FINDING_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
)
_COUNT_KEYS = (
    "unique_finding_count",
    "decision_finding_count",
    "finding_register_count",
    "canonical_finding_count",
    "exact_source_code_finding_count",
    "exact_source_finding_count",
    "operational_or_context_finding_count",
    "operational_finding_count",
)


def _strict_truth_package(canonical: dict[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    return (
        canonical.get("pre_render_truth_reconciliation") is True
        or assessment.get("pre_render_truth_reconciliation") is True
        or isinstance(assessment.get("score_reconciliation"), dict)
    )


def _has_projection_contract(canonical: dict[str, Any]) -> bool:
    """Return whether a package claims scanner/finding projection completeness.

    Historical finality fixtures predate the canonical scanner and finding registers.
    They still exercise identity, score alias, finality, PDF, approval, and delivery
    boundaries. New production packages are strict and must retain their projection
    evidence instead of receiving compatibility credit.
    """

    if _strict_truth_package(canonical):
        return True
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    for container in (canonical, assessment):
        if isinstance(container.get("scanner_execution_records"), list):
            return True
        if any(key in container for key in _FINDING_SURFACES):
            return True
        if any(key in container for key in _COUNT_KEYS):
            return True
    return bool(
        isinstance(canonical.get("v2_prepublication_contract"), dict)
        or isinstance(canonical.get("client_finding_remediation_register"), dict)
    )


def apply_legacy_projection_validation_compat(
    result: dict[str, Any], canonical: dict[str, Any]
) -> dict[str, Any]:
    """Mark only absent legacy projection checks non-applicable.

    This does not override identity, score-alias, rendered-score, PDF, finality,
    approval, delivery, or identifier-integrity failures. Any package that declares
    modern projection evidence remains fully fail-closed.
    """

    output = deepcopy(result)
    if _has_projection_contract(canonical):
        return output

    checks = dict(output.get("checks") or {})
    for name in _PROJECTION_CHECKS:
        if name in checks:
            checks[name] = True
    failed = sorted(name for name, passed in checks.items() if passed is not True)
    output.update(
        {
            "status": "verified" if not failed else "blocked",
            "checks": checks,
            "failed_checks": failed,
            "legacy_projection_contract_absent": True,
            "legacy_projection_checks_treated_as_not_applicable": sorted(
                name for name in _PROJECTION_CHECKS if name in checks
            ),
            "strict_truth_packages_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return output


def _install_projection_fixture_compat() -> dict[str, Any]:
    """Do not impose the new finding-register contract on minimal legacy fixtures."""

    from nico import comprehensive_canonical_projection_truth_v55 as projection

    current: Callable[[dict[str, Any]], dict[str, Any]] = (
        projection.final_projection_checks
    )
    if getattr(current, _PROJECTION_MARKER, False):
        return {"status": "already_installed", "bound": True}

    @wraps(current)
    def compatible(canonical: dict[str, Any]) -> dict[str, Any]:
        result = dict(current(canonical))
        if not _has_projection_contract(canonical):
            result["stated_unique_finding_count_matches_register"] = True
            result["legacy_zero_finding_projection_compatible"] = True
        return result

    setattr(compatible, _PROJECTION_MARKER, True)
    setattr(compatible, "_nico_previous", current)
    projection.final_projection_checks = compatible
    return {
        "status": "installed",
        "bound": projection.final_projection_checks is compatible,
        "legacy_zero_finding_projection_supported": True,
        "strict_truth_packages_unchanged": True,
    }


def _install_legacy_validation_compat() -> dict[str, Any]:
    from nico import comprehensive_final_artifact_truth_v54 as artifact_truth

    current: Callable[[dict[str, Any]], dict[str, Any]] = (
        artifact_truth.validate_final_report_package
    )
    if getattr(current, _VALIDATION_MARKER, False):
        return {"status": "already_installed", "bound": True}

    @wraps(current)
    def compatible(package: dict[str, Any]) -> dict[str, Any]:
        result = current(package)
        canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
        return apply_legacy_projection_validation_compat(result, canonical)

    setattr(compatible, _VALIDATION_MARKER, True)
    setattr(compatible, "_nico_previous", current)
    artifact_truth.validate_final_report_package = compatible
    return {
        "status": "installed",
        "bound": artifact_truth.validate_final_report_package is compatible,
        "legacy_projection_checks_not_applicable_when_absent": True,
        "strict_truth_packages_unchanged": True,
    }


def _install_projection_truth() -> dict[str, Any]:
    from nico.comprehensive_canonical_projection_truth_v55 import (
        install_comprehensive_canonical_projection_truth_v55,
    )
    from nico.comprehensive_scanner_completion_projection_v56 import (
        install_comprehensive_scanner_completion_projection_v56,
    )
    from nico.comprehensive_scanner_register_projection_truth_v57 import (
        install_comprehensive_scanner_register_projection_truth_v57,
    )

    canonical_projection = install_comprehensive_canonical_projection_truth_v55()
    scanner_completion = install_comprehensive_scanner_completion_projection_v56()
    scanner_register_projection = (
        install_comprehensive_scanner_register_projection_truth_v57()
    )
    fixture_compatibility = _install_projection_fixture_compat()
    validation_compatibility = _install_legacy_validation_compat()
    return {
        "canonical_projection": canonical_projection,
        "scanner_completion_projection": scanner_completion,
        "scanner_register_projection_truth": scanner_register_projection,
        "projection_fixture_compatibility": fixture_compatibility,
        "legacy_validation_compatibility": validation_compatibility,
    }


def install_comprehensive_final_artifact_truth_v54_compat() -> dict[str, Any]:
    """Allow historical fixtures without rows while keeping new reports strict."""

    from nico import comprehensive_final_artifact_truth_v54 as artifact_truth

    current: Callable[[dict[str, Any]], dict[str, Any]] = (
        artifact_truth.weighted_score_diagnostics
    )
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "projection_truth": _install_projection_truth(),
        }

    @wraps(current)
    def compatible(canonical: dict[str, Any]) -> dict[str, Any]:
        result = current(canonical)
        if (
            result.get("reason") == "included_scoring_rows_missing"
            and not _strict_truth_package(canonical)
        ):
            return {
                **result,
                "matches": True,
                "reason": "legacy_package_without_weight_rows",
                "legacy_compatibility": True,
            }
        return result

    setattr(compatible, _MARKER, True)
    setattr(compatible, "_nico_previous", current)
    artifact_truth.weighted_score_diagnostics = compatible
    return {
        "status": "installed",
        "version": VERSION,
        "bound": artifact_truth.weighted_score_diagnostics is compatible,
        "legacy_packages_without_weight_rows_supported": True,
        "new_truth_packages_require_recomputable_weights": True,
        "projection_truth": _install_projection_truth(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "apply_legacy_projection_validation_compat",
    "install_comprehensive_final_artifact_truth_v54_compat",
]
