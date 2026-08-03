from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive-finding-count-truth.v66"

_CANONICAL_COUNT_KEYS = {
    "canonical_finding_count",
    "decision_grade_finding_count",
    "unique_finding_count",
    "stated_unique_finding_count",
    "canonical_record_count",
}
_EXACT_SOURCE_COUNT_KEYS = {
    "exact_source_finding_count",
    "exact_source_findings",
}
_OPERATIONAL_COUNT_KEYS = {
    "operational_context_finding_count",
    "operational_context_findings",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _replace_count_prose(
    value: str,
    *,
    canonical_count: int,
    exact_source_count: int,
    operational_count: int,
    top_title: str,
) -> str:
    output = value
    output = re.sub(
        r"The canonical register contains\s+\d+\s+unique decision-grade findings?\.",
        f"The canonical register contains {canonical_count} unique decision-grade finding"
        + ("." if canonical_count == 1 else "s."),
        output,
        flags=re.I,
    )
    output = re.sub(
        r"Exact-source findings:\s*\d+",
        f"Exact-source findings: {exact_source_count}",
        output,
        flags=re.I,
    )
    output = re.sub(
        r"Operational/context findings:\s*\d+",
        f"Operational/context findings: {operational_count}",
        output,
        flags=re.I,
    )
    output = re.sub(
        r"Canonical findings:\s*\d+",
        f"Canonical findings: {canonical_count}",
        output,
        flags=re.I,
    )
    output = re.sub(
        r"Canonical finding count:\s*\d+",
        f"Canonical finding count: {canonical_count}",
        output,
        flags=re.I,
    )
    if canonical_count:
        replacement = (
            f"Priority finding retained: {top_title}"
            if canonical_count == 1 and top_title
            else f"{min(5, canonical_count)} priority findings retained; see the Executive Risk Register."
        )
        output = re.sub(
            r"No unresolved priority finding retained",
            replacement,
            output,
            flags=re.I,
        )
        output = re.sub(
            r"No canonical actionable finding was retained\.",
            f"{canonical_count} canonical actionable finding"
            + (" was" if canonical_count == 1 else "s were")
            + " retained.",
            output,
            flags=re.I,
        )
    return output


def _reconcile_value(
    value: Any,
    *,
    canonical_count: int,
    exact_source_count: int,
    operational_count: int,
    top_title: str,
    depth: int = 0,
) -> Any:
    if depth > 16:
        return deepcopy(value)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.casefold()
            if normalized in _CANONICAL_COUNT_KEYS:
                output[key] = canonical_count
            elif normalized in _EXACT_SOURCE_COUNT_KEYS:
                output[key] = exact_source_count
            elif normalized in _OPERATIONAL_COUNT_KEYS:
                output[key] = operational_count
            elif normalized in {
                "scanner_execution_records",
                "review_candidate_register",
                "review_candidate_summary",
            }:
                output[key] = deepcopy(child)
            else:
                output[key] = _reconcile_value(
                    child,
                    canonical_count=canonical_count,
                    exact_source_count=exact_source_count,
                    operational_count=operational_count,
                    top_title=top_title,
                    depth=depth + 1,
                )
        return output
    if isinstance(value, list):
        return [
            _reconcile_value(
                child,
                canonical_count=canonical_count,
                exact_source_count=exact_source_count,
                operational_count=operational_count,
                top_title=top_title,
                depth=depth + 1,
            )
            for child in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _reconcile_value(
                child,
                canonical_count=canonical_count,
                exact_source_count=exact_source_count,
                operational_count=operational_count,
                top_title=top_title,
                depth=depth + 1,
            )
            for child in value
        )
    if isinstance(value, str):
        return _replace_count_prose(
            value,
            canonical_count=canonical_count,
            exact_source_count=exact_source_count,
            operational_count=operational_count,
            top_title=top_title,
        )
    return deepcopy(value)


def reconcile_finding_count_truth(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Synchronize report-stage finding count aliases with restored canonical truth."""

    output = deepcopy(dict(canonical))
    findings = [
        item
        for item in output.get("canonical_findings") or []
        if isinstance(item, Mapping)
    ]
    canonical_count = len(findings)
    exact_source_count = sum(
        bool(_text(item.get("exact_source") or item.get("location")))
        for item in findings
    )
    operational_count = max(0, canonical_count - exact_source_count)
    top_title = _text(
        findings[0].get("title") or findings[0].get("decision_title")
    ) if findings else ""

    output["stage_summaries"] = _reconcile_value(
        output.get("stage_summaries") or [],
        canonical_count=canonical_count,
        exact_source_count=exact_source_count,
        operational_count=operational_count,
        top_title=top_title,
    )
    assessment = (
        output.get("assessment")
        if isinstance(output.get("assessment"), Mapping)
        else {}
    )
    assessment = _reconcile_value(
        assessment,
        canonical_count=canonical_count,
        exact_source_count=exact_source_count,
        operational_count=operational_count,
        top_title=top_title,
    )
    assessment["decision_grade_finding_count"] = canonical_count
    assessment["exact_source_finding_count"] = exact_source_count
    assessment["operational_context_finding_count"] = operational_count
    output["assessment"] = assessment
    output["decision_grade_finding_count"] = canonical_count
    output["exact_source_finding_count"] = exact_source_count
    output["operational_context_finding_count"] = operational_count

    manifest = {
        "version": VERSION,
        "canonical_finding_count": canonical_count,
        "exact_source_finding_count": exact_source_count,
        "operational_context_finding_count": operational_count,
        "stage_summary_aliases_reconciled": True,
        "scanner_finding_counts_preserved": True,
        "review_candidate_counts_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    output["finding_count_truth"] = deepcopy(manifest)
    assessment["finding_count_truth"] = deepcopy(manifest)
    return output, manifest


__all__ = [
    "VERSION",
    "reconcile_finding_count_truth",
]
