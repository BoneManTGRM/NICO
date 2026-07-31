from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico import client_finding_remediation_register_v3 as v3
from nico.client_assessment_truth_v3 import normalize_repository_path

VERSION = "nico.client-finding-remediation-register.v6"
_DIRECT_FINDING_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
)
_REFERENCE_SURFACES = (
    "executive_findings",
    "finding_cards",
    "roadmap",
    "backlog",
    "work_packages",
    "remediation_plan",
    "recommendations",
    "assessment",
    "stage_summaries",
)
_SKIP_KEYS = {
    "pdf_base64",
    "markdown",
    "html",
    "raw_output",
    "stdout",
    "stderr",
    "secret",
    "match",
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _text(value).casefold().replace("_", "-")).strip("-")


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return int(value) if str(value or "").isdigit() else None


def _dedupe(values: Any) -> list[str]:
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


def _parse_location(item: Mapping[str, Any]) -> tuple[str, int | None]:
    path = normalize_repository_path(
        item.get("path") or item.get("file_path") or item.get("source_path") or ""
    )
    line = _int(item.get("line") or item.get("start_line"))
    location = normalize_repository_path(item.get("location") or "")
    match = re.match(r"^(.*?):(\d+)(?:-\d+)?(?::\d+)?$", location)
    if match:
        path = normalize_repository_path(match.group(1))
        line = line or int(match.group(2))
    elif not path and location not in {"", "location-not-retained", "not retained", "unknown"}:
        path = location
    return path, line


def _family(item: Mapping[str, Any]) -> str:
    declared = _token(item.get("finding_family") or item.get("rule_id"))
    combined = " ".join(
        _text(item.get(key), 3000)
        for key in (
            "title",
            "decision_title",
            "problematic_code",
            "observed_evidence",
            "fact",
            "interpretation",
            "recommendation",
            "category",
        )
    ).casefold()
    if any(
        marker in combined
        for marker in (
            "cyclomatic_complexity",
            "high-complexity",
            "complexity hotspot",
            "concentrated branching",
            "reduce complexity",
        )
    ) or "complex" in declared:
        return "complexity_hotspot"
    if "tls" in combined and any(
        marker in combined
        for marker in ("verify", "certificate", "cert_none", "rejectunauthorized")
    ):
        return "tls_verify_disabled"
    advisory = re.search(r"\b(?:GHSA-[0-9A-Za-z-]+|CVE-\d{4}-\d+)\b", combined, re.IGNORECASE)
    if advisory:
        return f"dependency_vulnerability:{advisory.group(0).casefold()}"
    if _token(item.get("category")) == "dependency" or "dependency vulnerability" in combined:
        return "dependency_vulnerability"
    if _token(item.get("category")) == "secret" or "secret candidate" in combined:
        return "secret_candidate"
    if any(marker in combined for marker in ("workflow reliability", "historical ci", "non-success runs")):
        return "ci_reliability"
    return declared or _token(item.get("category") or item.get("title")) or "technical_finding"


def _stable_id(repository: str, path: str, line: int | None, family: str, title: str) -> str:
    identity = "|".join(
        (
            repository.casefold(),
            path.casefold(),
            str(line or 0),
            family.casefold(),
            "" if path and line else _token(title),
        )
    )
    return "NICO-FINDING-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()


def _iter_mappings(value: Any, *, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 10:
        return
    if isinstance(value, Mapping):
        yield value
        for key, child in value.items():
            if str(key).casefold() in _SKIP_KEYS:
                continue
            yield from _iter_mappings(child, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_mappings(child, depth=depth + 1)


def _alias_index(canonical: Mapping[str, Any]) -> dict[tuple[str, int, str], list[str]]:
    index: dict[tuple[str, int, str], list[str]] = {}
    for item in _iter_mappings(canonical):
        identifier = _text(item.get("finding_id") or item.get("id"))
        aliases = _dedupe(item.get("finding_aliases") or [])
        if not identifier and not aliases:
            continue
        path, line = _parse_location(item)
        if not path or line is None:
            continue
        family = _family(item)
        key = (path.casefold(), line, family)
        values = [*index.get(key, []), identifier, *aliases]
        index[key] = _dedupe(values)
    return index


def _quality(item: Mapping[str, Any]) -> tuple[int, ...]:
    return (
        int(bool(item.get("artifact_hash"))),
        int(bool(item.get("source_excerpt"))),
        int(bool(item.get("symbol"))),
        int(bool(item.get("rule_id"))),
        int(item.get("exact_commit_match") is True),
        len(_text(item.get("observed_evidence"))),
        len(_text(item.get("recommended_correction"))),
    )


def _merge(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    preferred, other = (right, left) if _quality(right) > _quality(left) else (left, right)
    result = deepcopy(dict(preferred))
    for field, value in other.items():
        if result.get(field) in (None, "", [], {}):
            result[field] = deepcopy(value)
    stable_id = _text(result.get("finding_id"))
    result["finding_aliases"] = [
        alias
        for alias in _dedupe(
            [
                *list(result.get("finding_aliases") or []),
                *list(other.get("finding_aliases") or []),
                other.get("finding_id"),
            ]
        )
        if alias != stable_id
    ]
    result["verification"] = _dedupe(
        [*list(result.get("verification") or []), *list(other.get("verification") or [])]
    )
    verification_keys = {value.casefold() for value in result["verification"]}
    exits = _dedupe(
        [*list(result.get("exit_criteria") or []), *list(other.get("exit_criteria") or [])]
    )
    result["exit_criteria"] = [value for value in exits if value.casefold() not in verification_keys]
    result["duplicate_sources_consolidated"] = True
    result["verification_and_exit_criteria_distinct"] = True
    return result


def _normalize_records(
    values: Iterable[Mapping[str, Any]],
    *,
    repository: str,
    aliases_by_anchor: Mapping[tuple[str, int, str], list[str]],
) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    order: list[tuple[str, str, int, str]] = []
    for raw in values:
        item = deepcopy(dict(raw))
        path, line = _parse_location(item)
        family = _family(item)
        original_id = _text(item.get("finding_id") or item.get("id"))
        stable_id = _stable_id(repository, path, line, family, _text(item.get("title")))
        anchor_aliases = aliases_by_anchor.get((path.casefold(), int(line or 0), family), [])
        aliases = _dedupe(
            [
                *list(item.get("finding_aliases") or []),
                original_id,
                *anchor_aliases,
            ]
        )
        item["finding_id"] = stable_id
        item["finding_aliases"] = [alias for alias in aliases if alias != stable_id]
        item["finding_family"] = family
        item["path"] = path
        item["line"] = line
        if family == "complexity_hotspot":
            item["rule_id"] = "complexity_hotspot"
        key = (
            "code" if path and line is not None and item.get("client_actionable") is not False else "operational",
            path.casefold(),
            int(line or 0),
            family,
        )
        if key not in selected:
            selected[key] = item
            order.append(key)
        else:
            selected[key] = _merge(selected[key], item)
    return [selected[key] for key in order]


def normalize_finding_remediation_register(
    register: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(register))
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    repository = _text(identity.get("repository") or canonical.get("repository"))
    aliases_by_anchor = _alias_index(canonical)

    code = _normalize_records(
        (item for item in result.get("code_findings") or [] if isinstance(item, Mapping)),
        repository=repository,
        aliases_by_anchor=aliases_by_anchor,
    )
    operational = _normalize_records(
        (item for item in result.get("operational_findings") or [] if isinstance(item, Mapping)),
        repository=repository,
        aliases_by_anchor=aliases_by_anchor,
    )
    excluded = _normalize_records(
        (
            item
            for item in result.get("excluded_non_production_findings") or []
            if isinstance(item, Mapping)
        ),
        repository=repository,
        aliases_by_anchor=aliases_by_anchor,
    )

    code.sort(
        key=lambda item: (
            item.get("priority") not in {"P0", "P1"},
            _text(item.get("path")),
            int(item.get("line") or 0),
            _text(item.get("finding_family")),
        )
    )
    operational.sort(
        key=lambda item: (
            item.get("priority") not in {"P0", "P1"},
            _text(item.get("category")),
            _text(item.get("title")),
        )
    )
    summary = deepcopy(dict(result.get("summary") or {}))
    decision_count = len(code) + len(operational)
    summary.update(
        {
            "register_normalization_version": VERSION,
            "decision_finding_count": decision_count,
            "exact_source_code_finding_count": len(code),
            "operational_or_context_finding_count": len(operational),
            "excluded_non_production_count": len(excluded),
            "semantic_duplicate_code_anchors_absent": len(
                {
                    (
                        _text(item.get("path")).casefold(),
                        int(item.get("line") or 0),
                        _text(item.get("finding_family")),
                    )
                    for item in code
                }
            )
            == len(code),
            "stable_alias_projection_idempotent": True,
            "finding_population_reconciled": int(summary.get("raw_observation_count") or decision_count)
            >= int(summary.get("normalized_candidate_count") or decision_count)
            >= decision_count,
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
        v3.build_finding_remediation_register(canonical),
        canonical,
    )


def canonical_findings_from_register(register: Mapping[str, Any]) -> list[dict[str, Any]]:
    return v3.canonical_findings_from_register(register)


def _canonical_by_identity(findings: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for item in findings:
        for value in (
            item.get("finding_id"),
            item.get("id"),
            *(item.get("finding_aliases") or []),
        ):
            key = _text(value)
            if key:
                output[key] = item
    return output


def _sync_surface(value: Any, canonical_by_id: Mapping[str, Mapping[str, Any]]) -> Any:
    if isinstance(value, list):
        return [_sync_surface(item, canonical_by_id) for item in value]
    if not isinstance(value, Mapping):
        return value
    original = dict(value)
    item = {
        key: _sync_surface(child, canonical_by_id)
        for key, child in original.items()
    }
    finding_id = _text(original.get("finding_id") or original.get("id"))
    if finding_id and finding_id in canonical_by_id:
        canonical = canonical_by_id[finding_id]
        for field in (
            "finding_id",
            "id",
            "finding_aliases",
            "title",
            "decision_title",
            "category",
            "priority",
            "severity",
            "status",
            "location",
            "path",
            "line",
            "column",
            "end_line",
            "symbol",
            "rule_id",
            "finding_family",
            "fact",
            "evidence",
            "interpretation",
            "business_impact",
            "impact",
            "recommendation",
            "owner_role",
            "effort",
            "cost_of_inaction",
            "residual_risk",
            "acceptance_criteria",
            "exit_criteria",
            "rollback",
            "supporting_evidence",
        ):
            if field in canonical:
                item[field] = deepcopy(canonical[field])
    return item


def synchronize_canonical_finding_surfaces(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    findings = canonical_findings_from_register(register)
    by_id = _canonical_by_identity(findings)

    for surface in _DIRECT_FINDING_SURFACES:
        result[surface] = deepcopy(findings)
    result["executive_risk_register"] = deepcopy(findings[:7])
    result["priority_findings"] = deepcopy(findings[:5])
    for surface in _REFERENCE_SURFACES:
        if surface in result:
            result[surface] = _sync_surface(result[surface], by_id)

    result["canonical_findings"] = deepcopy(findings)
    result["client_finding_remediation_register"] = deepcopy(register)
    summary = deepcopy(dict(register.get("summary") or {}))
    result["finding_population"] = summary
    assessment = deepcopy(dict(result.get("assessment") or {}))
    assessment["finding_population"] = deepcopy(summary)
    assessment["finding_register_count"] = len(findings)
    assessment["canonical_finding_count"] = len(findings)
    result["assessment"] = assessment

    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "canonical_finding_surface_sync_version": VERSION,
            "stable_finding_alias_projection_idempotent": True,
            "all_mirrored_finding_surfaces_synchronized": True,
        }
    )
    result["v2_pipeline_contract"] = contract
    return result


def finding_register_markdown(register: Mapping[str, Any], *, spanish: bool) -> str:
    return v3.finding_register_markdown(register, spanish=spanish)


def render_finding_register_pdf(register: Mapping[str, Any], *, spanish: bool) -> bytes:
    return v3.render_finding_register_pdf(register, spanish=spanish)


__all__ = [
    "VERSION",
    "build_finding_remediation_register",
    "canonical_findings_from_register",
    "finding_register_markdown",
    "normalize_finding_remediation_register",
    "render_finding_register_pdf",
    "synchronize_canonical_finding_surfaces",
]
