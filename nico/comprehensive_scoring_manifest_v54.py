from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_scoring_manifest.v54"
_MARKER = "_nico_comprehensive_scoring_manifest_v54"

_FACTOR_BY_STATUS = {
    "verified": 1.00,
    "complete": 1.00,
    "partial": 0.98,
    "review_limited": 0.95,
    "reviewlimited": 0.95,
    "blocked": 0.85,
    "unavailable": 0.85,
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _status(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def assurance_factor(*values: Any) -> tuple[str, float | None]:
    """Return the explicit evidence-assurance state and its deterministic factor."""

    for value in values:
        normalized = _status(value)
        if normalized in {"not_applicable", "not_scored", ""}:
            continue
        if normalized in _FACTOR_BY_STATUS:
            canonical = "review_limited" if normalized == "reviewlimited" else normalized
            return canonical, _FACTOR_BY_STATUS[normalized]
    return "unavailable", 0.85


def enrich_scoring_rows(
    rows: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {
        _text(section.get("id")): section
        for section in sections
        if isinstance(section, dict) and _text(section.get("id"))
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = deepcopy(raw)
        section = by_id.get(_text(row.get("section_id")), {})
        status, factor = assurance_factor(
            row.get("assurance_status"),
            section.get("assurance_status"),
            row.get("assurance"),
            row.get("assurance_label"),
            section.get("assurance_label"),
        )
        row["assurance_status"] = status
        row["assurance_factor"] = factor if row.get("included") is True else None
        row["assurance_factor_source"] = VERSION
        enriched.append(row)
    return enriched


def _wrap_weighted_maturity(
    delegate: Callable[[list[dict[str, Any]]], tuple[int | None, list[dict[str, Any]]]],
) -> Callable[[list[dict[str, Any]]], tuple[int | None, list[dict[str, Any]]]]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def weighted(
        sections: list[dict[str, Any]],
    ) -> tuple[int | None, list[dict[str, Any]]]:
        technical, rows = delegate(sections)
        return technical, enrich_scoring_rows(rows, sections)

    setattr(weighted, _MARKER, True)
    setattr(weighted, "_nico_previous", delegate)
    return weighted


def install_comprehensive_scoring_manifest_v54() -> dict[str, Any]:
    from nico import comprehensive_premium_synthesis_v6 as premium

    current = premium._weighted_maturity
    wrapped = _wrap_weighted_maturity(current)
    premium._weighted_maturity = wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": premium._weighted_maturity is wrapped,
        "explicit_assurance_factor_per_included_control": True,
        "weighted_scores_independently_recomputable": True,
        "score_floor_added": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assurance_factor",
    "enrich_scoring_rows",
    "install_comprehensive_scoring_manifest_v54",
]
