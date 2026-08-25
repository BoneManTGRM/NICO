from __future__ import annotations

from typing import Any, Mapping

from nico import comprehensive_commercial_ship_projection_v1 as v1

VERSION = "nico.comprehensive_commercial_ship_projection.v2"


def _deployment_metric_order_independent(value: str) -> bool:
    text = str(value or "")
    if v1._COMBINED_DEPLOYMENT.search(text):
        return True
    patterns = (
        *v1._OBSERVED_PATTERNS,
        *v1._SUCCESS_PATTERNS,
        *v1._FAILED_PATTERNS,
        *v1._REMAINDER_PATTERNS,
    )
    return any(pattern.search(text) for pattern in patterns)


# v1 owns the bounded renderer/route patch. Correct only its presentation-line
# classifier before any projection or installer is used. No canonical data changes.
v1._is_deployment_metric = _deployment_metric_order_independent


def project_canonical_for_client_presentation(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    return v1.project_canonical_for_client_presentation(canonical)


def compact_sparse_limitation_pages(pdf_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    return v1.compact_sparse_limitation_pages(pdf_bytes)


def install_comprehensive_commercial_ship_projection_v2() -> dict[str, Any]:
    result = dict(v1.install_comprehensive_commercial_ship_projection_v1())
    result.update(
        {
            "version": VERSION,
            "deployment_metric_detection_order_independent": True,
            "canonical_truth_mutated": False,
            "assessment_rerun": False,
            "approval_state_mutated": False,
            "delivery_state_mutated": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return result


__all__ = [
    "VERSION",
    "compact_sparse_limitation_pages",
    "install_comprehensive_commercial_ship_projection_v2",
    "project_canonical_for_client_presentation",
]
