from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.score_assurance_export_final_compat.v2"
_RECORDS_MARKER = "_nico_final_score_records_v2"
_REQUIREMENTS_MARKER = "_nico_final_green_requirements_v2"
_REWRITE_MARKER = "_nico_final_markdown_rewrite_v2"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _ensure_record(item: dict[str, Any]) -> dict[str, Any]:
    item.setdefault("findings", [])
    item.setdefault("unavailable", [])
    item.setdefault("score_rationale", "")
    score = item.get("technical_score")
    item["verified_green"] = bool(
        item.get("directly_scored") is True
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and score >= 80
        and _text(item.get("assurance_status")).casefold() == "verified"
        and _text(item.get("canonical_status")).upper() == "GREEN"
    )
    return item


def _heading(item: dict[str, Any]) -> str:
    return (
        f"### {item['label']} — {item['technical_band_label']} "
        f"({item['technical_score_label']})\n"
        f"**Evidence assurance:** {item['assurance_label']} · "
        f"**Risk disposition:** {item['canonical_status']}"
    )


def _rewrite_markdown(document: str, records: list[dict[str, Any]]) -> str:
    output = document
    for raw in records:
        if not isinstance(raw, dict):
            continue
        item = _ensure_record(raw)
        label_value = str(item.get("label") or "")
        if not label_value:
            continue
        label = re.escape(label_value)
        pattern = re.compile(
            rf"(?m)^###[ \t]+{label}[ \t]+(?:—|-)[ \t]+[^\n(]+[ \t]*"
            rf"\((?:\d{{1,3}}[ \t]*/[ \t]*100|NOT[ \t]+SCORED)\)[ \t]*"
            rf"(?:\n\*\*Evidence assurance:\*\*[^\n]*)?"
        )
        output = pattern.sub(lambda _match: _heading(item), output, count=1)
    return output


def install_score_assurance_export_final_compat_v2() -> dict[str, Any]:
    from nico import express_score_assurance_export_v1 as target

    records_current: Callable[[dict[str, Any]], list[dict[str, Any]]] = target._records
    if not getattr(records_current, _RECORDS_MARKER, False):
        @wraps(records_current)
        def records(result: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                _ensure_record(item)
                for item in records_current(result)
                if isinstance(item, dict)
            ]

        setattr(records, _RECORDS_MARKER, True)
        setattr(records, "_nico_previous", records_current)
        target._records = records

    requirements_current: Callable[[dict[str, Any]], list[str]] = target._green_requirements
    if not getattr(requirements_current, _REQUIREMENTS_MARKER, False):
        @wraps(requirements_current)
        def requirements(item: dict[str, Any]) -> list[str]:
            return requirements_current(_ensure_record(item))

        setattr(requirements, _REQUIREMENTS_MARKER, True)
        setattr(requirements, "_nico_previous", requirements_current)
        target._green_requirements = requirements

    rewrite_current = target._rewrite_markdown_section_headings
    if not getattr(rewrite_current, _REWRITE_MARKER, False):
        setattr(_rewrite_markdown, _REWRITE_MARKER, True)
        setattr(_rewrite_markdown, "_nico_previous", rewrite_current)
        target._rewrite_markdown_section_headings = _rewrite_markdown

    return {
        "status": "installed",
        "version": VERSION,
        "verified_green_defensive_at_final_export": True,
        "markdown_heading_rewrite_bounded_to_one_line": True,
        "idempotent_assurance_lines": True,
        "thresholds_lowered": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_score_assurance_export_final_compat_v2"]
