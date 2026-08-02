from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive_zero_finding_finality_truth.v1"
_MARKER = "_nico_comprehensive_zero_finding_finality_truth_v1"
_COUNT_KEYS = frozenset(
    {
        "unique_finding_count",
        "decision_finding_count",
        "finding_register_count",
        "canonical_finding_count",
    }
)
_PRIMARY_COUNT_KEYS = (
    "unique_finding_count",
    "finding_register_count",
    "canonical_finding_count",
)
_FINDING_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
)


def _walk_key_values(value: Any, key_name: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) == key_name:
                found.append(child)
            found.extend(_walk_key_values(child, key_name))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_key_values(child, key_name))
    return found


def _explicit_empty_finding_register(canonical: Mapping[str, Any]) -> bool:
    present = [
        canonical.get(key)
        for key in _FINDING_SURFACES
        if key in canonical and isinstance(canonical.get(key), list)
    ]
    if not present:
        return False
    return all(
        not [item for item in surface if isinstance(item, Mapping)]
        for surface in present
    )


def _zero_count_contract_is_consistent(canonical: Mapping[str, Any]) -> bool:
    if not _explicit_empty_finding_register(canonical):
        return False
    if any(
        key not in canonical
        or canonical.get(key) != 0
        or isinstance(canonical.get(key), bool)
        for key in _PRIMARY_COUNT_KEYS
    ):
        return False
    stated_values = {
        int(value)
        for key in _COUNT_KEYS
        for value in _walk_key_values(canonical, key)
        if isinstance(value, int) and not isinstance(value, bool)
    }
    return stated_values == {0}


def reconcile_zero_finding_projection(
    canonical: Mapping[str, Any],
    checks: Mapping[str, Any],
) -> dict[str, Any]:
    """Permit a real, explicit zero-finding register without weakening count truth.

    The v55 projection verifier historically required ``bool(findings)`` before it
    could accept the finding-count invariant. That correctly rejected missing legacy
    contracts, but it also rejected a fully explicit canonical register containing zero
    confirmed material findings with every mirrored count synchronized to zero.

    This boundary changes only that empty-register case. Missing finding surfaces,
    absent primary count aliases, nonzero stale aliases, and all nonempty registers keep
    the existing fail-closed result.
    """

    output = deepcopy(dict(checks))
    canonical_count = output.get("canonical_finding_count")
    explicit_empty = _explicit_empty_finding_register(canonical)
    consistent = (
        canonical_count == 0
        and not isinstance(canonical_count, bool)
        and _zero_count_contract_is_consistent(canonical)
    )
    if explicit_empty and canonical_count == 0:
        output["stated_unique_finding_count_matches_register"] = consistent
        output["zero_finding_register_explicit"] = True
        output["zero_finding_count_contract_consistent"] = consistent
        output["zero_finding_contract_version"] = VERSION
    return output


def install_comprehensive_zero_finding_finality_truth_v1() -> dict[str, Any]:
    """Bind zero-finding truth into the live v55 final projection verifier."""

    from nico import comprehensive_canonical_projection_truth_v55 as projection

    current: Callable[[Mapping[str, Any]], dict[str, Any]] = (
        projection.final_projection_checks
    )
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "explicit_zero_finding_register_supported": True,
            "missing_register_remains_blocked": True,
            "stale_nonzero_count_remains_blocked": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def final_projection_checks(canonical: Mapping[str, Any]) -> dict[str, Any]:
        return reconcile_zero_finding_projection(canonical, current(canonical))

    setattr(final_projection_checks, _MARKER, True)
    setattr(final_projection_checks, "_nico_previous", current)
    projection.final_projection_checks = final_projection_checks
    return {
        "status": "installed",
        "version": VERSION,
        "bound": projection.final_projection_checks is final_projection_checks,
        "explicit_zero_finding_register_supported": True,
        "missing_register_remains_blocked": True,
        "stale_nonzero_count_remains_blocked": True,
        "nonempty_register_semantics_unchanged": True,
        "scores_changed": False,
        "scanner_results_changed": False,
        "findings_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_zero_finding_finality_truth_v1",
    "reconcile_zero_finding_projection",
]
