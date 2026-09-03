from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.review-workload-truth.v1"

_RESOLVED_STATES = frozenset(
    {
        "accepted",
        "approved",
        "closed",
        "excluded",
        "false_positive",
        "fixed",
        "non_actionable",
        "remediated",
        "resolved",
        "risk_accepted",
        "verified_fixed",
    }
)


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finding_register(
    canonical: Mapping[str, Any],
    supplied: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if isinstance(supplied, Mapping):
        return supplied
    direct = canonical.get("client_finding_remediation_register")
    if isinstance(direct, Mapping):
        return direct
    assessment = _mapping(canonical.get("assessment"))
    nested = assessment.get("client_finding_remediation_register")
    return nested if isinstance(nested, Mapping) else {}


def _is_exact_source(item: Mapping[str, Any]) -> bool:
    path = str(item.get("path") or item.get("file_path") or item.get("source_path") or "").strip()
    location = str(item.get("location") or "").strip()
    return bool(path or location)


def _is_unresolved(item: Mapping[str, Any]) -> bool:
    if item.get("client_actionable") is False:
        return False
    states = {
        _token(item.get(key))
        for key in (
            "status",
            "disposition",
            "review_status",
            "human_review_status",
            "remediation_status",
        )
        if item.get(key) not in (None, "")
    }
    return not bool(states & _RESOLVED_STATES)


def _is_scanner_derived(item: Mapping[str, Any]) -> bool:
    sources = {
        _token(item.get("record_source")),
        *(_token(value) for value in item.get("record_sources") or []),
    }
    return "scanner_finding" in sources and "canonical_finding" not in sources


def exact_source_review_findings(
    canonical: Mapping[str, Any],
    *,
    finding_register: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    register = _finding_register(canonical, finding_register)
    raw = register.get("code_findings")
    if not isinstance(raw, list):
        raw = canonical.get("canonical_findings")
    if not isinstance(raw, list):
        raw = []

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for value in raw:
        if (
            not isinstance(value, Mapping)
            or _is_scanner_derived(value)
            or not _is_exact_source(value)
            or not _is_unresolved(value)
        ):
            continue
        item = deepcopy(dict(value))
        identity = (
            str(item.get("finding_id") or item.get("id") or "").strip().casefold(),
            str(item.get("path") or item.get("file_path") or item.get("source_path") or "").strip().casefold(),
            str(item.get("line") or item.get("start_line") or "").strip(),
            str(item.get("title") or item.get("decision_title") or "").strip().casefold(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        findings.append(item)
    return findings


def operational_review_findings(
    canonical: Mapping[str, Any],
    *,
    finding_register: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    register = _finding_register(canonical, finding_register)
    raw = register.get("operational_findings")
    if not isinstance(raw, list):
        raw = canonical.get("operational_findings")
    if not isinstance(raw, list):
        raw = []

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for value in raw:
        if (
            not isinstance(value, Mapping)
            or _is_scanner_derived(value)
            or not _is_unresolved(value)
        ):
            continue
        item = deepcopy(dict(value))
        identity = (
            str(item.get("finding_id") or item.get("id") or "").strip().casefold(),
            str(item.get("title") or item.get("decision_title") or "").strip().casefold(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        findings.append(item)
    return findings


def _candidate_work_units(
    canonical: Mapping[str, Any],
    candidate_register: Mapping[str, Any] | None,
) -> int:
    assessment = _mapping(canonical.get("assessment"))
    register_candidates = (
        candidate_register,
        canonical.get("canonical_scanner_finding_register"),
        assessment.get("canonical_scanner_finding_register"),
    )
    for register in register_candidates:
        if not isinstance(register, Mapping):
            continue
        triage = _mapping(register.get("technical_triage"))
        workload = _mapping(triage.get("workload_metrics"))
        if "human_review_work_units" in triage:
            return _integer(triage.get("human_review_work_units"))
        if "human_review_work_units" in workload:
            return _integer(workload.get("human_review_work_units"))

    for owner in (canonical, assessment):
        triage = _mapping(owner.get("technical_triage"))
        workload = _mapping(triage.get("workload_metrics"))
        if "human_review_work_units" in triage:
            return _integer(triage.get("human_review_work_units"))
        if "human_review_work_units" in workload:
            return _integer(workload.get("human_review_work_units"))
    return 0


def review_workload_summary(
    canonical: Mapping[str, Any],
    *,
    candidate_register: Mapping[str, Any] | None = None,
    finding_register: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    scanner_units = _candidate_work_units(canonical, candidate_register)
    exact_findings = exact_source_review_findings(
        canonical,
        finding_register=finding_register,
    )
    operational_findings = operational_review_findings(
        canonical,
        finding_register=finding_register,
    )
    exact_units = len(exact_findings)
    operational_units = len(operational_findings)
    total_units = scanner_units + exact_units + operational_units
    return {
        "version": VERSION,
        "scanner_candidate_review_work_units": scanner_units,
        "exact_source_review_work_units": exact_units,
        "operational_context_review_work_units": operational_units,
        "total_unresolved_human_review_work_units": total_units,
        "operator_attention_required": total_units > 0,
        "exact_source_review_findings": exact_findings,
        "operational_context_review_findings": operational_findings,
    }


__all__ = [
    "VERSION",
    "exact_source_review_findings",
    "operational_review_findings",
    "review_workload_summary",
]
