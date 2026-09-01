from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico import comprehensive_canonical_projection_truth_v55 as projection

VERSION = "nico.comprehensive_requested_scanner_projection.v63"
_MARKER = "_nico_comprehensive_requested_scanner_projection_v63"
_ORIGINAL = projection._scanner_population


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _name(value: Any) -> str:
    return projection._scanner_name(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _requested(canonical: Mapping[str, Any]) -> list[str]:
    assessment = _mapping(canonical.get("assessment"))
    contract = _mapping(canonical.get("client_readiness_contract"))
    candidates = (
        canonical.get("live_scanner_evidence"),
        assessment.get("live_scanner_evidence"),
        canonical.get("scanner_run_summary"),
        assessment.get("scanner_run_summary"),
    )
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        values = candidate.get("tools_requested")
        if isinstance(values, (list, tuple, set)):
            names = list(dict.fromkeys(_name(item) for item in values if _name(item)))
            if names:
                return names
    values = contract.get("requested_exact_run_scanners")
    if isinstance(values, (list, tuple, set)):
        names = list(dict.fromkeys(_name(item) for item in values if _name(item)))
        if names:
            return names
    return []


def requested_scanner_population(
    canonical: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    """Project only scanners requested by the immutable exact-run manifest.

    Historical, stale, or compatibility scanner rows remain outside the active
    coverage denominator. When a requested tool has no retained row, an explicit
    missing row is created so absent evidence remains fail-closed rather than
    disappearing from coverage and incomplete-scanner counts.
    """

    records, _, _, _ = _ORIGINAL(canonical)
    requested = _requested(canonical)
    if not requested:
        return _ORIGINAL(canonical)
    authoritative_applicability = (
        projection._authoritative_scanner_applicability(canonical)
    )

    by_name = {
        _name(item.get("scanner_name") or item.get("tool")): deepcopy(dict(item))
        for item in records
        if _name(item.get("scanner_name") or item.get("tool"))
    }
    selected: list[dict[str, Any]] = []
    for name in requested:
        item = deepcopy(by_name.get(name) or {})
        if not item:
            item = {
                "scanner_name": name,
                "tool": name,
                "status": "missing",
                "state": "missing",
                "completed": False,
                "verified": False,
                "verified_complete": False,
                "verified_for_this_report": False,
                "exact_commit_match": False,
                "artifact_hash": "",
                "finding_count": 0,
                "findings": [],
                "failure_reason": (
                    f"{name} did not retain a complete exact-SHA scanner record."
                ),
                "failure_or_unavailable_reason": (
                    f"{name} did not retain a complete exact-SHA scanner record."
                ),
            }
        item["scanner_name"] = name
        item["requested_for_exact_run"] = True
        selected.append(item)

    applicable = [
        item
        for item in selected
        if item.get("applicable") is not False
        and _text(item.get("status") or item.get("state"))
        .casefold()
        .replace("-", "_")
        not in {"not_applicable", "not_required", "inapplicable"}
        and (
            authoritative_applicability is None
            or _name(item.get("scanner_name"))
            not in authoritative_applicability[0]
            or _name(item.get("scanner_name"))
            in authoritative_applicability[1]
        )
    ]
    completed = [item for item in applicable if item.get("completed") is True]
    incomplete = [item for item in applicable if item.get("completed") is not True]
    coverage = round(100 * len(completed) / len(applicable)) if applicable else 0
    return selected, completed, incomplete, coverage


def install_comprehensive_requested_scanner_projection_v62() -> dict[str, Any]:
    current = projection._scanner_population
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    setattr(requested_scanner_population, _MARKER, True)
    setattr(requested_scanner_population, "_nico_previous", current)
    projection._scanner_population = requested_scanner_population
    return {
        "status": "installed",
        "version": VERSION,
        "bound": projection._scanner_population is requested_scanner_population,
        "live_tools_requested_is_denominator": True,
        "unrequested_stale_records_excluded": True,
        "missing_requested_records_created_fail_closed": True,
        "existing_report_renderer_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_requested_scanner_projection_v62",
    "requested_scanner_population",
]
