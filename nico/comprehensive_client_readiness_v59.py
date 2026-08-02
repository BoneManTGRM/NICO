from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from nico import comprehensive_report_truth_stabilization_v52 as legacy_truth

VERSION = "nico.comprehensive_client_readiness.v59"
_MARKER = "_nico_comprehensive_client_readiness_v59"
_COMPLETED = {
    "complete",
    "completed",
    "completed_clean",
    "completed_with_findings",
    "passed",
    "success",
    "succeeded",
}
_COVERAGE_KEY_RE = re.compile(r"(?:analy[sz]er|scanner).*(?:coverage|completion)|(?:coverage|completion).*(?:analy[sz]er|scanner)", re.I)
_COVERAGE_TEXT_RE = re.compile(
    r"(?P<label>(?:analy[sz]er|scanner)(?:\s+execution)?\s+(?:coverage|completion)\s*[:=]\s*)\d{1,3}(?P<pct>\s*%)?",
    re.I,
)
_KNOWN_IDENTIFIER_REPAIRS = {
    "appy_ l scanner_artifact_scoring": "apply_scanner_artifact_scoring",
    "appy_l scanner_artifact_scoring": "apply_scanner_artifact_scoring",
    " span ish_pdf": "_spanish_pdf",
    "span ish_pdf": "_spanish_pdf",
    "_ span ish_pdf": "_spanish_pdf",
    " span ish_markdown": "_spanish_markdown",
    "span ish_markdown": "_spanish_markdown",
    "_ span ish_markdown": "_spanish_markdown",
    "co llect_snapshot_repository_evidence": "collect_snapshot_repository_evidence",
    "eva luate_report_payload": "evaluate_report_payload",
    "mar kdown_report": "markdown_report",
    "production_ app": "production_app",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _tool(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    aliases = {
        "npm audit": "npm-audit",
        "osv": "osv-scanner",
        "osv scanner": "osv-scanner",
        "pip audit": "pip-audit",
        "truffle-hog": "trufflehog",
        "tsc": "typescript",
    }
    return aliases.get(normalized, normalized)


def _truthy(value: Any) -> bool:
    return value is True or _text(value).casefold() in {
        "1",
        "exact",
        "matched",
        "retained",
        "true",
        "verified",
        "yes",
    }


def _scanner_truth(node: Any) -> dict[str, dict[str, Any]]:
    truth: dict[str, dict[str, Any]] = {}
    if isinstance(node, Mapping):
        name = _tool(
            node.get("scanner_name")
            or node.get("scanner")
            or node.get("tool")
            or node.get("analyzer")
        )
        state = _text(
            node.get("status") or node.get("state") or node.get("execution_status")
        ).casefold().replace("-", "_")
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
        if name and exact and state in _COMPLETED:
            current = truth.get(name, {})
            truth[name] = {
                **current,
                "scanner_name": name,
                "status": state,
                "exact_commit_match": True,
                "artifact_retained": bool(
                    node.get("artifact_retained")
                    or node.get("artifact_hash")
                    or node.get("artifact")
                ),
                "finding_count": node.get("finding_count", node.get("findings", 0)),
            }
        for value in node.values():
            truth.update(_scanner_truth(value))
    elif isinstance(node, list):
        for value in node:
            truth.update(_scanner_truth(value))
    return truth


def _requested_analyzer_count(node: Any) -> int:
    candidates: list[int] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            normalized = str(key).casefold()
            if normalized in {
                "requested_analyzers",
                "applicable_analyzers",
                "requested_scanners",
                "applicable_scanners",
                "applicable_analyzer_count",
                "requested_analyzer_count",
                "applicable_scanner_count",
                "requested_scanner_count",
            }:
                if isinstance(value, int) and not isinstance(value, bool):
                    candidates.append(value)
                elif isinstance(value, list):
                    candidates.append(len(value))
            candidates.append(_requested_analyzer_count(value))
    elif isinstance(node, list):
        for value in node:
            candidates.append(_requested_analyzer_count(value))
    return max(candidates, default=0)


def _maturity_label(score: Any) -> str:
    try:
        value = int(round(float(score)))
    except (TypeError, ValueError):
        return "Not scored"
    if value >= 90:
        return "Exceptional"
    if value >= 80:
        return "Strong"
    if value >= 70:
        return "Moderate"
    if value >= 60:
        return "Developing"
    return "High risk"


def _symbols(node: Any) -> set[str]:
    output: set[str] = set()
    if isinstance(node, Mapping):
        for key in ("symbol", "function", "component", "function_name"):
            value = node.get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,}", value):
                output.add(value)
        for value in node.values():
            output.update(_symbols(value))
    elif isinstance(node, list):
        for value in node:
            output.update(_symbols(value))
    return output


def _repair_symbols(text: str, symbols: set[str], coverage: int) -> str:
    repaired = legacy_truth._repair_text(text) if hasattr(legacy_truth, "_repair_text") else text
    for broken, canonical in _KNOWN_IDENTIFIER_REPAIRS.items():
        repaired = re.sub(re.escape(broken), canonical, repaired, flags=re.IGNORECASE)
    for symbol in sorted(symbols, key=len, reverse=True):
        pattern = r"(?<![A-Za-z0-9_])" + r"\s*".join(map(re.escape, symbol)) + r"(?![A-Za-z0-9_])"
        repaired = re.sub(pattern, symbol, repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bS\s+p\s+ecific correction\b", "Specific correction", repaired)
    repaired = _COVERAGE_TEXT_RE.sub(
        lambda match: f"{match.group('label')}{coverage}{match.group('pct') or ''}",
        repaired,
    )
    return repaired


def _normalize_tree(
    node: Any,
    *,
    completed: set[str],
    requested: int,
    symbols: set[str],
    technical_score: int | None,
) -> Any:
    coverage = round(100 * len(completed) / requested) if requested else 0
    if isinstance(node, list):
        return [
            _normalize_tree(
                value,
                completed=completed,
                requested=requested,
                symbols=symbols,
                technical_score=technical_score,
            )
            for value in node
        ]
    if isinstance(node, str):
        return _repair_symbols(node, symbols, coverage)
    if not isinstance(node, Mapping):
        return node

    output = {
        key: _normalize_tree(
            value,
            completed=completed,
            requested=requested,
            symbols=symbols,
            technical_score=technical_score,
        )
        for key, value in node.items()
    }

    incomplete = output.get("incomplete_analyzers")
    if isinstance(incomplete, list):
        output["incomplete_analyzers"] = [
            value for value in incomplete if _tool(value) not in completed
        ]
    incomplete_scanners = output.get("incomplete_scanners")
    if isinstance(incomplete_scanners, list):
        output["incomplete_scanners"] = [
            value for value in incomplete_scanners if _tool(value) not in completed
        ]

    if requested > 0:
        for key in list(output):
            if _COVERAGE_KEY_RE.search(str(key)) and isinstance(output.get(key), (int, float)) and not isinstance(output.get(key), bool):
                output[key] = coverage
        if "completed_applicable_analyzers" in output:
            output["completed_applicable_analyzers"] = len(completed)
        if "completed_applicable_scanners" in output:
            output["completed_applicable_scanners"] = len(completed)
        if "incomplete_applicable_analyzers" in output:
            output["incomplete_applicable_analyzers"] = max(0, requested - len(completed))
        if "incomplete_applicable_scanners" in output:
            output["incomplete_applicable_scanners"] = max(0, requested - len(completed))

    if technical_score is not None:
        label = _maturity_label(technical_score)
        for key in ("maturity", "maturity_level", "maturity_label"):
            if key in output and isinstance(output.get(key), str):
                output[key] = label

    status = _text(output.get("status")).casefold()
    human_status = _text(output.get("human_evidence_status")).casefold()
    if status in {"complete", "completed"} and human_status in {
        "not_assessed",
        "missing",
        "unavailable",
    }:
        output["execution_status"] = "complete"
        output["evidence_status"] = "limited"
        output["requires_human_review"] = True

    return output


def reconcile_client_readiness(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(canonical))
    truth = _scanner_truth(output)
    completed = set(truth)

    requested = max(_requested_analyzer_count(output), len(completed))

    assessment = output.get("assessment") if isinstance(output.get("assessment"), Mapping) else {}
    technical = assessment.get("technical_score") or output.get("technical_score")
    try:
        technical_score = int(round(float(technical)))
    except (TypeError, ValueError):
        technical_score = None

    symbols = _symbols(output)
    output = _normalize_tree(
        output,
        completed=completed,
        requested=requested,
        symbols=symbols,
        technical_score=technical_score,
    )

    coverage = round(100 * len(completed) / requested) if requested else 0
    output["analyzer_execution_coverage"] = coverage
    output["scanner_execution_coverage"] = coverage
    output["completed_applicable_analyzers"] = len(completed)
    output["incomplete_applicable_analyzers"] = max(0, requested - len(completed))
    output["client_readiness_contract"] = {
        "version": VERSION,
        "scanner_execution_completion": coverage,
        "analyzer_execution_coverage": coverage,
        "coverage_numerator": len(completed),
        "coverage_denominator": requested,
        "completed_exact_commit_scanners": sorted(completed),
        "incomplete_analyzers": [],
        "maturity_label": _maturity_label(technical_score),
        "technical_maturity_is_not_operational_readiness": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "approval_required_for_client_delivery": True,
        "cross_format_truth_required": True,
        "identifier_integrity_required": True,
        "duplicate_detailed_finding_sections_allowed": False,
    }
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


def install_comprehensive_client_readiness_v59() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion

    current: Callable[[dict[str, Any]], dict[str, Any]] = completion._install_register
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def install_register(canonical: dict[str, Any]) -> dict[str, Any]:
        registered = current(canonical)
        return reconcile_client_readiness(registered)

    setattr(install_register, _MARKER, True)
    setattr(install_register, "_nico_previous", current)
    completion._install_register = install_register
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion._install_register is install_register,
        "scanner_state_canonicalized": True,
        "coverage_denominator_explicit": True,
        "all_coverage_aliases_synchronized": True,
        "maturity_terminology_unified": True,
        "identifier_integrity_repaired_before_render": True,
        "limited_evidence_status_separated_from_execution_status": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_client_readiness_v59",
    "reconcile_client_readiness",
]
