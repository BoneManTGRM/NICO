from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico import client_finding_remediation_register_v1 as v1

VERSION = "nico.client-finding-remediation-register.v2"


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
        return category, path, line, technical_identity
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


def _merge(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    preferred, other = (right, left) if _quality(right) > _quality(left) else (left, right)
    result = deepcopy(dict(preferred))
    for field, value in other.items():
        if result.get(field) in (None, "", [], {}):
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
    return result


def _consolidate(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    order: list[tuple[str, str, int, str]] = []
    for raw in values:
        item = deepcopy(dict(raw))
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
