from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_evidence_quality.v1"

_WEIGHTS = {
    "code_audit": 0.20,
    "dependency_health": 0.15,
    "dependency_library_ecosystem": 0.15,
    "secrets_review": 0.15,
    "static_analysis": 0.15,
    "ci_cd": 0.15,
    "ci_cd_analysis": 0.15,
    "architecture_debt": 0.15,
    "velocity_complexity": 0.05,
}

_TOOL_CONTROL = {
    "pip-audit": "dependency_health",
    "npm-audit": "dependency_health",
    "osv-scanner": "dependency_health",
    "gitleaks": "secrets_review",
    "trufflehog": "secrets_review",
    "bandit": "static_analysis",
    "semgrep": "static_analysis",
    "eslint": "static_analysis",
    "typescript": "static_analysis",
}

_ASSURANCE_FACTORS = {
    "verified": 1.00,
    "partial": 0.98,
    "review_limited": 0.95,
    "unavailable": 0.85,
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values if isinstance(values, list) else []:
        value = _text(raw)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _section_id(section: dict[str, Any]) -> str:
    value = _text(section.get("id")).casefold()
    aliases = {
        "dependency_library_ecosystem": "dependency_health",
        "ci_cd_analysis": "ci_cd",
    }
    return aliases.get(value, value)


def _section_score(section: dict[str, Any]) -> int | None:
    if section.get("directly_scored") is False or section.get("exclude_from_maturity") is True:
        return None
    for key in ("presented_score", "score", "source_score"):
        value = section.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0, min(100, int(round(value))))
    return None


def _combined(section: dict[str, Any]) -> str:
    return " ".join(
        _text(item)
        for field in ("evidence", "findings", "unavailable", "evidence_full", "findings_full", "unavailable_full")
        for item in section.get(field) or []
    )


def _tool_name_in(value: str) -> set[str]:
    lowered = value.casefold()
    return {tool for tool in _TOOL_CONTROL if tool in lowered}


def _filter_cross_control_limitations(section: dict[str, Any]) -> None:
    section_id = _section_id(section)
    retained: list[str] = []
    for item in _unique(section.get("unavailable")):
        tools = _tool_name_in(item)
        if tools and all(_TOOL_CONTROL[tool] != section_id for tool in tools):
            continue
        retained.append(item)
    section["unavailable"] = retained


def _required_signal_present(section: dict[str, Any]) -> bool:
    section_id = _section_id(section)
    text = _combined(section).casefold()
    evidence_count = len(_unique(section.get("evidence")))
    if section_id == "code_audit":
        return evidence_count > 0 and "snapshot" in text and any(token in text for token in ("source", "repository", "code"))
    if section_id == "dependency_health":
        return evidence_count > 0 and any(token in text for token in ("manifest", "lockfile", "pip-audit", "npm-audit", "osv"))
    if section_id == "secrets_review":
        return evidence_count > 0 and any(token in text for token in ("gitleaks", "trufflehog", "full-history", "full history"))
    if section_id == "static_analysis":
        return "semgrep" in text and "typescript" in text
    if section_id == "ci_cd":
        return evidence_count > 0 and any(token in text for token in ("workflow", "required check", "check run", "job evidence"))
    if section_id == "architecture_debt":
        return evidence_count > 0 and "complexity" in text and any(token in text for token in ("hotspot", "nesting", "coupling", "files analyzed"))
    if section_id == "velocity_complexity":
        return evidence_count > 0 and "commit" in text and any(token in text for token in ("pull-request", "pull request", "complexity", "ownership"))
    return evidence_count > 0


def _assurance(section: dict[str, Any]) -> tuple[str, str, str]:
    section_id = _section_id(section)
    status = _text(section.get("status") or section.get("presented_status")).casefold().replace("-", "_")
    text = _combined(section).casefold()
    limitations = _unique(section.get("unavailable"))
    score = _section_score(section)

    if "not_applicable" in status or "not applicable" in text:
        return "not_applicable", "Not applicable", "gray"
    if section_id == "static_analysis" and (score is None or "review_limited" in status):
        return "review_limited", "Review limited", "yellow"
    if not _unique(section.get("evidence")) and limitations:
        return "unavailable", "Unavailable", "gray"
    if _required_signal_present(section) and not limitations:
        return "verified", "Verified", "green"
    if _unique(section.get("evidence")):
        return "partial", "Partial", "yellow"
    return "unavailable", "Unavailable", "gray"


def _explicit_verified_static_blockers(section: dict[str, Any]) -> int:
    text = _combined(section)
    counts = [
        int(match.group(1))
        for pattern in (
            r"verified blockers?\s*[=:]\s*(\d+)",
            r"confirmed (?:critical|high(?:-severity)?) findings?\s*[=:]\s*(\d+)",
            r"blocking\s*[=:]\s*(\d+)",
        )
        for match in re.finditer(pattern, text, re.I)
    ]
    return max(counts, default=0)


def _static_candidate_total(section: dict[str, Any]) -> int:
    text = _combined(section)
    direct = re.search(r"\braw\s*=\s*(\d+)", text, re.I)
    if direct:
        return int(direct.group(1))
    values = [
        int(match.group(1))
        for match in re.finditer(
            r"exact-snapshot\s+(?:semgrep|typescript|bandit)\s+status=completed;\s*findings=(\d+)",
            text,
            re.I,
        )
    ]
    return sum(values)


def _rewrite_static(section: dict[str, Any]) -> None:
    raw = _static_candidate_total(section)
    material = min(raw, _explicit_verified_static_blockers(section))
    review_required = max(0, raw - material)

    evidence = [
        item
        for item in _unique(section.get("evidence"))
        if not re.search(r"static candidates:\s*raw=", item, re.I)
    ]
    if raw:
        evidence.append(
            f"Static candidates: raw={raw}; verified_material={material}; review_required={review_required}."
        )

    findings: list[str] = []
    limitations = _unique(section.get("unavailable"))
    limitation_keys = {item.casefold() for item in limitations}
    for item in _unique(section.get("findings")):
        lowered = item.casefold()
        if re.search(r"\d+\s+material static-analysis finding", item, re.I):
            continue
        if "failed static analyzers" in lowered or re.search(r"\b(?:bandit|eslint|semgrep|typescript)\b.*\bfailed\b", lowered):
            if lowered not in limitation_keys:
                limitations.append(item)
                limitation_keys.add(lowered)
            continue
        findings.append(item)

    if material:
        findings.insert(0, f"{material} verified high-severity static finding(s) require disposition.")
    if review_required:
        findings.append(
            f"{review_required} unverified static-analysis candidate(s) require human triage; candidate volume is not a confirmed defect count."
        )

    section["evidence"] = _unique(evidence)
    section["findings"] = _unique(findings)
    section["unavailable"] = _unique(limitations)
    section["static_candidate_classification"] = {
        "raw_candidates": raw,
        "verified_material": material,
        "review_required": review_required,
        "informational_or_nonblocking": 0,
        "candidate_volume_is_not_confirmed_defect_count": True,
    }
    if material == 0:
        score = _section_score(section)
        score_text = "not scored" if score is None else f"{score}/100"
        section["summary"] = (
            f"Static Analysis is {score_text} with review-limited assurance. Completed analyzer evidence remains visible, "
            "execution failures are treated as evidence limitations, and unverified candidates require human triage rather than being presented as confirmed material defects."
        )


def _canonical_adjusted_score(assessment: dict[str, Any]) -> tuple[int | None, list[dict[str, Any]]]:
    numerator = 0.0
    denominator = 0.0
    records: list[dict[str, Any]] = []
    for section in assessment.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _section_id(section)
        weight = _WEIGHTS.get(section_id, 0.0)
        score = _section_score(section)
        assurance = _text(section.get("assurance_status")).casefold()
        factor = _ASSURANCE_FACTORS.get(assurance)
        included = score is not None and weight > 0 and factor is not None
        if included:
            numerator += score * weight * factor
            denominator += weight
        records.append(
            {
                "section_id": section_id,
                "label": section.get("label") or section_id,
                "weight": weight,
                "technical_score": score,
                "included": included,
                "assurance_status": assurance or "unavailable",
                "assurance_factor": factor if included else None,
            }
        )

    if denominator:
        adjusted = int(round(numerator / denominator))
    else:
        adjusted = None
        for candidate in (
            assessment.get("canonical_evidence_adjusted_score"),
            assessment.get("evidence_adjusted_score"),
            (assessment.get("maturity_signal") or {}).get("evidence_adjusted_score") if isinstance(assessment.get("maturity_signal"), dict) else None,
        ):
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                adjusted = max(0, min(100, int(round(candidate))))
                break

    technical = assessment.get("technical_score")
    if not isinstance(technical, (int, float)) and isinstance(assessment.get("maturity_signal"), dict):
        technical = assessment["maturity_signal"].get("technical_score", assessment["maturity_signal"].get("score"))
    if isinstance(technical, (int, float)) and adjusted is not None:
        adjusted = min(int(round(technical)), adjusted)
    return adjusted, records


def normalize_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(assessment)
    sections = [section for section in output.get("sections") or [] if isinstance(section, dict)]
    for section in sections:
        _filter_cross_control_limitations(section)
        if _section_id(section) == "static_analysis":
            _rewrite_static(section)
        status, label, tone = _assurance(section)
        section["assurance_status"] = status
        section["assurance_label"] = label
        section["assurance_tone"] = tone
        section["evidence_completeness_status"] = status
        section["evidence_completeness_is_control_specific"] = True
        if _text(section.get("status")).casefold() == "incomplete":
            section["status"] = status
        if _text(section.get("presented_status")).casefold() == "incomplete":
            section["presented_status"] = status
    output["sections"] = sections

    adjusted, records = _canonical_adjusted_score(output)
    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    technical = output.get("technical_score", maturity.get("technical_score", maturity.get("score")))
    maturity["technical_score"] = technical
    maturity["score"] = technical
    maturity["source_score"] = technical
    maturity["presented_score"] = adjusted
    maturity["evidence_adjusted_score"] = adjusted
    maturity["canonical_evidence_adjusted_score"] = adjusted
    output["maturity_signal"] = maturity
    output["technical_score"] = technical
    output["evidence_adjusted_score"] = adjusted
    output["canonical_evidence_adjusted_score"] = adjusted
    output["scoring_weights"] = records

    repository = output.get("repository") or "the authorized repository"
    technical_text = "not scored" if technical is None else f"{int(technical)}/100"
    adjusted_text = "not scored" if adjusted is None else f"{adjusted}/100"
    output["executive_summary"] = (
        f"NICO completed an authorized Comprehensive Technical Assessment for {repository}. "
        f"Weighted technical maturity is {technical_text}; canonical evidence-adjusted readiness is {adjusted_text}. "
        "Evidence completeness is evaluated per control, open findings remain separate from assurance, and client delivery remains blocked pending exact-package human review."
    )
    output["control_specific_assurance"] = {
        "status": "complete",
        "version": VERSION,
        "statuses": ["verified", "partial", "review_limited", "not_applicable", "unavailable"],
        "blanket_incomplete_removed": True,
        "open_findings_separate_from_evidence_completeness": True,
    }
    output["canonical_evidence_score_contract"] = {
        "version": VERSION,
        "canonical_evidence_adjusted_score": adjusted,
        "calculated_once_after_control_specific_assurance": True,
        "immutable_for_downstream_report_formats": True,
    }
    return output


def normalize_scoring_result(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    assessment = output.get("assessment")
    if output.get("status") == "complete" and isinstance(assessment, dict):
        normalized = normalize_assessment(assessment)
        output["assessment"] = normalized
        evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
        evidence["technical_score"] = normalized.get("technical_score")
        evidence["evidence_adjusted_score"] = normalized.get("canonical_evidence_adjusted_score")
        evidence["canonical_evidence_adjusted_score"] = normalized.get("canonical_evidence_adjusted_score")
        output["evidence"] = evidence
    return output


def wrap_evidence_quality_provider(delegate: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    @wraps(delegate)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        return normalize_scoring_result(delegate(context))

    return wrapped


__all__ = [
    "VERSION",
    "normalize_assessment",
    "normalize_scoring_result",
    "wrap_evidence_quality_provider",
]
