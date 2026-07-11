from __future__ import annotations

import hashlib
import json
from typing import Any

from nico.full_assessment_ci_score import full_assessment_scoring_with_ci_handler
from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in _list(assessment.get("sections"))
        if isinstance(item, dict) and item.get("id")
    }


def _append_unique(values: list[Any], line: str) -> None:
    if line not in values:
        values.append(line)


def _recompute_technical_score(assessment: dict[str, Any]) -> None:
    sections = _section_map(assessment)
    weighted = 0
    total = 0
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = sections.get(section_id)
        if not section or section.get("status") == "gray":
            continue
        weighted += _int(section.get("score")) * weight
        total += weight
    score = round(weighted / total) if total else 0
    level = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    signal = assessment.setdefault("maturity_signal", {})
    signal["score"] = score
    signal["level"] = level
    signal["summary"] = "Weighted technical score includes attached CI runtime and bounded complexity evidence without changing section weights."
    scorecard = assessment.setdefault("scorecard", {})
    scorecard["technical_score"] = score
    scorecard["weights"] = TECHNICAL_SECTION_WEIGHTS
    scorecard["complexity_evidence_applied"] = True


def _artifact_hash(complexity: dict[str, Any]) -> str:
    encoded = json.dumps(complexity, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _complexity_artifact(assessment: dict[str, Any], complexity: dict[str, Any]) -> dict[str, Any]:
    hotspots = [item for item in _list(complexity.get("hotspots")) if isinstance(item, dict)]
    duplicate = _dict(complexity.get("duplicate_evidence"))
    findings: list[str] = []
    for item in hotspots[:10]:
        findings.append(
            f"{item.get('path')}:{item.get('line')} {item.get('name')} complexity={item.get('cyclomatic_complexity')} loc={item.get('loc')} nesting={item.get('max_nesting')}."
        )
    if _int(duplicate.get("duplicate_block_groups")):
        findings.append(
            f"Cross-file duplicate analysis identified {_int(duplicate.get('duplicate_block_groups'))} duplicate block group(s) at a duplicate-line ratio of {_float(duplicate.get('duplicate_line_ratio')) or 0:.1%}."
        )
    return {
        "status": "completed",
        "verified_for_this_report": True,
        "report_run_id": assessment.get("run_id") or "",
        "repository": assessment.get("repository") or "",
        "generated_at": assessment.get("generated_at") or "",
        "artifact_hash": _artifact_hash(complexity),
        "evidence_id": complexity.get("evidence_id") or "",
        "analyzer_version": complexity.get("analyzer_version") or "nico-bounded-complexity-v1",
        "summary": {
            "source_file_count": _int(complexity.get("files_analyzed")),
            "source_loc": _int(complexity.get("total_source_loc")),
            "function_count": _int(complexity.get("functions_measured")),
            "average_cyclomatic_complexity": complexity.get("average_cyclomatic_complexity"),
            "maximum_cyclomatic_complexity": complexity.get("maximum_cyclomatic_complexity"),
            "high_complexity_functions": _int(complexity.get("high_complexity_functions")),
            "long_functions": _int(complexity.get("long_functions")),
            "deep_nesting_functions": _int(complexity.get("deep_nesting_functions")),
            "call_graph_edge_count": _int(complexity.get("internal_import_edges")),
            "import_edge_count": _int(complexity.get("import_edges")),
            "duplicate_block_groups": _int(duplicate.get("duplicate_block_groups")),
            "duplicate_line_ratio": duplicate.get("duplicate_line_ratio"),
        },
        "findings": findings,
        "retention_note": complexity.get("retention_note") or "Only bounded numeric and path-level complexity evidence is retained.",
        "guardrail": complexity.get("guardrail") or "Complexity evidence covers the authorized sampled source files only.",
    }


def apply_complexity_score(assessment: dict[str, Any], complexity: dict[str, Any]) -> dict[str, Any]:
    """Apply transparent score credit or penalties only from attached same-run complexity evidence."""

    scorecard = assessment.setdefault("scorecard", {})
    if complexity.get("status") != "attached" or _int(complexity.get("files_analyzed")) <= 0:
        scorecard["complexity_evidence_applied"] = False
        return assessment

    assessment_run_id = str(assessment.get("run_id") or "")
    evidence_run_id = str(complexity.get("run_id") or "")
    velocity = _section_map(assessment).get("velocity_complexity")
    if not velocity:
        scorecard["complexity_evidence_applied"] = False
        return assessment
    if not assessment_run_id or evidence_run_id != assessment_run_id:
        unavailable = velocity.setdefault("unavailable", [])
        _append_unique(unavailable, "Complexity evidence was not applied because its run_id did not match this Full Assessment run.")
        velocity["unverified_claims"] = list(unavailable)
        scorecard["complexity_evidence_applied"] = False
        return assessment

    baseline = _int(velocity.get("score"))
    increment = 0
    reasons: list[str] = []
    files_analyzed = _int(complexity.get("files_analyzed"))
    functions = _int(complexity.get("functions_measured"))
    average_complexity = _float(complexity.get("average_cyclomatic_complexity"))
    maximum_complexity = _int(complexity.get("maximum_cyclomatic_complexity"))
    high_complexity = _int(complexity.get("high_complexity_functions"))
    very_high = _int(complexity.get("very_high_complexity_functions"))
    high_ratio = _float(complexity.get("high_complexity_ratio"))
    long_functions = _int(complexity.get("long_functions"))
    deep_nesting = _int(complexity.get("deep_nesting_functions"))
    maximum_fan_out = _int(complexity.get("maximum_fan_out"))
    parse_failures = _int(complexity.get("python_parse_failures"))
    duplicate = _dict(complexity.get("duplicate_evidence"))
    duplicate_ratio = _float(duplicate.get("duplicate_line_ratio"))
    duplicate_groups = _int(duplicate.get("duplicate_block_groups"))

    if files_analyzed >= 20:
        increment += 3
        reasons.append(f"+3 complexity evidence covers {files_analyzed} source files")
    elif files_analyzed >= 10:
        increment += 2
        reasons.append(f"+2 complexity evidence covers {files_analyzed} source files")
    elif files_analyzed >= 3:
        increment += 1
        reasons.append(f"+1 complexity evidence covers {files_analyzed} source files")

    if functions >= 10 and average_complexity is not None:
        if average_complexity <= 5:
            increment += 3
            reasons.append(f"+3 average cyclomatic complexity is {average_complexity:.2f}")
        elif average_complexity <= 8:
            increment += 1
            reasons.append(f"+1 average cyclomatic complexity is {average_complexity:.2f}")
        elif average_complexity > 12:
            increment -= 3
            reasons.append(f"-3 average cyclomatic complexity is {average_complexity:.2f}")

    if functions and high_ratio is not None:
        if high_ratio <= 0.03:
            increment += 3
            reasons.append(f"+3 high-complexity function ratio is {high_ratio:.1%}")
        elif high_ratio <= 0.08:
            increment += 1
            reasons.append(f"+1 high-complexity function ratio is {high_ratio:.1%}")
        elif high_ratio > 0.20:
            increment -= 4
            reasons.append(f"-4 high-complexity function ratio is {high_ratio:.1%}")

    if maximum_complexity:
        if maximum_complexity <= 10:
            increment += 2
            reasons.append(f"+2 maximum measured complexity is {maximum_complexity}")
        elif maximum_complexity > 40:
            increment -= 4
            reasons.append(f"-4 maximum measured complexity is {maximum_complexity}")
        elif maximum_complexity > 25:
            increment -= 2
            reasons.append(f"-2 maximum measured complexity is {maximum_complexity}")

    if duplicate_ratio is not None:
        if duplicate_ratio <= 0.02:
            increment += 2
            reasons.append(f"+2 duplicate-line ratio is {duplicate_ratio:.1%}")
        elif duplicate_ratio <= 0.05:
            increment += 1
            reasons.append(f"+1 duplicate-line ratio is {duplicate_ratio:.1%}")
        elif duplicate_ratio > 0.15:
            increment -= 3
            reasons.append(f"-3 duplicate-line ratio is {duplicate_ratio:.1%}")

    if functions:
        deep_ratio = deep_nesting / functions
        long_ratio = long_functions / functions
        if deep_ratio <= 0.03:
            increment += 1
            reasons.append(f"+1 deep-nesting function ratio is {deep_ratio:.1%}")
        elif deep_ratio > 0.15:
            increment -= 2
            reasons.append(f"-2 deep-nesting function ratio is {deep_ratio:.1%}")
        if long_ratio > 0.20:
            increment -= 2
            reasons.append(f"-2 long-function ratio is {long_ratio:.1%}")

    if maximum_fan_out <= 10:
        increment += 1
        reasons.append(f"+1 maximum sampled import fan-out is {maximum_fan_out}")
    elif maximum_fan_out > 25:
        increment -= 2
        reasons.append(f"-2 maximum sampled import fan-out is {maximum_fan_out}")

    if parse_failures and parse_failures / max(1, files_analyzed + parse_failures) > 0.10:
        increment -= 1
        reasons.append(f"-1 Python parse failures affect {parse_failures} sampled file(s)")

    score = max(0, min(95, baseline + increment))
    velocity["score"] = score
    velocity["status"] = "green" if score >= 80 else "yellow" if score >= 55 else "red"
    velocity["confidence"] = (
        "ast-and-sampled-source-bound"
        if _int(complexity.get("javascript_typescript_files_analyzed")) == 0
        else "mixed-ast-and-lexical-sample"
    )
    velocity["summary"] = "Velocity / Complexity combines bounded commit and pull-request traceability with same-run source complexity, nesting, duplication, and import-coupling evidence."

    evidence = velocity.setdefault("evidence", [])
    _append_unique(
        evidence,
        f"Complexity engine analyzed {files_analyzed} sampled source file(s), {functions} measured function/module unit(s), and {_int(complexity.get('total_source_loc'))} source lines for this exact report run.",
    )
    _append_unique(
        evidence,
        f"Cyclomatic complexity: average={average_complexity if average_complexity is not None else 'unavailable'}, maximum={maximum_complexity or 'unavailable'}, high-complexity functions={high_complexity}, very-high-complexity functions={very_high}.",
    )
    _append_unique(
        evidence,
        f"Complexity hotspots: long functions={long_functions}, deep-nesting functions={deep_nesting}, maximum import fan-out={maximum_fan_out}.",
    )
    _append_unique(
        evidence,
        f"Cross-file duplicate evidence: groups={duplicate_groups}, duplicate-line ratio={duplicate_ratio if duplicate_ratio is not None else 'unavailable'}.",
    )
    velocity["verified_claims"] = list(evidence)

    findings = velocity.setdefault("findings", [])
    if high_complexity:
        _append_unique(findings, f"Review {high_complexity} function/module unit(s) with cyclomatic complexity of 11 or higher.")
    if very_high:
        _append_unique(findings, f"Prioritize {very_high} function/module unit(s) with cyclomatic complexity of 21 or higher.")
    if long_functions:
        _append_unique(findings, f"Review {long_functions} function/module unit(s) measuring at least 80 source lines.")
    if duplicate_groups:
        _append_unique(findings, f"Review {duplicate_groups} cross-file duplicate block group(s) before refactoring or consolidation.")

    unavailable = velocity.setdefault("unavailable", [])
    _append_unique(
        unavailable,
        "Complexity measurements cover the authorized sampled text files, not every repository object or runtime execution path.",
    )
    for note in _list(complexity.get("unavailable_data_notes")):
        _append_unique(unavailable, str(note))
    velocity["unverified_claims"] = list(unavailable)
    velocity["score_evidence_breakdown"] = {
        "baseline_score": baseline,
        "complexity_evidence_increment": increment,
        "final_score": score,
        "reasons": reasons,
        "weights_changed": False,
        "thresholds_changed": False,
    }

    assessment["complexity_artifact"] = _complexity_artifact(assessment, complexity)
    scorecard["complexity_runtime_evidence"] = {
        "status": complexity.get("status") or "unknown",
        "evidence_id": complexity.get("evidence_id") or "",
        "files_analyzed": files_analyzed,
        "functions_measured": functions,
        "average_cyclomatic_complexity": average_complexity,
        "maximum_cyclomatic_complexity": maximum_complexity,
        "high_complexity_functions": high_complexity,
        "duplicate_line_ratio": duplicate_ratio,
        "baseline_score": baseline,
        "final_score": score,
        "weights_changed": False,
    }
    _recompute_technical_score(assessment)
    return assessment


def full_assessment_scoring_with_complexity_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    result = full_assessment_scoring_with_ci_handler(context, outputs)
    if result.get("status") != "complete" or not isinstance(result.get("assessment"), dict):
        return result
    repo_output = _dict(outputs.get("repo_evidence"))
    complexity = _dict(repo_output.get("complexity_evidence"))
    result["assessment"] = apply_complexity_score(result["assessment"], complexity)
    scorecard = _dict(result["assessment"].get("scorecard"))
    result.setdefault("evidence", {})["technical_score"] = scorecard.get("technical_score", 0)
    result["evidence"]["complexity_evidence_applied"] = bool(scorecard.get("complexity_evidence_applied"))
    result["evidence"]["complexity_evidence_id"] = complexity.get("evidence_id") or ""
    return result
