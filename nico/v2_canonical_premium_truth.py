from __future__ import annotations

import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

VERSION = "nico.v2.canonical-premium-truth.v1"

SECTION_WEIGHTS = {
    "code_audit": 0.20,
    "dependency_health": 0.15,
    "secrets_review": 0.15,
    "static_analysis": 0.15,
    "ci_cd": 0.15,
    "architecture_debt": 0.15,
    "velocity_complexity": 0.05,
}

SECTION_SCANNERS = {
    "dependency_health": ("npm-audit", "pip-audit", "osv-scanner"),
    "secrets_review": ("gitleaks", "trufflehog"),
    "static_analysis": ("bandit", "eslint", "semgrep", "typescript"),
}

_NON_PRODUCTION_PARTS = {
    "test", "tests", "testing", "fixture", "fixtures", "example", "examples",
    "sample", "samples", "demo", "demos", "mock", "mocks", "__mocks__",
    "generated", "vendor", "vendors", "node_modules", ".next", "dist", "build",
    "coverage", "coverage_html",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(dict(item)) for item in value or [] if isinstance(item, Mapping)]


def _section_id(section: Mapping[str, Any]) -> str:
    value = _text(section.get("id") or section.get("section_id") or section.get("label")).casefold()
    aliases = {
        "code audit": "code_audit",
        "dependency / library ecosystem": "dependency_health",
        "dependency library ecosystem": "dependency_health",
        "secrets exposure review": "secrets_review",
        "static analysis": "static_analysis",
        "ci/cd analysis": "ci_cd",
        "architecture & technical debt": "architecture_debt",
        "velocity / complexity": "velocity_complexity",
    }
    return aliases.get(value, value.replace("-", "_").replace(" ", "_"))


def _scanner_name(record: Mapping[str, Any]) -> str:
    return _text(record.get("scanner_name") or record.get("tool") or record.get("scanner")).casefold().replace("_", "-")


def _scanner_completed(record: Mapping[str, Any]) -> bool:
    state = _text(record.get("state") or record.get("status")).casefold().replace("-", "_")
    return record.get("completed") is True or state in {"completed", "completed_with_findings", "complete", "success", "passed"}


def _scanner_verified(record: Mapping[str, Any]) -> bool:
    return _scanner_completed(record) and (
        record.get("verified") is True
        or record.get("verified_complete") is True
        or record.get("verified_for_this_report") is True
    )


def _scanner_line(record: Mapping[str, Any]) -> str:
    name = _scanner_name(record)
    state = _text(record.get("state") or record.get("status") or "unknown").casefold().replace("-", "_")
    return (
        f"{name}: status={state}; exact_commit_match={record.get('exact_commit_match') is True}; "
        f"verified_complete={_scanner_verified(record)}; findings={len(record.get('findings') or [])}; "
        f"artifact_hash={'retained' if _text(record.get('artifact_hash')) else 'unavailable'}"
    )


def _failure_line(record: Mapping[str, Any]) -> str:
    reason = _text(
        record.get("failure_reason")
        or record.get("failure_or_unavailable_reason")
        or record.get("reason")
        or record.get("stderr")
        or "completion requirements were not met"
    )
    return f"{_scanner_name(record)} exact-SHA evidence remains {_text(record.get('state') or record.get('status') or 'incomplete')}: {reason}"


def _severity_text(value: Any) -> str:
    if isinstance(value, str):
        return _text(value).casefold()
    if isinstance(value, Mapping):
        for key in ("severity", "level", "score", "type"):
            if value.get(key) not in (None, ""):
                return _severity_text(value.get(key))
    if isinstance(value, (list, tuple)):
        return " ".join(_severity_text(item) for item in value if _severity_text(item))
    return ""


def _cvss_score(value: Any) -> float | None:
    texts: list[str] = []
    if isinstance(value, (str, int, float)):
        texts.append(str(value))
    elif isinstance(value, Mapping):
        texts.extend(str(item) for item in value.values() if isinstance(item, (str, int, float)))
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, Mapping):
                texts.extend(str(child) for child in item.values() if isinstance(child, (str, int, float)))
            elif isinstance(item, (str, int, float)):
                texts.append(str(item))
    for text in texts:
        for match in re.findall(r"(?<!\d)(10(?:\.0)?|[0-9](?:\.\d+)?)(?!\d)", text):
            try:
                score = float(match)
            except ValueError:
                continue
            if 0 <= score <= 10:
                return score
    return None


def _first(value: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        item = value.get(key)
        if item not in (None, "", [], {}):
            return item
    return None


def _fixed_versions(finding: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    raw = _first(finding, "fixed_versions", "fixed_version", "fix_versions")
    if isinstance(raw, str):
        values.append(raw)
    elif isinstance(raw, (list, tuple)):
        values.extend(_text(item) for item in raw if _text(item))
    affected = finding.get("affected")
    if isinstance(affected, list):
        for item in affected:
            if not isinstance(item, Mapping):
                continue
            for value in item.get("ranges") or []:
                if not isinstance(value, Mapping):
                    continue
                for event in value.get("events") or []:
                    if isinstance(event, Mapping) and _text(event.get("fixed")):
                        values.append(_text(event.get("fixed")))
    return list(dict.fromkeys(values))


def _dependency_disposition(raw: Mapping[str, Any], scanner: str) -> dict[str, Any]:
    finding = deepcopy(dict(raw))
    package_value = _first(finding, "package", "package_name", "name", "module")
    if isinstance(package_value, Mapping):
        package = _text(package_value.get("name"))
        ecosystem = _text(package_value.get("ecosystem"))
        package_version = _text(package_value.get("version"))
    else:
        package = _text(package_value)
        ecosystem = _text(finding.get("ecosystem"))
        package_version = ""
    advisory = _text(_first(finding, "id", "advisory_id", "ghsa_id", "vulnerability_id"))
    if not advisory:
        aliases = finding.get("aliases")
        if isinstance(aliases, list) and aliases:
            advisory = _text(aliases[0])
    installed = _text(_first(finding, "installed_version", "version", "current_version")) or package_version
    fixed = _fixed_versions(finding)
    path = _text(_first(finding, "dependency_path", "path", "manifest", "source", "lockfile"))
    severity_raw = _first(finding, "severity", "database_specific", "cvss", "score")
    severity_text = _severity_text(severity_raw)
    cvss = _cvss_score(severity_raw)
    if "critical" in severity_text or (cvss is not None and cvss >= 9):
        severity = "critical"
    elif "high" in severity_text or (cvss is not None and cvss >= 7):
        severity = "high"
    elif "medium" in severity_text or "moderate" in severity_text or (cvss is not None and cvss >= 4):
        severity = "medium"
    elif "low" in severity_text or cvss is not None:
        severity = "low"
    else:
        severity = "unknown"
    context = " ".join((package, path, _text(finding.get("scope")), _text(finding.get("dependency_type")))).casefold()
    scope = "development_or_test" if any(token in context for token in ("devdepend", "test", "fixture", "example", "demo")) else "production_or_unknown"
    reachability_value = finding.get("reachable") if "reachable" in finding else finding.get("reachability")
    if reachability_value is True or _text(reachability_value).casefold() in {"true", "reachable", "yes"}:
        reachability = "reachable"
    elif reachability_value is False or _text(reachability_value).casefold() in {"false", "unreachable", "no"}:
        reachability = "unreachable"
    else:
        reachability = "unknown"
    complete = bool(advisory and package and installed)
    material = bool(complete and severity in {"critical", "high"} and scope != "development_or_test" and reachability != "unreachable")
    disposition = "verified_material" if material else "review_required"
    missing = [
        label
        for label, value in (("advisory_id", advisory), ("package", package), ("installed_version", installed))
        if not value
    ]
    return {
        "scanner": scanner,
        "advisory_id": advisory or "unavailable",
        "package": package or "unavailable",
        "ecosystem": ecosystem or "unavailable",
        "installed_version": installed or "unavailable",
        "fixed_versions": fixed,
        "dependency_path": path or "unavailable",
        "severity": severity,
        "cvss_score": cvss,
        "scope": scope,
        "reachability": reachability,
        "disposition": disposition,
        "evidence_complete": complete,
        "missing_required_fields": missing,
        "summary": _text(_first(finding, "summary", "details", "message", "description")),
        "raw_finding": finding,
    }


def _dependency_dispositions(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        name = _scanner_name(record)
        if name not in {"npm-audit", "pip-audit", "osv-scanner"}:
            continue
        for raw in record.get("findings") or []:
            if not isinstance(raw, Mapping):
                continue
            item = _dependency_disposition(raw, name)
            key = (
                item["advisory_id"].casefold(),
                item["package"].casefold(),
                item["installed_version"].casefold(),
                item["dependency_path"].casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
    return output


def _finding_location(finding: Mapping[str, Any]) -> str:
    value = finding.get("location")
    if isinstance(value, Mapping):
        return _text(value.get("path") or value.get("file") or value.get("file_path"))
    return _text(value).split(":", 1)[0]


def _non_production_path(path: str) -> bool:
    normalized = path.replace("\\", "/").casefold().strip("/")
    parts = [part for part in normalized.split("/") if part]
    filename = PurePosixPath(normalized).name
    return (
        any(part in _NON_PRODUCTION_PARTS for part in parts)
        or filename.startswith("test_")
        or filename.endswith("_test.py")
        or filename.endswith(".spec.ts")
        or filename.endswith(".spec.tsx")
        or filename.endswith(".test.ts")
        or filename.endswith(".test.tsx")
    )


def _split_non_production_findings(canonical: dict[str, Any]) -> None:
    source = _records(canonical.get("canonical_findings"))
    retained: list[dict[str, Any]] = []
    observations = _records(canonical.get("non_production_observations"))
    for item in source:
        category = _text(item.get("category")).casefold()
        rule_text = " ".join(
            _text(item.get(key)).casefold()
            for key in ("title", "decision_title", "rule_id", "rule", "test_id", "interpretation")
        )
        security_pattern = category in {"code", "static", "security"} or any(
            token in rule_text for token in ("eval", "exec", "tls", "secret", "shell", "injection")
        )
        path = _finding_location(item)
        if security_pattern and path and _non_production_path(path):
            item["production_relevance"] = "non_production"
            item["score_impact"] = False
            item["disposition"] = "test_fixture_example_or_generated_context"
            observations.append(item)
        else:
            item["production_relevance"] = item.get("production_relevance") or "production_or_unknown"
            retained.append(item)
    canonical["non_production_observations"] = observations
    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        canonical[surface] = deepcopy(retained)
    canonical["priority_findings"] = deepcopy(retained[:5])


def _score_from_scoring_stage(canonical: Mapping[str, Any]) -> tuple[int | None, int | None]:
    technical: int | None = None
    adjusted: int | None = None

    def walk(value: Any, scoring_context: bool = False, depth: int = 0) -> None:
        nonlocal technical, adjusted
        if depth > 9:
            return
        if isinstance(value, Mapping):
            label = " ".join(
                _text(value.get(key)).casefold()
                for key in ("stage_id", "title", "capability", "name", "summary")
            )
            local_scoring = scoring_context or "scor" in label or value.get("final_report_input_scores_synchronized") is True
            if local_scoring:
                for key in ("technical_score", "canonical_technical_score"):
                    if technical is None and (candidate := _numeric(value.get(key))) is not None:
                        technical = candidate
                for key in ("canonical_evidence_adjusted_score", "evidence_adjusted_score"):
                    if adjusted is None and (candidate := _numeric(value.get(key))) is not None:
                        adjusted = candidate
            for item in value.values():
                walk(item, local_scoring, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item, scoring_context, depth + 1)

    walk(canonical)
    return technical, adjusted


def _weighted_score(sections: list[dict[str, Any]]) -> tuple[int | None, list[dict[str, Any]]]:
    active_weight = 0.0
    weighted_sum = 0.0
    rows: list[dict[str, Any]] = []
    for section in sections:
        section_id = _section_id(section)
        weight = SECTION_WEIGHTS.get(section_id, 0.0)
        score = _numeric(section.get("score_value"))
        if score is None:
            score = _numeric(section.get("presented_score"))
        if score is None:
            score = _numeric(section.get("score"))
        included = score is not None and section.get("exclude_from_maturity") is not True
        contribution = round(score * weight, 2) if included else None
        rows.append({
            "control": section.get("label") or section_id,
            "section_id": section_id,
            "weight": weight,
            "weight_percent": round(weight * 100),
            "technical_score": score if included else None,
            "weighted_contribution": contribution,
            "assurance": section.get("assurance_label") or section.get("assurance_status"),
            "included": included,
        })
        if included:
            active_weight += weight
            weighted_sum += score * weight
    if active_weight <= 0:
        return None, rows
    return round(weighted_sum / active_weight), rows


def _band(score: int | None) -> tuple[str, str]:
    if score is None:
        return "not_scored", "NOT SCORED"
    if score >= 90:
        return "exceptional", "EXCEPTIONAL"
    if score >= 80:
        return "strong", "STRONG"
    if score >= 70:
        return "moderate", "MODERATE"
    if score >= 55:
        return "weak", "WEAK"
    return "critical", "CRITICAL"


def _repair_sections(canonical: dict[str, Any], assessment: dict[str, Any], records: list[dict[str, Any]], dispositions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_scanner = {_scanner_name(item): item for item in records}
    sections = _records(assessment.get("sections"))
    for section in sections:
        section_id = _section_id(section)
        section["id"] = section_id
        tools = SECTION_SCANNERS.get(section_id)
        if tools:
            selected = [by_scanner[name] for name in tools if name in by_scanner]
            incomplete = [item for item in selected if not _scanner_completed(item) or not _scanner_verified(item)]
            section["evidence"] = [_scanner_line(item) for item in selected]
            section["unavailable"] = [_failure_line(item) for item in incomplete]
            section["scanner_execution_records"] = deepcopy(selected)
            if incomplete:
                section["assurance_status"] = "review_limited"
                section["assurance_label"] = "REVIEW LIMITED"
                section["assurance_display"] = "REVIEW LIMITED"
                if section_id in {"secrets_review", "static_analysis"}:
                    section["status"] = "yellow"
                    section["presented_status"] = "yellow"
            else:
                section["assurance_status"] = "verified"
                section["assurance_label"] = "VERIFIED"
                section["assurance_display"] = "VERIFIED"
                section["status"] = section.get("status") if section.get("status") not in {"red", "blocked"} else "green"
                section["presented_status"] = section.get("status")
        if section_id == "dependency_health":
            material = [item for item in dispositions if item["disposition"] == "verified_material"]
            review = [item for item in dispositions if item["disposition"] != "verified_material"]
            complete = bool(dispositions) and all(item["evidence_complete"] for item in dispositions)
            section["dependency_dispositions"] = deepcopy(dispositions)
            section["findings"] = [
                f"{item['advisory_id']} · {item['package']} {item['installed_version']} · severity={item['severity']} · "
                f"scope={item['scope']} · reachability={item['reachability']} · disposition={item['disposition']} · "
                f"fixed={','.join(item['fixed_versions']) or 'not retained'}"
                for item in dispositions
            ]
            section["summary"] = (
                f"Dependency evidence retained {len(dispositions)} unique advisory disposition(s): "
                f"{len(material)} verified material and {len(review)} review-required. "
                "Raw candidate volume is not treated as confirmed defect volume."
            )
            if not complete:
                previous_score = _numeric(section.get("score_value")) or _numeric(section.get("presented_score")) or _numeric(section.get("score"))
                section["source_score_before_disposition_gate"] = previous_score
                section["score"] = None
                section["presented_score"] = None
                section["score_value"] = None
                section["technical_score_display"] = "NOT SCORED"
                section["score_band"] = "not_scored"
                section["score_band_label"] = "NOT SCORED"
                section["exclude_from_maturity"] = True
                section["assurance_status"] = "review_limited"
                section["assurance_label"] = "REVIEW LIMITED · DISPOSITION INCOMPLETE"
                section["unavailable"] = list(dict.fromkeys([
                    *list(section.get("unavailable") or []),
                    "Dependency scoring is excluded until each advisory retains package, installed version, advisory identity, fixed-version guidance, scope, and reachability disposition.",
                ]))
    return sections


def _repair_stages(canonical: dict[str, Any], records: list[dict[str, Any]], technical: int | None, adjusted: int | None) -> None:
    stages = _records(canonical.get("stage_summaries"))
    filtered = [
        item for item in stages
        if _text(item.get("stage_id")) not in {"dependency_security_static_analysis", "evidence_reconciliation_and_scoring"}
    ]
    completed = [item for item in records if _scanner_completed(item) and _scanner_verified(item)]
    incomplete = [item for item in records if item not in completed]
    filtered.append({
        "stage_id": "dependency_security_static_analysis",
        "title": "Dependency, Security, and Static Analysis",
        "status": "complete" if not incomplete else "review_required",
        "summary": f"{len(completed)} canonical scanner records completed and {len(incomplete)} remain review-limited.",
        "evidence": [_scanner_line(item) for item in records],
        "findings": [],
        "unavailable": [_failure_line(item) for item in incomplete],
    })
    filtered.append({
        "stage_id": "evidence_reconciliation_and_scoring",
        "title": "Evidence Reconciliation and Scoring",
        "status": "complete",
        "summary": "One canonical score pair is used by JSON, Markdown, HTML, PDF, UI, and the persisted run record.",
        "evidence": [
            f"technical_score: {technical if technical is not None else 'not_scored'}",
            f"canonical_evidence_adjusted_score: {adjusted if adjusted is not None else 'not_scored'}",
            "final_report_input_scores_synchronized: True",
        ],
        "findings": [],
        "unavailable": [],
    })
    canonical["stage_summaries"] = filtered


def repair_canonical_premium_truth(value: Mapping[str, Any]) -> dict[str, Any]:
    canonical = deepcopy(dict(value))
    assessment = _mapping(canonical.get("assessment"))
    records = _records(canonical.get("scanner_execution_records") or assessment.get("scanner_execution_records"))
    canonical["scanner_execution_records"] = deepcopy(records)

    _split_non_production_findings(canonical)
    dispositions = _dependency_dispositions(records)
    canonical["dependency_dispositions"] = deepcopy(dispositions)

    sections = _repair_sections(canonical, assessment, records, dispositions)
    assessment["sections"] = sections
    assessment["scanner_execution_records"] = deepcopy(records)
    completed = [item for item in records if _scanner_completed(item) and _scanner_verified(item)]
    incomplete = [item for item in records if item not in completed]
    assessment["completed_scanner_records"] = deepcopy(completed)
    assessment["incomplete_scanner_records"] = deepcopy(incomplete)
    assessment["evidence_health_summary"] = {
        "completed_scanners": [_scanner_name(item) for item in completed],
        "incomplete_scanners": [
            {
                "scanner": _scanner_name(item),
                "status": _text(item.get("state") or item.get("status")),
                "required": item.get("required") is not False,
                "affected_categories": [item.get("category") or "unknown"],
                "confidence_impact": "Material reduction" if item.get("required") is not False else "Disclosure only",
                "remediation": _failure_line(item),
            }
            for item in incomplete
        ],
        "scanner_execution_records": deepcopy(records),
        "completed_scanner_count": len(completed),
        "incomplete_scanner_count": len(incomplete),
        "single_normalized_scanner_population": True,
        "confidence_effect": (
            "All required scanner records completed with retained exact-SHA evidence."
            if not incomplete
            else "Incomplete scanner records reduce evidence assurance but are not treated as confirmed product defects."
        ),
    }

    stage_technical, stage_adjusted = _score_from_scoring_stage(canonical)
    weighted_technical, weighting = _weighted_score(sections)
    technical = weighted_technical if weighted_technical is not None else stage_technical
    if technical is None:
        technical = _numeric(assessment.get("technical_score"))
    adjusted_candidates = [
        stage_adjusted,
        _numeric(assessment.get("canonical_evidence_adjusted_score")),
        _numeric(assessment.get("evidence_adjusted_score")),
        technical,
    ]
    adjusted = next((item for item in adjusted_candidates if item is not None), None)
    if technical is not None and adjusted is not None:
        adjusted = min(technical, adjusted)

    band_key, band_label = _band(technical)
    maturity = _mapping(assessment.get("maturity_signal"))
    maturity.update({
        "score": technical,
        "source_score": technical,
        "presented_score": technical,
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "evidence_adjusted_score": adjusted,
        "score_band": band_key,
        "score_band_label": band_label,
        "scoring_method": "canonical_weighted_scored_controls_only_v2",
        "unscored_controls_excluded": [item["section_id"] for item in weighting if not item["included"]],
    })
    assessment.update({
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "evidence_adjusted_score": adjusted,
        "maturity_signal": maturity,
        "scoring_weights": weighting,
        "findings_register": deepcopy(canonical.get("canonical_findings") or []),
        "decision_grade_findings_register": deepcopy(canonical.get("canonical_findings") or []),
        "executive_risk_register": deepcopy(canonical.get("canonical_findings") or [])[:7],
        "dependency_dispositions": deepcopy(dispositions),
        "non_production_observations": deepcopy(canonical.get("non_production_observations") or []),
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "comprehensive_score_truth": {
            "technical_score": technical,
            "canonical_evidence_adjusted_score": adjusted,
            "aliases_synchronized": True,
            "weighted_scored_controls_only": True,
        },
    })
    summary = _text(assessment.get("executive_summary"))
    if summary:
        summary = re.sub(r"\bdraft\b", "final report pending human approval", summary, flags=re.I)
    else:
        summary = "NICO completed the automated Comprehensive assessment. The final report remains pending authorized human approval and is not authorized for client delivery."
    assessment["executive_summary"] = summary
    canonical["assessment"] = assessment
    canonical.update({
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "evidence_adjusted_score": adjusted,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "assessment_state": "review_required",
        "human_review_required": True,
        "client_delivery_allowed": False,
    })
    _repair_stages(canonical, records, technical, adjusted)
    canonical["v2_canonical_premium_truth"] = {
        "version": VERSION,
        "single_score_pair": True,
        "single_scanner_population": True,
        "stale_scanner_sections_replaced": True,
        "dependency_advisories_dispositioned": True,
        "raw_dependency_volume_not_confirmed_defect_volume": True,
        "non_production_code_patterns_excluded_from_score": True,
        "non_production_observations_retained": len(canonical.get("non_production_observations") or []),
        "finality_synchronized": True,
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
    }
    return canonical


__all__ = ["VERSION", "repair_canonical_premium_truth"]
