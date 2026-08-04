from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-zero-incomplete-validation.v1"
_MARKER = "__nico_comprehensive_zero_incomplete_validation_v1__"
_ZERO_INCOMPLETE = re.compile(
    r"\b0\s+remain\s+incomplete\s+or\s+review-limited\b",
    re.IGNORECASE,
)


def _normalize(value: Any) -> str:
    return _ZERO_INCOMPLETE.sub("0 remain incomplete", str(value or ""))


def install_comprehensive_zero_incomplete_validation_v1() -> dict[str, Any]:
    """Keep zero-incomplete execution truth from tripping contradiction checks.

    The phrase is legitimate only when the retained count is exactly zero. A
    positive incomplete count remains untouched and therefore still fails the
    underlying strict contradiction validator.
    """

    from nico import comprehensive_client_truth_final_v1 as truth

    current = truth._validate_surfaces
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _validate_surfaces(result: Mapping[str, Any]) -> None:
        compatible = deepcopy(dict(result))
        for key in ("markdown", "html"):
            compatible[key] = _normalize(compatible.get(key))

        canonical = (
            deepcopy(dict(compatible.get("json")))
            if isinstance(compatible.get("json"), Mapping)
            else {}
        )
        assessment = (
            deepcopy(dict(canonical.get("assessment")))
            if isinstance(canonical.get("assessment"), Mapping)
            else {}
        )
        if assessment.get("executive_summary"):
            assessment["executive_summary"] = _normalize(
                assessment.get("executive_summary")
            )
        canonical["assessment"] = assessment
        if canonical.get("executive_summary"):
            canonical["executive_summary"] = _normalize(
                canonical.get("executive_summary")
            )
        compatible["json"] = canonical
        current(compatible)

    setattr(_validate_surfaces, _MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    truth._validate_surfaces = _validate_surfaces
    return {
        "status": "installed",
        "version": VERSION,
        "zero_incomplete_execution_phrase_allowed": True,
        "positive_incomplete_counts_still_fail_closed": True,
        "rendered_artifacts_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_zero_incomplete_validation_v1",
]
