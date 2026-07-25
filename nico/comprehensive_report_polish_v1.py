from __future__ import annotations

import unicodedata
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_report_polish.v1"
_PATCH_MARKER = "_nico_comprehensive_report_polish_v1"


def _clean_text(value: Any, limit: int = 1800) -> str:
    raw = str(value or "")
    safe = "".join(
        " " if character.isspace() else character
        for character in raw
        if not unicodedata.category(character).startswith("C")
    )
    normalized = " ".join(safe.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _clean_object(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return [_clean_object(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_object(item) for key, item in value.items()}
    return value


def _friendly_title(record: dict[str, Any]) -> str:
    title = _clean_text(record.get("title"), 420)
    lowered = title.casefold()
    location = _clean_text(record.get("location"), 520).casefold()

    if "failed to create new os thread" in lowered or "newosproc" in lowered:
        return "OSV scanner worker resource limit prevented completion"
    if "tool failed without stdout" in lowered:
        return "Dependency analyzer failed without diagnostic output"
    if "dependabot-missing-cooldown" in lowered or "missing cooldown" in lowered:
        return "Dependabot configuration is missing a cooldown policy"
    if "github-actions-mutable-action-tag" in lowered or "mutable action tag" in lowered:
        return "GitHub Actions workflow uses a mutable action tag"
    if "python_eval_exec" in lowered or "dynamic code execution" in lowered:
        if any(suffix in location for suffix in (".ts:", ".tsx:", ".js:", ".jsx:")):
            return "Potential dynamic execution pattern requires TypeScript source review"
        return "Potential dynamic execution pattern requires source review"
    return title or "Technical finding requires review"


def _sanitize_finding(record: dict[str, Any]) -> dict[str, Any]:
    output = {key: _clean_object(value) for key, value in record.items()}
    output["title"] = _friendly_title(output)
    category = _clean_text(output.get("category"), 80).casefold()
    evidence = _clean_text(output.get("evidence"), 900)
    title = _clean_text(output.get("title"), 420).casefold()
    unverified = "verified=false" in evidence.casefold()
    pattern_review = "potential dynamic execution pattern" in title

    if unverified or pattern_review:
        output["priority"] = "P2"
        output["confidence"] = "moderate"
        output["impact"] = (
            "The retained pattern is not a confirmed defect. Exact-source review is required before remediation or escalation."
        )
    if category == "static" and unverified:
        output["recommendation"] = (
            "Validate the grouped rule against the exact files and revision, then remediate confirmed instances or approve a bounded exception."
        )
    return output


def _group_review_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    indexes: dict[tuple[str, str, str], int] = {}
    locations: dict[tuple[str, str, str], list[str]] = {}

    for record in records:
        category = _clean_text(record.get("category"), 80).casefold()
        priority = _clean_text(record.get("priority"), 20).upper()
        title = _clean_text(record.get("title"), 420)
        may_group = category in {"code", "static"} and priority == "P2"
        key = (category, priority, title.casefold())
        location = _clean_text(record.get("location"), 520)

        if not may_group or key not in indexes:
            indexes[key] = len(grouped)
            locations[key] = [location] if location else []
            grouped.append(dict(record))
            continue

        target = grouped[indexes[key]]
        if location and location not in locations[key]:
            locations[key].append(location)
        count = len(locations[key])
        target["title"] = f"{title} ({count} locations)"
        target["location"] = "; ".join(locations[key][:10])
        target["evidence"] = _clean_text(
            f"{target.get('evidence')}; grouped_exact_locations={count}",
            900,
        )
        target["id"] = f"{_clean_text(target.get('id'), 200)}-grouped"

    return grouped


def polish_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    output = _clean_object(assessment)
    findings = [
        _sanitize_finding(item)
        for item in output.get("findings_register") or []
        if isinstance(item, dict)
    ]
    output["findings_register"] = _group_review_candidates(findings)
    output["comprehensive_report_polish"] = {
        "version": VERSION,
        "control_characters_removed": True,
        "raw_scanner_failures_summarized": True,
        "unverified_candidates_not_p1": True,
        "equivalent_review_candidates_grouped": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def install_comprehensive_report_polish_v1() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report

    current_decorate: Callable[[dict[str, Any]], dict[str, Any]] = report._decorate_assessment
    if getattr(current_decorate, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "unverified_candidates_not_p1": True,
            "equivalent_review_candidates_grouped": True,
        }

    @wraps(current_decorate)
    def decorate(assessment: dict[str, Any]) -> dict[str, Any]:
        return polish_assessment(current_decorate(assessment))

    setattr(decorate, _PATCH_MARKER, True)
    report._decorate_assessment = decorate
    return {
        "status": "installed",
        "version": VERSION,
        "control_characters_removed": True,
        "raw_scanner_failures_summarized": True,
        "unverified_candidates_not_p1": True,
        "equivalent_review_candidates_grouped": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_clean_text",
    "polish_assessment",
    "install_comprehensive_report_polish_v1",
]
