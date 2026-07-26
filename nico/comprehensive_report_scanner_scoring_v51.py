from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from nico.comprehensive_report_scanner_detection_v51 import _text, _walk_strings

VERSION = "nico.comprehensive_report_scanner_scoring.v51"

SECTION_WEIGHTS = {
    "code_audit": 0.20,
    "dependency_health": 0.15,
    "secrets_review": 0.15,
    "static_analysis": 0.15,
    "ci_cd": 0.15,
    "architecture_debt": 0.15,
    "velocity_complexity": 0.05,
}

def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(item.get("id"), 80).casefold(): item
        for item in assessment.get("sections") or []
        if isinstance(item, dict) and _text(item.get("id"), 80)
    }


def _contains_verified_blocker(section: dict[str, Any]) -> bool:
    combined = " ".join(
        _text(item).casefold()
        for field in ("evidence", "findings", "unavailable")
        for item in section.get(field) or []
    )
    zero = bool(re.search(r"(?:blocking|verified(?:_material| blockers?))\s*[=:]\s*0\b", combined))
    blocker = any(
        token in combined
        for token in (
            "confirmed critical",
            "confirmed high severity",
            "verified vulnerability",
            "verified exposure",
            "verified blocker",
        )
    )
    return blocker and not zero


def _section_execution_status(section_id: str, truth: dict[str, dict[str, Any]]) -> tuple[str, str]:
    groups = {
        "dependency_health": {"npm-audit", "pip-audit", "osv-scanner"},
        "secrets_review": {"gitleaks", "trufflehog"},
        "static_analysis": {"bandit", "eslint", "semgrep", "typescript"},
    }
    tools = groups.get(section_id)
    if tools is None:
        return "complete", "verified"
    observed = [truth[tool] for tool in tools if tool in truth]
    applicable = [item for item in observed if item.get("status") != "not_applicable"]
    if not observed:
        return "partial", "review_limited"
    statuses = {str(item.get("status")) for item in applicable}
    if "timed_out" in statuses or "failed" in statuses:
        return "partial", "review_limited"
    if "partial" in statuses or not applicable:
        return "partial", "review_limited"
    return "complete", "verified"


def _set_assurance(section: dict[str, Any], execution: str, assurance: str) -> None:
    label = "VERIFIED" if assurance == "verified" else "REVIEW LIMITED" if assurance == "review_limited" else "BLOCKED"
    tone = "green" if assurance == "verified" else "yellow" if assurance == "review_limited" else "red"
    section.update(
        {
            "execution_status": execution,
            "evidence_assurance": assurance,
            "assurance_status": assurance,
            "assurance_label": label,
            "assurance_display": label,
            "assurance_tone": tone,
            "finding_disposition": "OPEN" if section.get("findings") else "NO OPEN FINDINGS",
            "report_approval": "PENDING HUMAN APPROVAL",
        }
    )


def _static_score(section: dict[str, Any], truth: dict[str, dict[str, Any]]) -> None:
    if _contains_verified_blocker(section):
        return
    applicable = {
        tool
        for tool in ("semgrep", "typescript", "bandit", "eslint")
        if tool in truth and truth[tool].get("status") != "not_applicable"
    }
    completed = {tool for tool in applicable if truth[tool].get("status") == "complete"}
    if not {"semgrep", "typescript"}.issubset(completed):
        return
    combined = " ".join(_walk_strings(section)).casefold()
    zero_blockers = bool(
        re.search(r"(?:blocking|verified(?:_material| blockers?))\s*[=:]\s*0\b", combined)
        or "verified_material=0" in combined
        or "material=0" in combined
    )
    units = float(len(completed))
    if "bandit" in applicable and "bandit" not in completed and zero_blockers:
        units += 0.5
    coverage = round(100 * units / max(1, len(applicable)))
    score = max(70, min(85, 70 + round(15 * coverage / 100)))
    section.update(
        {
            "score": score,
            "source_score": score,
            "presented_score": score,
            "presented": score,
            "score_value": score,
            "score_band": "strong" if score >= 80 else "moderate",
            "score_band_label": "STRONG" if score >= 80 else "MODERATE",
            "score_tone": "green" if score >= 80 else "yellow",
            "technical_score_display": f"{'STRONG' if score >= 80 else 'MODERATE'} · {score}/100",
            "directly_scored": True,
            "exclude_from_maturity": False,
            "analyzer_execution_coverage": coverage,
            "analyzer_table": [deepcopy(record) for record in truth.values() if record["scanner_name"] in {"semgrep", "typescript", "bandit", "eslint"}],
            "score_treatment": "bounded_static_score_with_independent_assurance_v51",
            "score_rationale": (
                f"A bounded technical score of {score}/100 is supported by completed exact-snapshot Semgrep and TypeScript evidence, "
                f"{coverage}% accepted applicable-analyzer coverage, and no retained verified critical or high-severity blocker. "
                "Incomplete analyzers constrain assurance independently and do not erase the completed analyzer evidence."
            ),
            "summary": (
                f"Static Analysis is scored {score}/100 from completed analyzer evidence. Analyzer execution coverage is {coverage}%; "
                "remaining failed or partial tools are shown separately as Review Limited assurance."
            ),
        }
    )


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


def _normalize_assessment(assessment: dict[str, Any], truth: dict[str, dict[str, Any]]) -> dict[str, Any]:
    output = deepcopy(assessment)
    sections = _section_map(output)

    static = sections.get("static_analysis")
    if static:
        _static_score(static, truth)

    for section_id, section in sections.items():
        execution, assurance = _section_execution_status(section_id, truth)
        # Open findings are a disposition state, not evidence incompleteness. For
        # repository, CI, architecture, and velocity controls, retained current-run
        # evidence is sufficient to mark the evidence execution complete.
        if section_id not in {"dependency_health", "secrets_review", "static_analysis"}:
            execution = "complete" if section.get("evidence") or section.get("score") is not None else "partial"
            assurance = "verified" if execution == "complete" else "review_limited"
        _set_assurance(section, execution, assurance)

    rows: list[dict[str, Any]] = []
    numerator = 0.0
    denominator = 0.0
    adjusted_numerator = 0.0
    for section_id, section in sections.items():
        weight = SECTION_WEIGHTS.get(section_id, 0.0)
        raw = section.get("score_value", section.get("presented_score", section.get("score")))
        score = int(round(float(raw))) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        included = score is not None and weight > 0 and section.get("exclude_from_maturity") is not True
        assurance = str(section.get("assurance_status") or "review_limited")
        factor = 1.0 if assurance == "verified" else 0.95 if assurance == "review_limited" else 0.85
        contribution = round(score * weight, 2) if included else None
        if included:
            numerator += score * weight
            adjusted_numerator += score * factor * weight
            denominator += weight
        rows.append(
            {
                "control": section.get("label") or section_id,
                "section_id": section_id,
                "weight": weight,
                "weight_percent": round(weight * 100),
                "technical_score": score if included else None,
                "weighted_contribution": contribution,
                "assurance": section.get("assurance_label"),
                "execution_status": section.get("execution_status"),
                "finding_disposition": section.get("finding_disposition"),
                "included": included,
            }
        )

    technical = round(numerator / denominator) if denominator else None
    adjusted = round(adjusted_numerator / denominator) if denominator else None
    band_key, band_label = _band(technical)
    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    maturity.update(
        {
            "score": technical,
            "source_score": technical,
            "presented_score": technical,
            "technical_score": technical,
            "evidence_adjusted_score": adjusted,
            "score_band": band_key,
            "score_band_label": band_label,
            "scoring_method": "weighted_controls_with_independent_execution_and_assurance_v51",
            "unscored_controls_excluded": [row["section_id"] for row in rows if row["weight"] and not row["included"]],
        }
    )
    output["sections"] = list(sections.values())
    output["maturity_signal"] = maturity
    output["technical_score"] = technical
    output["evidence_adjusted_score"] = adjusted
    output["canonical_evidence_adjusted_score"] = adjusted
    output["scoring_weights"] = rows
    output["scanner_execution_records"] = [deepcopy(record) for record in truth.values()]

    completed = [tool for tool, record in truth.items() if record.get("status") == "complete"]
    incomplete = [deepcopy(record) for record in truth.values() if record.get("status") in {"partial", "failed", "timed_out"}]
    output["evidence_health_summary"] = {
        "structured_execution_records_present": bool(truth),
        "completed_scanners": completed,
        "incomplete_scanners": incomplete,
        "required_scanner_failures": [record["scanner_name"] for record in incomplete if record.get("required")],
        "scanner_status_counts": {
            status: sum(1 for record in truth.values() if record.get("status") == status)
            for status in ("complete", "partial", "failed", "timed_out", "not_applicable")
            if any(record.get("status") == status for record in truth.values())
        },
        "confidence_effect": (
            "The assessment completed. Analyzer limitations constrain only the controls they affect; completed controls retain their verified evidence status."
        ),
    }
    output["assessment_completion"] = {
        "assessment_execution": "complete",
        "artifact_generation": "complete",
        "scanner_execution": "partial" if incomplete else "complete",
        "evidence_assurance": "review_limited" if incomplete else "verified",
        "cross_format_verification": "pending_final_stage",
        "human_approval": "pending",
    }
    output["completion_status"] = "complete_with_disclosed_evidence_limitations" if incomplete else "complete"
    return output


def _scanner_execution_objects(records: list[dict[str, Any]]) -> list[Any]:
    from nico.decision_grade_contract_v1 import EvidenceStatus, ScannerExecutionRecord

    output: list[Any] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        status_value = str(raw.get("status") or "partial")
        try:
            status = EvidenceStatus(status_value)
        except ValueError:
            status = EvidenceStatus.PARTIAL
        output.append(
            ScannerExecutionRecord(
                scanner_name=str(raw.get("scanner_name") or "unknown"),
                scanner_version=raw.get("scanner_version"),
                status=status,
                started_at=raw.get("started_at"),
                finished_at=raw.get("finished_at"),
                duration_seconds=raw.get("duration_seconds"),
                retry_count=int(raw.get("retry_count") or 0),
                timeout_state=bool(raw.get("timeout_state")),
                failure_type=raw.get("failure_type"),
                failure_message=raw.get("failure_message"),
                evidence_categories_affected=list(raw.get("evidence_categories_affected") or []),
                score_controls_affected=list(raw.get("score_controls_affected") or []),
                confidence_impact=str(raw.get("confidence_impact") or "Execution status retained."),
                required=bool(raw.get("required")),
                remediation_guidance=raw.get("remediation_guidance"),
            )
        )
    return output


__all__ = ["VERSION", "_normalize_assessment", "_scanner_execution_objects"]
