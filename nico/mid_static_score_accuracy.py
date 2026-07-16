from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS, full_assessment_scoring_handler

MID_STATIC_SCORE_ACCURACY_VERSION = "nico.mid_static_score_accuracy.v5"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _tools(scanner: dict[str, Any], key: str) -> set[str]:
    return {str(item).strip().lower() for item in _list(scanner.get(key)) if str(item).strip()}


def _typescript_state(scanner: dict[str, Any]) -> tuple[str, int]:
    run = _tools(scanner, "tools_run")
    failed = _tools(scanner, "failed_tools")
    timed_out = _tools(scanner, "timed_out_tools")
    unavailable = _tools(scanner, "unavailable_tools")
    requested = _tools(scanner, "tools_requested")
    if "typescript" in run:
        return "completed", 10
    if "typescript" in failed:
        return "failed", -12
    if "typescript" in timed_out:
        return "timed_out", -8
    if "typescript" in unavailable:
        return "unavailable", -5
    if "typescript" in requested:
        return "requested_without_terminal_evidence", 0
    return "not_requested", 0


def _maturity_level(score: int) -> str:
    if score >= 82:
        return "Senior"
    if score >= 58:
        return "Mid"
    return "Junior"


def _weighted_score(sections: list[dict[str, Any]]) -> int:
    by_id = {str(item.get("id") or ""): item for item in sections}
    weighted = 0
    total = 0
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = by_id.get(section_id)
        if not section or str(section.get("status") or "").lower() == "gray":
            continue
        try:
            score = max(0, min(100, int(section.get("score") or 0)))
        except (TypeError, ValueError):
            continue
        weighted += score * weight
        total += weight
    return round(weighted / total) if total else 0


def apply_typescript_static_evidence(
    assessment: dict[str, Any],
    scanner_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Apply TypeScript compiler state to the Mid static section exactly once.

    Mid explicitly requests the TypeScript compiler. The shared scorecard's
    static section historically counted Bandit, Semgrep, and ESLint but omitted
    TypeScript. This function corrects the completed Mid assessment after the
    shared scorecard is built, without changing parsed findings or affecting
    Express/Full scoring contracts.
    """

    output = deepcopy(assessment)
    sections = [deepcopy(item) for item in _list(output.get("sections")) if isinstance(item, dict)]
    static = next((item for item in sections if str(item.get("id") or "") == "static_analysis"), None)
    if static is None:
        output["mid_static_score_accuracy"] = {
            "status": "unavailable",
            "reason": "static_analysis_section_missing",
            "version": MID_STATIC_SCORE_ACCURACY_VERSION,
        }
        return output

    state, delta = _typescript_state(scanner_evidence)
    breakdown = _dict(static.get("score_evidence_breakdown"))
    if (
        breakdown.get("version") == MID_STATIC_SCORE_ACCURACY_VERSION
        and breakdown.get("typescript_state") == state
        and breakdown.get("typescript_accuracy_applied") is True
    ):
        return output

    try:
        previous = max(0, min(100, int(static.get("score") or 0)))
    except (TypeError, ValueError):
        previous = 0
    revised = max(0, min(88, previous + delta))
    static["score"] = revised
    static["status"] = "green" if revised >= 80 else "yellow" if revised >= 55 else "red"
    evidence = [str(item) for item in _list(static.get("evidence"))]
    note = f"TypeScript compiler static-analysis state={state}; bounded score adjustment={delta:+d}."
    if note not in evidence:
        evidence.append(note)
    static["evidence"] = evidence
    static["verified_claims"] = list(evidence)
    findings = [str(item) for item in _list(static.get("findings"))]
    if state in {"failed", "timed_out", "unavailable", "requested_without_terminal_evidence"}:
        finding = f"TypeScript static-analysis execution {state.replace('_', ' ')}; typed-code conclusions remain incomplete."
        if finding not in findings:
            findings.append(finding)
    static["findings"] = findings
    static["score_evidence_breakdown"] = {
        **breakdown,
        "pre_typescript_score": previous,
        "typescript_state": state,
        "typescript_score_adjustment": delta,
        "post_typescript_score": revised,
        "typescript_execution_treated_as_clean": False,
        "typescript_accuracy_applied": True,
        "score_forced_upward": False,
        "version": MID_STATIC_SCORE_ACCURACY_VERSION,
    }

    technical_score = _weighted_score(sections)
    maturity = deepcopy(_dict(output.get("maturity_signal")))
    maturity.update(
        {
            "score": technical_score,
            "level": _maturity_level(technical_score),
            "summary": "Weighted technical score derived from attached repository and completed same-run scanner evidence, including bounded TypeScript compiler execution state.",
        }
    )
    scorecard = deepcopy(_dict(output.get("scorecard")))
    scorecard["technical_score"] = technical_score
    scorecard["typescript_static_evidence_included"] = state != "not_requested"
    output["sections"] = sections
    output["maturity_signal"] = maturity
    output["scorecard"] = scorecard
    output["mid_static_score_accuracy"] = {
        "status": "complete",
        "version": MID_STATIC_SCORE_ACCURACY_VERSION,
        "typescript_state": state,
        "typescript_score_adjustment": delta,
        "static_score_before": previous,
        "static_score_after": revised,
        "technical_score_after": technical_score,
        "execution_treated_as_clean": False,
        "parsed_findings_changed": False,
        "express_score_changed": False,
        "full_score_changed": False,
        "human_review_required": True,
    }
    return output


def mid_scoring_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    """Run the shared evidence-bound scorecard, then apply Mid-only accuracy."""

    result = full_assessment_scoring_handler(context, outputs)
    if str(result.get("status") or "").lower() != "complete":
        return result
    assessment = _dict(result.get("assessment"))
    attachment = _dict(outputs.get("evidence_attachment"))
    scanner_evidence = _dict(attachment.get("scanner_evidence"))
    if not assessment or not scanner_evidence:
        return result

    adjusted = apply_typescript_static_evidence(assessment, scanner_evidence)
    result = deepcopy(result)
    result["assessment"] = adjusted
    evidence = deepcopy(_dict(result.get("evidence")))
    evidence["technical_score"] = _dict(adjusted.get("maturity_signal")).get("score", evidence.get("technical_score", 0))
    evidence["mid_static_score_accuracy"] = deepcopy(_dict(adjusted.get("mid_static_score_accuracy")))
    result["evidence"] = evidence
    result["message"] = "Mid Assessment multi-section scorecard was generated from same-run evidence with bounded TypeScript compiler state included."
    return result


__all__ = [
    "MID_STATIC_SCORE_ACCURACY_VERSION",
    "apply_typescript_static_evidence",
    "mid_scoring_handler",
]
