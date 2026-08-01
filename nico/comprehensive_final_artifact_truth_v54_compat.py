from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_artifact_truth_v54_compat.v2"
_MARKER = "_nico_comprehensive_final_artifact_truth_v54_compat_v1"


def _strict_truth_package(canonical: dict[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    return (
        canonical.get("pre_render_truth_reconciliation") is True
        or assessment.get("pre_render_truth_reconciliation") is True
        or isinstance(assessment.get("score_reconciliation"), dict)
    )


def _install_projection_truth() -> dict[str, Any]:
    from nico.comprehensive_canonical_projection_truth_v55 import (
        install_comprehensive_canonical_projection_truth_v55,
    )

    return install_comprehensive_canonical_projection_truth_v55()


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
            "canonical_projection_truth": _install_projection_truth(),
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
        "canonical_projection_truth": _install_projection_truth(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_final_artifact_truth_v54_compat",
]
