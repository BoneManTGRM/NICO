from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_report_truth_stabilization.v53"
_PATCH_MARKER = "_nico_comprehensive_report_truth_stabilization_v52"
_COMPLETED_SCANNER_STATES = {
    "complete",
    "completed",
    "completed_clean",
    "completed_with_findings",
    "passed",
    "success",
    "succeeded",
}
_FINDING_LIST_KEYS = {
    "canonical_findings",
    "decision_grade_findings_register",
    "executive_risk_register",
    "findings",
    "findings_register",
    "risks",
}
_SOURCE_EXTENSIONS = (
    "py",
    "pyi",
    "ts",
    "tsx",
    "js",
    "jsx",
    "mjs",
    "cjs",
    "java",
    "kt",
    "swift",
    "go",
    "rs",
    "rb",
    "php",
    "cs",
    "c",
    "cc",
    "cpp",
    "h",
    "hpp",
    "sh",
    "yml",
    "yaml",
    "toml",
    "json",
)
_SOURCE_RE = re.compile(
    rf"([A-Za-z0-9_.\-/]+\.(?:{'|'.join(_SOURCE_EXTENSIONS)}))",
    re.IGNORECASE,
)
_IDENTIFIER_REPLACEMENTS = (
    (re.compile(r"(?<![A-Za-z0-9_])_?\s*span\s+ish_pdf(?![A-Za-z0-9_])", re.I), "_spanish_pdf"),
    (re.compile(r"(?<![A-Za-z0-9_])_?\s*span\s+ish_markdown(?![A-Za-z0-9_])", re.I), "_spanish_markdown"),
    (re.compile(r"(?<![A-Za-z0-9_])co\s+llect_snapshot_repository_evidence(?![A-Za-z0-9_])", re.I), "collect_snapshot_repository_evidence"),
    (re.compile(r"(?<![A-Za-z0-9_])co\s+llect_complexity_evidence(?![A-Za-z0-9_])", re.I), "collect_complexity_evidence"),
    (re.compile(r"(?<![A-Za-z0-9_])appy_?\s+l\s+scanner_artifact_scoring(?![A-Za-z0-9_])", re.I), "apply_scanner_artifact_scoring"),
    (re.compile(r"(?<![A-Za-z0-9_])eva\s+luate_report_payload(?![A-Za-z0-9_])", re.I), "evaluate_report_payload"),
    (re.compile(r"(?<![A-Za-z0-9_])mar\s+kdown_report(?![A-Za-z0-9_])", re.I), "markdown_report"),
    (re.compile(r"(?<![A-Za-z0-9_])reso\s+lve_repository_commit(?![A-Za-z0-9_])", re.I), "resolve_repository_commit"),
    (re.compile(r"(?<![A-Za-z0-9_])production_\s+app(?![A-Za-z0-9_])", re.I), "production_app"),
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def _repair_text(value: str) -> str:
    output = value
    for pattern, replacement in _IDENTIFIER_REPLACEMENTS:
        output = pattern.sub(replacement, output)
    return output


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    return _normalized_text(value) in {
        "1",
        "exact",
        "matched",
        "retained",
        "true",
        "verified",
        "yes",
    }


def _canonical_tool(value: Any) -> str:
    normalized = _normalized_text(value).replace("_", "-")
    aliases = {
        "npm audit": "npm-audit",
        "osv": "osv-scanner",
        "osv scanner": "osv-scanner",
        "pip audit": "pip-audit",
        "truffle-hog": "trufflehog",
        "tsc": "typescript",
    }
    return aliases.get(normalized, normalized)


def _source_path(value: Any) -> str:
    text = _repair_text(str(value or ""))
    match = _SOURCE_RE.search(text)
    return match.group(1).casefold() if match else ""


def _function_name(item: dict[str, Any]) -> str:
    for key in ("function", "function_name", "component", "symbol", "name"):
        value = _normalized_text(_repair_text(str(item.get(key) or "")))
        if value:
            return value
    title = _repair_text(str(item.get("title") or item.get("summary") or ""))
    match = re.search(r"reduce\s+complexity\s+in\s+([^·\n]+)", title, re.I)
    if match:
        return _normalized_text(match.group(1).strip(" `.:"))
    return ""


def _rule_name(item: dict[str, Any]) -> str:
    for key in ("rule", "rule_id", "finding_type", "analyzer_rule", "category"):
        value = _normalized_text(item.get(key))
        if value:
            return value
    title = _normalized_text(item.get("title") or item.get("summary"))
    return "complexity_hotspot" if "reduce complexity in" in title else ""


def _source_identity(item: dict[str, Any]) -> tuple[str, str, str]:
    path = ""
    for key in ("path", "file", "source_path", "exact_source", "location"):
        path = _source_path(item.get(key))
        if path:
            break
    return path, _function_name(item), _rule_name(item)


def _string_finding_identity(value: str) -> tuple[str, str, str]:
    repaired = _repair_text(value)
    path = _source_path(repaired)
    function = ""
    match = re.search(r"reduce\s+complexity\s+in\s+([^·\n]+)", repaired, re.I)
    if match:
        function = _normalized_text(match.group(1).strip(" `.:"))
    rule = "complexity_hotspot" if function and path else ""
    return path, function, rule


def _is_finding(item: dict[str, Any]) -> bool:
    return bool(
        set(item).intersection(
            {
                "finding_id",
                "finding_type",
                "severity",
                "priority",
                "recommendation",
                "exact_source",
                "rule_id",
                "analyzer_rule",
            }
        )
    )


def _finding_identity(value: Any) -> tuple[str, str, str] | None:
    if isinstance(value, dict) and _is_finding(value):
        key = _source_identity(value)
        return key if key[0] and key[1] else None
    if isinstance(value, str) and "NICO-FINDING-" in value:
        key = _string_finding_identity(value)
        return key if key[0] and key[1] else None
    return None


def _prefer_richer(left: Any, right: Any) -> Any:
    if isinstance(left, dict) and isinstance(right, dict):
        left_score = len(str(left)) + len(left) * 16
        right_score = len(str(right)) + len(right) * 16
        winner_source = right if right_score > left_score else left
        loser = left if winner_source is right else right
        winner = deepcopy(winner_source)
        for key, value in loser.items():
            if key not in winner or winner.get(key) in (None, "", [], {}):
                winner[key] = deepcopy(value)
        return winner
    if isinstance(left, str) and isinstance(right, str):
        return right if len(right) > len(left) else left
    return right


def _dedupe_finding_list(values: list[Any]) -> list[Any]:
    output: list[Any] = []
    positions: dict[tuple[str, str, str], int] = {}
    for value in values:
        key = _finding_identity(value)
        if key is None:
            output.append(value)
            continue
        if key in positions:
            index = positions[key]
            output[index] = _prefer_richer(output[index], value)
        else:
            positions[key] = len(output)
            output.append(value)
    return output


def _authoritative_completed_scanners(node: Any) -> set[str]:
    completed: set[str] = set()
    if isinstance(node, dict):
        name = _canonical_tool(
            node.get("scanner_name") or node.get("scanner") or node.get("tool") or node.get("analyzer")
        )
        state = _normalized_text(
            node.get("status") or node.get("state") or node.get("execution_status")
        ).replace("-", "_")
        exact = any(
            _truthy(node.get(key))
            for key in (
                "exact_commit_match",
                "exact_sha",
                "exact_commit",
                "snapshot_match",
                "commit_match",
            )
        )
        artifact = bool(
            node.get("artifact_hash")
            or node.get("artifact_sha256")
            or _truthy(node.get("artifact"))
            or _truthy(node.get("artifact_retained"))
            or _truthy(node.get("verified"))
        )
        if name and state in _COMPLETED_SCANNER_STATES and exact and artifact:
            completed.add(name)
        for value in node.values():
            completed.update(_authoritative_completed_scanners(value))
    elif isinstance(node, list):
        for value in node:
            completed.update(_authoritative_completed_scanners(value))
    return completed


def _authoritative_scanner_truth(stage_results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from nico.comprehensive_report_scanner_detection_v51 import _scanner_truth

    truth = _scanner_truth(stage_results)
    authoritative = _authoritative_completed_scanners(stage_results)
    for tool in authoritative:
        record = deepcopy(truth.get(tool) or {})
        record.update(
            {
                "scanner_name": tool,
                "status": "complete",
                "required": record.get("required", tool != "eslint"),
                "timeout_state": False,
                "failure_type": None,
                "failure_message": None,
                "confidence_impact": (
                    "Verified exact-commit scanner execution completed and retained an artifact."
                ),
                "remediation_guidance": None,
                "source": "authoritative_exact_sha_artifact_reconciliation_v53",
            }
        )
        truth[tool] = record
    return truth


def _remove_stale_scanner_limitations(
    assessment: dict[str, Any], completed: set[str]
) -> dict[str, Any]:
    output = deepcopy(assessment)
    failure_terms = (
        "failed",
        "failure",
        "incomplete",
        "not complete",
        "output exceeded",
        "timed out",
        "timeout",
        "unavailable",
    )
    for section in output.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for field in ("findings", "unavailable"):
            values = section.get(field)
            if not isinstance(values, list):
                continue
            retained: list[Any] = []
            for value in values:
                text = _normalized_text(value)
                stale = any(tool in text for tool in completed) and any(
                    term in text for term in failure_terms
                )
                if not stale:
                    retained.append(value)
            section[field] = retained
    return output


def _score(value: Any) -> int | None:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _score_pair(node: Any) -> tuple[int | None, int | None]:
    technical: int | None = None
    adjusted: int | None = None
    if isinstance(node, dict):
        for key in ("canonical_technical_score", "technical_score"):
            candidate = _score(node.get(key))
            if candidate is not None:
                technical = candidate
                break
        for key in ("canonical_evidence_adjusted_score", "evidence_adjusted_score"):
            candidate = _score(node.get(key))
            if candidate is not None:
                adjusted = candidate
                break
        for value in node.values():
            child_technical, child_adjusted = _score_pair(value)
            technical = technical if technical is not None else child_technical
            adjusted = adjusted if adjusted is not None else child_adjusted
            if technical is not None and adjusted is not None:
                break
    elif isinstance(node, list):
        for value in node:
            child_technical, child_adjusted = _score_pair(value)
            technical = technical if technical is not None else child_technical
            adjusted = adjusted if adjusted is not None else child_adjusted
            if technical is not None and adjusted is not None:
                break
    return technical, adjusted


def _repair_contract_state(node: dict[str, Any]) -> None:
    reason = _normalized_text(node.get("report_contract_reason") or node.get("reason"))
    if reason != "canonical_evidence_adjusted_score_mismatch":
        return
    _, adjusted = _score_pair(node)
    canonical = _score(node.get("canonical_evidence_adjusted_score"))
    displayed = _score(node.get("evidence_adjusted_score"))
    if canonical is None:
        canonical = adjusted
    if displayed is None:
        displayed = adjusted
    if canonical is None or canonical != displayed:
        return
    if "report_contract_reason" in node:
        node["report_contract_reason"] = ""
    if node.get("reason") == "canonical_evidence_adjusted_score_mismatch":
        node["reason"] = ""
    if "report_contract_status" in node:
        node["report_contract_status"] = "ready_for_human_review"
    if node.get("status") == "blocked":
        node["status"] = "ready_for_human_review"


def _repair_tree(node: Any, *, key_hint: str = "") -> Any:
    if isinstance(node, str):
        return _repair_text(node)
    if isinstance(node, list):
        repaired = [_repair_tree(value) for value in node]
        if key_hint in _FINDING_LIST_KEYS or any(_finding_identity(value) for value in repaired):
            repaired = _dedupe_finding_list(repaired)
        return repaired
    if not isinstance(node, dict):
        return node
    repaired = {
        key: _repair_tree(value, key_hint=str(key))
        for key, value in node.items()
    }
    _repair_contract_state(repaired)
    return repaired


def _finding_metrics(node: Any) -> tuple[int, int, int]:
    exact: set[tuple[str, str, str]] = set()
    operational: set[str] = set()

    def walk(value: Any, key_hint: str = "") -> None:
        if isinstance(value, dict):
            if _is_finding(value):
                key = _finding_identity(value)
                if key:
                    exact.add(key)
                else:
                    finding_id = _normalized_text(value.get("finding_id") or value.get("id"))
                    if finding_id:
                        operational.add(finding_id)
            for key, child in value.items():
                walk(child, str(key))
        elif isinstance(value, list):
            if key_hint in _FINDING_LIST_KEYS:
                for child in value:
                    key = _finding_identity(child)
                    if key:
                        exact.add(key)
                    elif isinstance(child, dict):
                        finding_id = _normalized_text(child.get("finding_id") or child.get("id"))
                        if finding_id:
                            operational.add(finding_id)
                    elif isinstance(child, str):
                        match = re.search(r"NICO-FINDING-[A-F0-9]+", child, re.I)
                        if match:
                            operational.add(match.group(0).casefold())
            for child in value:
                walk(child)

    walk(node)
    return len(exact), len(operational), len(exact | {("", item, "") for item in operational})


def _apply_finding_metrics(node: Any, exact: int, operational: int, total: int) -> Any:
    if isinstance(node, str):
        value = re.sub(
            r"The canonical register contains \d+ unique decision-grade findings",
            f"The canonical register contains {total} unique decision-grade findings",
            node,
            flags=re.I,
        )
        value = re.sub(
            r"Exact-source findings:\s*\d+\s*·\s*Operational/context findings:\s*\d+",
            f"Exact-source findings: {exact} · Operational/context findings: {operational}",
            value,
            flags=re.I,
        )
        return value
    if isinstance(node, list):
        return [_apply_finding_metrics(value, exact, operational, total) for value in node]
    if not isinstance(node, dict):
        return node
    output = {
        key: _apply_finding_metrics(value, exact, operational, total)
        for key, value in node.items()
    }
    for key in ("unique_finding_count", "decision_grade_finding_count"):
        if key in output:
            output[key] = total
    for key in ("exact_source_finding_count", "exact_source_findings"):
        if key in output and isinstance(output[key], int):
            output[key] = exact
    for key in ("operational_finding_count", "operational_context_findings"):
        if key in output and isinstance(output[key], int):
            output[key] = operational
    return output


def _reconcile_scoring_stage(
    stages: dict[str, Any], truth: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    from nico.comprehensive_cross_format_finality_v49 import (
        synchronize_comprehensive_score_truth,
    )
    from nico.comprehensive_evidence_quality_v1 import normalize_assessment
    from nico.comprehensive_report_scanner_scoring_v51 import _normalize_assessment

    output = deepcopy(stages)
    scoring = output.get("evidence_reconciliation_and_scoring")
    if not isinstance(scoring, dict) or not isinstance(scoring.get("assessment"), dict):
        return output

    completed = {
        tool for tool, record in truth.items() if record.get("status") == "complete"
    }
    assessment = _remove_stale_scanner_limitations(scoring["assessment"], completed)
    assessment = _normalize_assessment(assessment, truth)
    assessment = normalize_assessment(assessment)
    assessment = synchronize_comprehensive_score_truth(assessment)
    assessment = _repair_tree(assessment)

    applicable = {
        tool: record
        for tool, record in truth.items()
        if record.get("status") != "not_applicable"
    }
    incomplete = sorted(
        tool for tool, record in applicable.items() if record.get("status") != "complete"
    )
    coverage = round(100 * (len(applicable) - len(incomplete)) / max(1, len(applicable)))
    technical = assessment.get("technical_score")
    adjusted = assessment.get("canonical_evidence_adjusted_score")

    scoring["assessment"] = assessment
    evidence = _dict(scoring.get("evidence"))
    evidence.update(
        {
            "technical_score": technical,
            "canonical_technical_score": technical,
            "evidence_adjusted_score": adjusted,
            "canonical_evidence_adjusted_score": adjusted,
            "incomplete_analyzers": incomplete,
            "analyzer_execution_coverage": coverage,
            "final_report_input_scores_synchronized": True,
            "scanner_state_reconciled_from_exact_sha_artifacts": True,
        }
    )
    scoring["evidence"] = evidence
    scoring["technical_score"] = technical
    scoring["canonical_technical_score"] = technical
    scoring["evidence_adjusted_score"] = adjusted
    scoring["canonical_evidence_adjusted_score"] = adjusted
    scoring["incomplete_analyzers"] = incomplete
    scoring["analyzer_execution_coverage"] = coverage
    scoring["scanner_execution_records"] = [deepcopy(record) for record in truth.values()]
    output["evidence_reconciliation_and_scoring"] = scoring
    return output


def prepare_report_stage_results(stage_results: dict[str, Any]) -> dict[str, Any]:
    """Reconcile scanner, score, finding, and identifier truth before rendering.

    Every client-visible format must be generated from this same repaired stage graph;
    post-render mutation is retained only as a defensive compatibility layer.
    """

    stages = _repair_tree(deepcopy(stage_results))
    truth = _authoritative_scanner_truth(stages)
    stages = _reconcile_scoring_stage(stages, truth)
    stages = _repair_tree(stages)
    exact, operational, total = _finding_metrics(stages)
    stages = _apply_finding_metrics(stages, exact, operational, total)
    return stages


def stabilize_report_package(result: dict[str, Any]) -> dict[str, Any]:
    output = _repair_tree(deepcopy(result))
    exact, operational, total = _finding_metrics(output)
    output = _apply_finding_metrics(output, exact, operational, total)

    package = _dict(output.get("report_package"))
    if package:
        canonical = _dict(package.get("json"))
        if canonical:
            canonical["unique_finding_count"] = total
            canonical["exact_source_finding_count"] = exact
            canonical["operational_finding_count"] = operational
            canonical["finding_register_deduplicated"] = True
            canonical["scanner_state_reconciled"] = True
            canonical["cross_format_score_truth_synchronized"] = True
            canonical["pre_render_truth_reconciliation"] = True
            package["json"] = canonical
        quality = _dict(package.get("report_quality_contract"))
        quality.update(
            {
                "finding_register_deduplicated": True,
                "scanner_state_reconciled": True,
                "pre_render_truth_reconciliation": True,
            }
        )
        _repair_contract_state(quality)
        package["report_quality_contract"] = quality
        output["report_package"] = package

    output.update(
        {
            "unique_finding_count": total,
            "exact_source_finding_count": exact,
            "operational_finding_count": operational,
            "finding_register_deduplicated": True,
            "scanner_state_reconciled": True,
            "cross_format_score_truth_synchronized": True,
            "pre_render_truth_reconciliation": True,
        }
    )
    return output


def install_comprehensive_report_truth_stabilization_v52() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico import comprehensive_native_providers as providers

    current: Callable[..., dict[str, Any]] = report.build_comprehensive_report_package
    if getattr(current, _PATCH_MARKER, False):
        providers.build_comprehensive_report_package = current
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def build_package(*args: Any, **kwargs: Any) -> dict[str, Any]:
        call_kwargs = dict(kwargs)
        stage_results = call_kwargs.get("stage_results")
        if isinstance(stage_results, dict):
            call_kwargs["stage_results"] = prepare_report_stage_results(stage_results)
        result = current(*args, **call_kwargs)
        return stabilize_report_package(result) if isinstance(result, dict) else result

    setattr(build_package, _PATCH_MARKER, True)
    setattr(build_package, "_nico_previous", current)
    report.build_comprehensive_report_package = build_package
    providers.build_comprehensive_report_package = build_package
    return {
        "status": "installed",
        "version": VERSION,
        "bound": report.build_comprehensive_report_package is build_package,
        "pre_render_truth_reconciliation": True,
        "finding_register_deduplicated": True,
        "scanner_state_reconciled": True,
        "canonical_score_contract_reconciled": True,
        "cross_format_identifier_repair": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_report_truth_stabilization_v52",
    "prepare_report_stage_results",
    "stabilize_report_package",
]
