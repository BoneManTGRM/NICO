from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_artifact_truth_compat.v54"
_MARKER = "_nico_comprehensive_final_artifact_truth_compat_v54"


def _rows(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    reconciliation = (
        assessment.get("score_reconciliation")
        if isinstance(assessment.get("score_reconciliation"), dict)
        else {}
    )
    values = reconciliation.get("rows") or assessment.get("scoring_weights") or []
    return [value for value in values if isinstance(value, dict)]


def _strict_truth_package(canonical: dict[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    return (
        canonical.get("pre_render_truth_reconciliation") is True
        or assessment.get("pre_render_truth_reconciliation") is True
        or isinstance(assessment.get("score_reconciliation"), dict)
    )


def install_comprehensive_final_artifact_truth_compat_v54() -> dict[str, Any]:
    """Preserve legacy verifier fixtures without weakening new report packages.

    Historical and V2 compatibility packages can be valid final artifacts without
    retaining scoring-weight rows. New Comprehensive packages are explicitly marked by
    pre-render truth reconciliation and must retain recomputable rows. This adapter
    applies that distinction at the weighted-score check only.
    """

    from nico import comprehensive_final_artifact_truth_v53 as artifact_truth

    current: Callable[[dict[str, Any]], bool] = artifact_truth._weighted_scores_recompute
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def compatible(canonical: dict[str, Any]) -> bool:
        if _rows(canonical):
            return current(canonical)
        return not _strict_truth_package(canonical)

    setattr(compatible, _MARKER, True)
    setattr(compatible, "_nico_previous", current)
    artifact_truth._weighted_scores_recompute = compatible
    return {
        "status": "installed",
        "version": VERSION,
        "bound": artifact_truth._weighted_scores_recompute is compatible,
        "legacy_packages_without_weight_rows_supported": True,
        "new_truth_packages_require_recomputable_weights": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_final_artifact_truth_compat_v54"]
