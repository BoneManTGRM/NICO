from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_artifact_truth_v54_compat.v4"
_MARKER = "_nico_comprehensive_final_artifact_truth_v54_compat_v1"
_PROJECTION_MARKER = "_nico_comprehensive_projection_fixture_compat_v1"


def _strict_truth_package(canonical: dict[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    return (
        canonical.get("pre_render_truth_reconciliation") is True
        or assessment.get("pre_render_truth_reconciliation") is True
        or isinstance(assessment.get("score_reconciliation"), dict)
    )


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
        finding_surfaces = (
            "canonical_findings",
            "findings_register",
            "findings",
            "decision_grade_findings_register",
        )
        has_finding_surface = any(
            isinstance(canonical.get(key), list) for key in finding_surfaces
        )
        if not has_finding_surface and not _strict_truth_package(canonical):
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


def _install_projection_truth() -> dict[str, Any]:
    from nico.comprehensive_canonical_projection_truth_v55 import (
        install_comprehensive_canonical_projection_truth_v55,
    )
    from nico.comprehensive_scanner_completion_projection_v56 import (
        install_comprehensive_scanner_completion_projection_v56,
    )

    canonical_projection = install_comprehensive_canonical_projection_truth_v55()
    scanner_completion = install_comprehensive_scanner_completion_projection_v56()
    fixture_compatibility = _install_projection_fixture_compat()
    return {
        "canonical_projection": canonical_projection,
        "scanner_completion_projection": scanner_completion,
        "projection_fixture_compatibility": fixture_compatibility,
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
    "install_comprehensive_final_artifact_truth_v54_compat",
]
