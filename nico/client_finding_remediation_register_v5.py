from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico import client_finding_remediation_register_v3 as v3
from nico import client_finding_remediation_register_v4 as v4
from nico.client_assessment_truth_v3 import normalize_repository_path

VERSION = "nico.client-finding-remediation-register.v8"
_RISK_PUBLIC_ID = re.compile(r"^RISK-P[0-3]-", re.IGNORECASE)
_MISSING_LOCATION_TOKENS = {
    "",
    "location-not-retained",
    "not-retained",
    "unknown",
    "none",
    "n-a",
}
_DECISION_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
)


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


def _dedupe(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _clean_location(value: Any) -> str:
    normalized = normalize_repository_path(value or "")
    return "" if _token(normalized) in _MISSING_LOCATION_TOKENS else normalized


def _parse_location(item: Mapping[str, Any]) -> tuple[str, int | None]:
    path = _clean_location(
        item.get("path") or item.get("file_path") or item.get("source_path") or ""
    )
    line = _int(item.get("line") or item.get("start_line"))
    location = _clean_location(item.get("location") or "")
    match = re.match(r"^(.*?):(\d+)(?:-\d+)?(?::\d+)?$", location)
    if match:
        path = _clean_location(match.group(1))
        line = line or int(match.group(2))
    elif not path and location:
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


def _anchor(item: Mapping[str, Any]) -> tuple[str, int, str] | None:
    path, line = _parse_location(item)
    if not path or line is None:
        return None
    return path.casefold(), line, _family(item)


def _public_id_quality(item: Mapping[str, Any]) -> tuple[int, ...]:
    priority = {"P0": 4, "P1": 3, "P2": 2, "P3": 1}.get(
        _text(item.get("priority")).upper(),
        0,
    )
    criteria = item.get("acceptance_criteria") or item.get("verification") or []
    if isinstance(criteria, str):
        criteria = [criteria]
    return (
        priority,
        int(bool(item.get("business_impact") or item.get("impact"))),
        int(bool(item.get("owner_role"))),
        int(bool(item.get("effort"))),
        len(criteria) if isinstance(criteria, (list, tuple)) else 0,
        len(_text(item.get("fact") or item.get("observed_evidence"))),
    )


def _preferred_public_ids(canonical: Mapping[str, Any]) -> dict[tuple[str, int, str], str]:
    selected: dict[tuple[str, int, str], tuple[tuple[int, ...], str]] = {}
    for surface in _DECISION_SURFACES:
        values = canonical.get(surface)
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, Mapping):
                continue
            identifier = _text(raw.get("finding_id") or raw.get("id"))
            anchor = _anchor(raw)
            if not identifier or not anchor or not _RISK_PUBLIC_ID.match(identifier):
                continue
            quality = _public_id_quality(raw)
            if anchor not in selected or quality > selected[anchor][0]:
                selected[anchor] = (quality, identifier)
    return {anchor: identifier for anchor, (_, identifier) in selected.items()}


def _restore_compatible_public_ids(
    register: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(register))
    preferred = _preferred_public_ids(canonical)
    restored = 0
    for surface in (
        "code_findings",
        "operational_findings",
        "excluded_non_production_findings",
    ):
        records: list[dict[str, Any]] = []
        for raw in result.get(surface) or []:
            if not isinstance(raw, Mapping):
                continue
            item = deepcopy(dict(raw))
            anchor = _anchor(item)
            public_id = preferred.get(anchor) if anchor else None
            stable_id = _text(item.get("finding_id") or item.get("id"))
            aliases = _dedupe(item.get("finding_aliases") or [])
            if public_id and public_id in aliases and public_id != stable_id:
                item["stable_finding_id"] = stable_id
                item["finding_id"] = public_id
                item["finding_aliases"] = aliases
                item["finding_identity_compatibility_projection"] = True
                restored += 1
            records.append(item)
        result[surface] = records
    summary = deepcopy(dict(result.get("summary") or {}))
    summary["compatible_public_finding_ids_restored"] = restored
    summary["stable_finding_ids_retained_separately"] = restored > 0
    result["summary"] = summary
    return result


def _is_unanchored_generic_scanner_candidate(item: Mapping[str, Any]) -> bool:
    if _token(item.get("record_source")) != "scanner-finding":
        return False
    path, line = _parse_location(item)
    if path or line is not None:
        return False
    family = _family(item)
    category = _token(item.get("category"))
    combined = " ".join(
        _text(item.get(key), 2000)
        for key in (
            "title",
            "observed_evidence",
            "problematic_code",
            "interpretation",
            "rule_id",
        )
    )
    if category in {"dependency", "secret", "ci", "ci-cd", "supply-chain"}:
        return False
    if family.startswith("dependency_vulnerability") or family in {
        "secret_candidate",
        "ci_reliability",
    }:
        return False
    if re.search(r"\b(?:GHSA-[0-9A-Za-z-]+|CVE-\d{4}-\d+)\b", combined, re.IGNORECASE):
        return False
    return True


def _configuration_issue_count(canonical: Mapping[str, Any]) -> int:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    for candidate in (
        canonical.get("requested_scanner_records"),
        assessment.get("requested_scanner_records"),
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
    ):
        if not isinstance(candidate, list):
            continue
        affected: set[str] = set()
        for raw in candidate:
            if not isinstance(raw, Mapping):
                continue
            count = max(
                _int(raw.get("scanner_configuration_error_count")) or 0,
                _int(raw.get("configuration_error_count")) or 0,
            )
            state = _token(raw.get("state") or raw.get("status"))
            if count <= 0 and state not in {
                "configuration-failed",
                "configuration-error",
                "invalid-configuration",
            }:
                continue
            scanner = _text(raw.get("scanner_name") or raw.get("scanner") or raw.get("tool"))
            reason = _text(raw.get("failure_reason") or raw.get("reason") or raw.get("error"))
            affected.add(scanner.casefold() or reason.casefold() or "unknown")
        if affected:
            return len(affected)

    issues = canonical.get("scanner_configuration_issues")
    if isinstance(issues, list):
        affected = {
            _text(item.get("scanner_name") or item.get("reason")).casefold()
            for item in issues
            if isinstance(item, Mapping)
            and _text(item.get("scanner_name") or item.get("reason"))
        }
        if affected:
            return len(affected)

    summary = assessment.get("scanner_applicability_summary")
    if isinstance(summary, Mapping):
        return max(0, _int(summary.get("scanner_configuration_issue_count")) or 0)
    return 0


def normalize_finding_remediation_register(
    register: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(register))
    code = [
        deepcopy(dict(item))
        for item in result.get("code_findings") or []
        if isinstance(item, Mapping)
    ]
    operational: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for raw in result.get("operational_findings") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        if _is_unanchored_generic_scanner_candidate(item):
            item["client_actionable"] = False
            item["suppression_reason"] = "scanner_candidate_missing_decision_grade_source_evidence"
            item["promotion_blocked_reason"] = "exact_source_anchor_not_retained"
            suppressed.append(item)
        else:
            operational.append(item)
    excluded = [
        deepcopy(dict(item))
        for item in result.get("excluded_non_production_findings") or []
        if isinstance(item, Mapping)
    ]

    summary = deepcopy(dict(result.get("summary") or {}))
    decision_count = len(code) + len(operational)
    existing_normalized = max(0, _int(summary.get("normalized_candidate_count")) or 0)
    normalized_count = max(decision_count, existing_normalized)
    raw_count = max(
        normalized_count,
        _int(summary.get("raw_observation_count")) or 0,
        decision_count + len(excluded) + len(suppressed),
    )
    summary.update(
        {
            "register_normalization_version": VERSION,
            "canonical_finding_count": decision_count,
            "finding_register_count": decision_count,
            "deduplicated_record_count": decision_count + len(excluded),
            "raw_observation_count": raw_count,
            "normalized_candidate_count": normalized_count,
            "decision_finding_count": decision_count,
            "exact_source_code_finding_count": len(code),
            "operational_or_context_finding_count": len(operational),
            "excluded_non_production_count": len(excluded),
            "suppressed_unanchored_scanner_candidate_count": len(suppressed),
            "scanner_configuration_issue_count": _configuration_issue_count(canonical),
            "scanner_configuration_errors_promoted_to_code_findings": False,
            "unanchored_generic_scanner_candidates_promoted": False,
            "finding_population_reconciled": raw_count >= normalized_count >= decision_count,
            "stable_alias_projection_idempotent": True,
        }
    )
    result.update(
        {
            "version": VERSION,
            "code_findings": code,
            "operational_findings": operational,
            "excluded_non_production_findings": excluded,
            "suppressed_unanchored_scanner_candidates": suppressed,
            "summary": summary,
        }
    )
    return _restore_compatible_public_ids(result, canonical)


def build_finding_remediation_register(canonical: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_finding_remediation_register(
        v4.build_finding_remediation_register(canonical),
        canonical,
    )


def canonical_findings_from_register(register: Mapping[str, Any]) -> list[dict[str, Any]]:
    return v4.canonical_findings_from_register(register)


def synchronize_canonical_finding_surfaces(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_finding_remediation_register(register, canonical)
    result = v4.synchronize_canonical_finding_surfaces(canonical, normalized)
    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "final_finding_truth_version": VERSION,
            "unanchored_generic_scanner_candidates_suppressed": True,
            "scanner_configuration_incidents_counted_per_affected_scanner": True,
            "legacy_aliases_omitted_from_rendered_register": True,
        }
    )
    result["v2_pipeline_contract"] = contract
    return result


def finding_register_markdown(register: Mapping[str, Any], *, spanish: bool) -> str:
    # V4 preserves aliases in structured truth. They are intentionally omitted
    # from client-facing prose so retired identifiers do not reappear in reports.
    return v3.finding_register_markdown(register, spanish=spanish)


def render_finding_register_pdf(register: Mapping[str, Any], *, spanish: bool) -> bytes:
    return v4.render_finding_register_pdf(register, spanish=spanish)


__all__ = [
    "VERSION",
    "build_finding_remediation_register",
    "canonical_findings_from_register",
    "finding_register_markdown",
    "normalize_finding_remediation_register",
    "render_finding_register_pdf",
    "synchronize_canonical_finding_surfaces",
]
