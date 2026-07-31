from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico import client_finding_remediation_register_v1 as v1

VERSION = "nico.client-finding-remediation-register.v4"
_CANONICAL_DECISION_FIELDS = (
    "finding_id",
    "priority",
    "category",
    "status",
    "title",
    "interpretation",
    "business_impact",
    "recommended_correction",
    "owner_role",
    "effort",
    "rollback",
)
_GENERIC_EXIT_CRITERION = (
    "All listed verification requirements pass on the exact remediation commit, "
    "the exact-SHA rerun no longer reports the condition as unresolved material risk, "
    "and no new material regression is introduced."
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _identity_token(value: Any) -> str:
    text = _text(value).casefold().replace("_", "-")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _record_key(item: Mapping[str, Any]) -> tuple[str, str, int, str]:
    category = _identity_token(item.get("category"))
    path = _text(item.get("path")).casefold().replace("\\", "/")
    line = int(item.get("line") or 0)
    technical_identity = _identity_token(
        item.get("rule_id")
        or item.get("symbol")
        or item.get("problematic_code")
        or item.get("title")
    )
    if path and line:
        return "code", path, line, technical_identity
    return category, "", 0, _identity_token(
        item.get("finding_id")
        or item.get("title")
        or item.get("observed_evidence")
    )


def _quality(item: Mapping[str, Any]) -> tuple[int, ...]:
    source = _text(item.get("record_source")).casefold()
    return (
        int(bool(item.get("artifact_hash"))),
        int(bool(item.get("source_excerpt"))),
        int(item.get("exact_commit_match") is True),
        int(source == "canonical_finding"),
        int(bool(item.get("rule_id"))),
        int(bool(item.get("symbol"))),
        len(_text(item.get("observed_evidence"))),
        len(_text(item.get("recommended_correction"))),
    )


def _dedupe_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    output: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _distinct_verification_and_exit(item: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(item))
    verification = _dedupe_list(result.get("verification") or [])
    exits = _dedupe_list(result.get("exit_criteria") or [])
    verification_keys = {value.casefold() for value in verification}
    unique_exits = [value for value in exits if value.casefold() not in verification_keys]
    if exits and not unique_exits:
        unique_exits = [_GENERIC_EXIT_CRITERION]
    result["verification"] = verification
    result["exit_criteria"] = unique_exits
    result["verification_and_exit_criteria_distinct"] = True
    return result


def _canonical_source(left: Mapping[str, Any], right: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for item in (left, right):
        if _text(item.get("record_source")).casefold() == "canonical_finding":
            return item
    return None


def _merge(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    preferred, other = (right, left) if _quality(right) > _quality(left) else (left, right)
    result = deepcopy(dict(preferred))
    for field, value in other.items():
        if result.get(field) in (None, "", [], {}):
            result[field] = deepcopy(value)

    canonical = _canonical_source(left, right)
    if canonical is not None:
        for field in _CANONICAL_DECISION_FIELDS:
            value = canonical.get(field)
            if value not in (None, "", [], {}):
                result[field] = deepcopy(value)

    result["verification"] = _dedupe_list(
        [*list(result.get("verification") or []), *list(other.get("verification") or [])]
    )
    result["exit_criteria"] = _dedupe_list(
        [*list(result.get("exit_criteria") or []), *list(other.get("exit_criteria") or [])]
    )
    aliases = [
        *list(result.get("finding_aliases") or []),
        result.get("finding_id"),
        *list(other.get("finding_aliases") or []),
        other.get("finding_id"),
    ]
    result["finding_aliases"] = _dedupe_list(aliases)
    result["record_sources"] = _dedupe_list(
        [
            *list(result.get("record_sources") or []),
            result.get("record_source"),
            *list(other.get("record_sources") or []),
            other.get("record_source"),
        ]
    )
    result["duplicate_sources_consolidated"] = True
    return _distinct_verification_and_exit(result)


def _consolidate(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    order: list[tuple[str, str, int, str]] = []
    for raw in values:
        item = _distinct_verification_and_exit(raw)
        key = _record_key(item)
        if key not in selected:
            selected[key] = item
            order.append(key)
        else:
            selected[key] = _merge(selected[key], item)
    return [selected[key] for key in order]


def normalize_finding_remediation_register(register: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(register))
    code = _consolidate(
        item for item in result.get("code_findings") or [] if isinstance(item, Mapping)
    )
    operational = _consolidate(
        item for item in result.get("operational_findings") or [] if isinstance(item, Mapping)
    )
    excluded = _consolidate(
        item
        for item in result.get("excluded_non_production_findings") or []
        if isinstance(item, Mapping)
    )
    code.sort(
        key=lambda item: (
            item.get("priority") not in {"P0", "P1"},
            _text(item.get("path")),
            int(item.get("line") or 0),
            _text(item.get("finding_id")),
        )
    )
    operational.sort(
        key=lambda item: (
            item.get("priority") not in {"P0", "P1"},
            _text(item.get("title")),
        )
    )
    summary = deepcopy(dict(result.get("summary") or {}))
    before = int(summary.get("deduplicated_record_count") or 0)
    all_records = [*code, *operational]
    summary.update(
        {
            "register_normalization_version": VERSION,
            "records_before_cross_source_consolidation": before,
            "records_after_cross_source_consolidation": len(code) + len(operational) + len(excluded),
            "cross_source_duplicates_consolidated": max(
                0,
                before - (len(code) + len(operational) + len(excluded)),
            ),
            "exact_source_code_finding_count": len(code),
            "operational_or_context_finding_count": len(operational),
            "excluded_non_production_count": len(excluded),
            "semantic_duplicate_code_anchors_absent": len(
                {_record_key(item) for item in code}
            )
            == len(code),
            "verification_and_exit_criteria_distinct": all(
                item.get("verification_and_exit_criteria_distinct") is True
                for item in all_records
            ),
        }
    )
    result.update(
        {
            "version": VERSION,
            "code_findings": code,
            "operational_findings": operational,
            "excluded_non_production_findings": excluded,
            "summary": summary,
        }
    )
    return result


def build_finding_remediation_register(canonical: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_finding_remediation_register(
        v1.build_finding_remediation_register(canonical)
    )


def finding_register_markdown(register: Mapping[str, Any], *, spanish: bool) -> str:
    return v1.finding_register_markdown(
        normalize_finding_remediation_register(register),
        spanish=spanish,
    )


def render_finding_register_pdf(register: Mapping[str, Any], *, spanish: bool) -> bytes:
    return v1.render_finding_register_pdf(
        normalize_finding_remediation_register(register),
        spanish=spanish,
    )


__all__ = [
    "VERSION",
    "build_finding_remediation_register",
    "finding_register_markdown",
    "normalize_finding_remediation_register",
    "render_finding_register_pdf",
]
