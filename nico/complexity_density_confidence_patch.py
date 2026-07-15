from __future__ import annotations

import math
from typing import Any

PATCH_VERSION = "nico.complexity_density_confidence.v1"
_MIN_DENSITY_SAMPLE_LOC = 50
_MARKER = "_nico_complexity_density_confidence_v1"


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def confidence_adjusted_file_complexity(item: dict[str, Any]) -> tuple[int, float]:
    """Return function risk and density with a bounded small-file confidence factor.

    Raw branch density is statistically unstable for tiny adapters: one branch in a
    one-line file equals 100 branches per 100 LOC even though the file is trivial.
    Function complexity remains fully counted. Density reaches full weight at 50 LOC
    and is proportionally confidence-adjusted below that threshold.
    """

    module_complexity = _int(item.get("cyclomatic_complexity"))
    max_function = _int(item.get("max_function_complexity"))
    function_count = _int(item.get("function_count"))
    loc = max(1, _int(item.get("loc")))
    if max_function <= 0:
        divisor = max(1, function_count)
        max_function = min(
            module_complexity,
            max(1, math.ceil((module_complexity / divisor) * 1.35)),
        )
    raw_density = (module_complexity / loc) * 100
    confidence = min(1.0, loc / _MIN_DENSITY_SAMPLE_LOC)
    adjusted_density = round(raw_density * confidence, 2)
    return max_function, adjusted_density


def install_complexity_density_confidence_patch() -> dict[str, Any]:
    from nico import complexity_score_integrity_patch as integrity

    current = integrity._effective_file_complexity
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "minimum_density_sample_loc": _MIN_DENSITY_SAMPLE_LOC,
        }
    setattr(confidence_adjusted_file_complexity, _MARKER, True)
    setattr(confidence_adjusted_file_complexity, "_nico_previous", current)
    integrity._effective_file_complexity = confidence_adjusted_file_complexity
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "minimum_density_sample_loc": _MIN_DENSITY_SAMPLE_LOC,
        "function_complexity_discounted": False,
        "small_file_density_confidence_adjusted": True,
        "guardrail": "Small files retain all measured function complexity; only density-derived risk is confidence-adjusted until the file reaches 50 source LOC.",
    }


__all__ = [
    "PATCH_VERSION",
    "confidence_adjusted_file_complexity",
    "install_complexity_density_confidence_patch",
]
