from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

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


def _repair_symbols(text: str, symbols: set[str]) -> str:
    repaired = text
    for symbol in sorted(symbols, key=len, reverse=True):
        pattern = r"(?<![A-Za-z0-9_])" + r"\s*".join(map(re.escape, symbol)) + r"(?![A-Za-z0-9_])"
        repaired = re.sub(pattern, symbol, repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bS\s+p\s+ecific correction\b", "Specific correction", repaired)
    return repaired


def _normalize_tree(
    node: Any,
    *,
    completed: set[str],
    requested: int,
    symbols: set[str],
    technical_score: int | None,
) -> Any:
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
        return _repair_symbols(node, symbols)
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

    if requested > 0:
        coverage = round(100 * len(completed) / requested)
        for key in (
            "analyzer_execution_coverage",
            "analyzer_coverage",
            "scanner_execution_coverage",
        ):
            if key in output:
                output[key] = coverage
        if "completed_applicable_analyzers" in output:
            output["completed_applicable_analyzers"] = len(completed)
        if "incomplete_applicable_analyzers" in output:
            output["incomplete_applicable_analyzers"] = max(0, requested - len(completed))

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

    requested = 0
    for key in ("requested_analyzers", "applicable_analyzers"):
        value = output.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            requested = max(requested, value)
        elif isinstance(value, list):
            requested = max(requested, len(value))
    requested = requested or len(completed)

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
    output["client_readiness_contract"] = {
        "version": VERSION,
        "scanner_execution_completion": coverage,
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
