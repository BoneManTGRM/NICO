from __future__ import annotations

from typing import Any, Mapping

from nico import v2_pipeline_adapter_legacy as _legacy
from nico.v2_authoritative_report_truth import repair_canonical_truth_in_place

_ORIGINAL_BUILD_CANONICAL_ASSESSMENT = _legacy.build_canonical_assessment


def __getattr__(name: str) -> Any:
    return getattr(_legacy, name)


def _build_authoritative_canonical_assessment(report: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _ORIGINAL_BUILD_CANONICAL_ASSESSMENT(report)
    repair_canonical_truth_in_place(canonical)
    return canonical


# The preserved production adapter calculates the canonical hash only after this
# function returns, so all repaired score, scanner, dependency, scope, and
# finality truth is included in every cross-format identity.
_legacy.build_canonical_assessment = _build_authoritative_canonical_assessment
apply_v2_pipeline = _legacy.apply_v2_pipeline


__all__ = ["apply_v2_pipeline"]
