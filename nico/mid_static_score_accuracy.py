from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS, full_assessment_scoring_handler

MID_STATIC_SCORE_ACCURACY_VERSION = "nico.mid_static_score_accuracy.v5"
MID_VERIFIED_CONTROL_RECONCILIATION_VERSION = "nico.mid_verified_control_reconciliation.v1"

DEPENDENCY_TOOLS = {"pip-audit", "npm-audit", "osv-scanner"}
STATIC_TOOLS = {"bandit", "semgrep", "eslint", "typescript"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _tools(scanner: dict[str, Any], key: str) -> set[str]:
    return {str(item).strip().lower() for item in _list(scanner.get(key)) if str(item).strip()}


def _verified_tools(scanner: dict[str, Any]) -> set[str]:
    results = [item for item in _list(scanner.get("scanner_results")) if isinstance(item, dict)]
    if not results:
        return _tools(scanner, "tools_run")
    return {
        str(item.get("tool") or item.get("scanner") or "").strip().lower()
        for item in results
        if str(item.get("status") or "").lower() == "completed"
        and item.get("verified_for_this_report") is not False
        and item.get("current_run") is not False
        and str(item.get("tool") or item.get("scanner") or "").strip()
    }


def _category_counts(scanner: dict[str, Any], category: str) -> dict[str, int]:
    summary = _dict(scanner.get("finding_summary"))
    value = _dict(summary.get("by_category")).get(category)
    if isinstance(value, dict):
        return {
            "raw": _int(value.get("raw")),
            "material": _int(value.get("material")),
            "review_required": _int(value.get("review_required")),
            "approved_or_nonblocking": _int(value.get("approved_or_nonblocking")),
            "excluded_test_only": _int(value.get("excluded_test_only")),
        }
    raw = _int(value)
    severity = _dict(_dict(summary.get("severity_by_category")).get(category))
    material = _int(severity.get("critical")) + _int(severity.get("high"))
    return {
        "raw": raw,
        "material": material,
        "review_required": max(0, raw - material),
        "approved_or_nonblocking": 0,
        "excluded_test_only": 0,
    }


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
    return "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"


def _weighted_score(sections: list[dict[str, Any]]) -> int:
    by_id = {str(item.get("id") or ""): item for item in sections}
    weighted = 0
    total = 0
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = by_id.get(section_id)
        if not section or str(section.get("status") or "").lower() == "gray":
            continue
        weighted += max(0, min(100, _int(section.get("score")))) * weight
        total += weight
    return round(weighted / total) if total else 0


def _append_unique(items: list[Any], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _status(score: int) -> str:
    return "green" if score >= 80 else "yellow" if score >= 55 else "red"


def _apply_candidate(
    section: dict[str, Any],
    *,
    candidate: int,
    evidence_note: str,
    breakdown: dict[str, Any],
) -> tuple[int, int]:
    previous = max(0, min(100, _int(section.get("score"))))
    bounded_candidate = max(0, min(88, int(candidate)))
    revised = max(previous, bounded_candidate)
    section["score"] = revised
    section["status"] = _status(revised)
    evidence = [str(item) for item in _list(section.get("evidence"))]
    _append_unique(evidence, evidence_note)
    section["evidence"] = evidence
    section["verified_claims"] = list(evidence)
    section["score_evidence_breakdown"] = {
        **_dict(section.get("score_evidence_breakdown")),
        **breakdown,
        "verified_reconciliation_pre_score": previous,
        "verified_reconciliation_candidate_score": bounded_candidate,
        "verified_reconciliation_final_score": revised,
        "score_increased_from_verified_evidence": revised > previous,
        "score_forced_upward": False,
        "version": MID_VERIFIED_CONTROL_RECONCILIATION_VERSION,
    }
    return previous, revised


def _refresh_scorecard(output: dict[str, Any], sections: list[dict[str, Any]], summary: str) -> None:
    technical_score = _weighted_score(sections)
    maturity = deepcopy(_dict(output.get("maturity_signal")))
    maturity.update({"score": technical_score, "level": _maturity_level(technical_score), "summary": summary})
    scorecard = deepcopy(_dict(output.get("scorecard")))
    scorecard["technical_score"] = technical_score
    output["sections"] = sections
    output["maturity_signal"] = maturity
    output["scorecard"] = scorecard


def apply_typescript_static_evidence(
    assessment: dict[str, Any],
    scanner_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Apply the Mid-only TypeScript execution state exactly once."""

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
        breakdown.get("typescript_version") == MID_STATIC_SCORE_ACCURACY_VERSION
        and breakdown.get("typescript_state") == state
        and breakdown.get("typescript_accuracy_applied") is True
    ):
        return output

    previous = max(0, min(100, _int(static.get("score"))))
    revised = max(0, min(88, previous + delta))
    static["score"] = revised
    static["status"] = _status(revised)
    evidence = [str(item) for item in _list(static.get("evidence"))]
    _append_unique(evidence, f"TypeScript compiler static-analysis state={state}; bounded score adjustment={delta:+d}.")
    static["evidence"] = evidence
    static["verified_claims"] = list(evidence)
    findings = [str(item) for item in _list(static.get("findings"))]
    if state in {"failed", "timed_out", "unavailable", "requested_without_terminal_evidence"}:
        _append_unique(findings, f"TypeScript static-analysis execution {state.replace('_', ' ')}; typed-code conclusions remain incomplete.")
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
        "typescript_version": MID_STATIC_SCORE_ACCURACY_VERSION,
    }

    _refresh_scorecard(
        output,
        sections,
        "Weighted technical score derived from attached repository and completed same-run scanner evidence, including bounded TypeScript compiler execution state.",
    )
    output["scorecard"]["typescript_static_evidence_included"] = state != "not_requested"
    output["mid_static_score_accuracy"] = {
        "status": "complete",
        "version": MID_STATIC_SCORE_ACCURACY_VERSION,
        "typescript_state": state,
        "typescript_score_adjustment": delta,
        "static_score_before": previous,
        "static_score_after": revised,
        "technical_score_after": output["maturity_signal"]["score"],
        "execution_treated_as_clean": False,
        "parsed_findings_changed": False,
        "express_score_changed": False,
        "full_score_changed": False,
        "human_review_required": True,
    }
    return output


def apply_verified_control_reconciliation(
    assessment: dict[str, Any],
    repository_evidence: dict[str, Any],
    scanner_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Correct undercredited Mid controls only from verified exact-snapshot evidence."""

    output = deepcopy(assessment)
    if (
        repository_evidence.get("status") != "attached"
        or scanner_evidence.get("status") != "attached"
        or scanner_evidence.get("snapshot_match") is not True
    ):
        return output

    sections = [deepcopy(item) for item in _list(output.get("sections")) if isinstance(item, dict)]
    by_id = {str(item.get("id") or ""): item for item in sections}
    verified = _verified_tools(scanner_evidence)
    failed = _tools(scanner_evidence, "failed_tools")
    timed_out = _tools(scanner_evidence, "timed_out_tools")
    unavailable = _tools(scanner_evidence, "unavailable_tools")
    verified_dependency = verified & DEPENDENCY_TOOLS
    verified_static = verified & STATIC_TOOLS
    dependency_counts = _category_counts(scanner_evidence, "dependency")
    static_counts = _category_counts(scanner_evidence, "static")

    files = _dict(repository_evidence.get("file_evidence"))
    architecture = _dict(repository_evidence.get("architecture_evidence"))
    activity = _dict(repository_evidence.get("activity_evidence"))
    dependencies = _dict(repository_evidence.get("dependency_evidence"))
    signals = _dict(repository_evidence.get("code_signal_evidence"))
    changes: dict[str, dict[str, int]] = {}

    code = by_id.get("code_audit")
    if code is not None and static_counts["material"] == 0:
        risks = _int(signals.get("risk_pattern_hits"))
        candidate = 36
        candidate += 10 if _int(files.get("files_profiled")) >= 10 else 5 if _int(files.get("files_profiled")) else 0
        candidate += 10 if _int(architecture.get("source_file_count")) >= 5 else 5 if _int(architecture.get("source_file_count")) else 0
        candidate += 12 if _int(architecture.get("test_path_count")) >= 3 else 6 if _int(architecture.get("test_path_count")) else 0
        candidate += 6 if _int(architecture.get("documentation_path_count")) else 0
        candidate += 5 if _int(activity.get("commits_returned")) else 0
        candidate += 5 if _int(activity.get("pull_requests_returned")) else 0
        candidate += min(6, len(verified_static) * 2)
        candidate -= min(6, risks)
        candidate -= min(4, _int(signals.get("todo_fixme_security_notes")))
        candidate -= len(failed & STATIC_TOOLS) * 6
        candidate -= len(timed_out & STATIC_TOOLS) * 4
        candidate -= len(unavailable & STATIC_TOOLS)
        before, after = _apply_candidate(
            code,
            candidate=candidate,
            evidence_note=(
                f"Mid exact-snapshot reconciliation verified {len(verified_static)}/{len(STATIC_TOOLS)} static analyzer(s); "
                f"material static findings=0. The {risks} sampled risk-pattern signal(s) remain review indicators, not confirmed production defects."
            ),
            breakdown={
                "verified_static_tool_count": len(verified_static),
                "sampled_risk_pattern_count": risks,
                "material_static_finding_count": 0,
                "sampled_patterns_treated_as_confirmed_defects": False,
            },
        )
        changes["code_audit"] = {"before": before, "after": after}

    dependency = by_id.get("dependency_health")
    if dependency is not None and dependency_counts["material"] == 0:
        candidate = 38
        candidate += 14 if _list(dependencies.get("manifest_paths")) else 0
        candidate += 14 if _list(dependencies.get("lockfile_paths")) else 0
        candidate += 10 if _int(dependencies.get("dependency_entries")) else 0
        candidate += min(24, len(verified_dependency) * 8)
        candidate += 6 if len(verified_dependency) >= 2 else 0
        candidate -= len(failed & DEPENDENCY_TOOLS) * 8
        candidate -= len(timed_out & DEPENDENCY_TOOLS) * 5
        candidate -= len(unavailable & DEPENDENCY_TOOLS) * 2
        before, after = _apply_candidate(
            dependency,
            candidate=candidate,
            evidence_note=(
                f"Mid exact-snapshot dependency reconciliation verified {len(verified_dependency)}/{len(DEPENDENCY_TOOLS)} dependency analyzer(s); "
                f"material dependency findings=0, review-required={dependency_counts['review_required']}, test-only excluded={dependency_counts['excluded_test_only']}."
            ),
            breakdown={
                "verified_dependency_tool_count": len(verified_dependency),
                "material_dependency_finding_count": 0,
                "dependency_review_required_count": dependency_counts["review_required"],
                "dependency_test_only_excluded_count": dependency_counts["excluded_test_only"],
            },
        )
        changes["dependency_health"] = {"before": before, "after": after}

    static = by_id.get("static_analysis")
    if static is not None and static_counts["material"] == 0:
        risks = _int(signals.get("risk_pattern_hits"))
        candidate = 52 + min(32, len(verified_static) * 8)
        candidate += 6 if len(verified_static) >= 2 else 0
        candidate += 4 if risks == 0 else -min(4, risks)
        candidate -= len(failed & STATIC_TOOLS) * 8
        candidate -= len(timed_out & STATIC_TOOLS) * 5
        candidate -= len(unavailable & STATIC_TOOLS)
        before, after = _apply_candidate(
            static,
            candidate=candidate,
            evidence_note=(
                f"Mid exact-snapshot static reconciliation verified {len(verified_static)}/{len(STATIC_TOOLS)} analyzer(s); "
                f"material findings=0, review-required={static_counts['review_required']}, test-only excluded={static_counts['excluded_test_only']}."
            ),
            breakdown={
                "verified_static_tool_count": len(verified_static),
                "material_static_finding_count": 0,
                "static_review_required_count": static_counts["review_required"],
                "static_test_only_excluded_count": static_counts["excluded_test_only"],
                "execution_coverage_treated_as_clean": False,
            },
        )
        changes["static_analysis"] = {"before": before, "after": after}

    _refresh_scorecard(
        output,
        sections,
        "Weighted Mid technical score reconciled to verified exact-snapshot repository and analyzer evidence; material findings, failed tools, and missing evidence remain adverse.",
    )
    output["scorecard"]["mid_verified_control_reconciliation"] = True
    output["mid_verified_control_reconciliation"] = {
        "status": "complete",
        "version": MID_VERIFIED_CONTROL_RECONCILIATION_VERSION,
        "verified_dependency_tools": sorted(verified_dependency),
        "verified_static_tools": sorted(verified_static),
        "dependency_material_findings": dependency_counts["material"],
        "static_material_findings": static_counts["material"],
        "section_changes": changes,
        "technical_score_after": output["maturity_signal"]["score"],
        "findings_removed": False,
        "missing_evidence_treated_as_clean": False,
        "material_findings_can_receive_upward_reconciliation": False,
        "express_score_changed": False,
        "full_score_changed": False,
        "human_review_required": True,
    }
    return output


def mid_scoring_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    result = full_assessment_scoring_handler(context, outputs)
    if str(result.get("status") or "").lower() != "complete":
        return result

    assessment = _dict(result.get("assessment"))
    attachment = _dict(outputs.get("evidence_attachment"))
    scanner_evidence = _dict(attachment.get("scanner_evidence"))
    if not assessment or not scanner_evidence:
        return result

    adjusted = apply_typescript_static_evidence(assessment, scanner_evidence)
    repo_output = _dict(outputs.get("repo_evidence"))
    repository_evidence = _dict(repo_output.get("repository_evidence"))
    if repository_evidence:
        adjusted = apply_verified_control_reconciliation(adjusted, repository_evidence, scanner_evidence)

    result = deepcopy(result)
    result["assessment"] = adjusted
    evidence = deepcopy(_dict(result.get("evidence")))
    evidence["technical_score"] = _dict(adjusted.get("maturity_signal")).get("score", evidence.get("technical_score", 0))
    evidence["mid_static_score_accuracy"] = deepcopy(_dict(adjusted.get("mid_static_score_accuracy")))
    if adjusted.get("mid_verified_control_reconciliation"):
        evidence["mid_verified_control_reconciliation"] = deepcopy(_dict(adjusted.get("mid_verified_control_reconciliation")))
    result["evidence"] = evidence
    result["message"] = "Mid Assessment scorecard was generated from same-run evidence with verified exact-snapshot reconciliation where available."
    return result


__all__ = [
    "MID_STATIC_SCORE_ACCURACY_VERSION",
    "MID_VERIFIED_CONTROL_RECONCILIATION_VERSION",
    "apply_typescript_static_evidence",
    "apply_verified_control_reconciliation",
    "mid_scoring_handler",
]
