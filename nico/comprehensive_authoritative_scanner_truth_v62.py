from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico import comprehensive_client_readiness_v59 as v59

VERSION = "nico.comprehensive_authoritative_scanner_truth.v62"
_REQUIRED_TOOLS = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _names(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    output: list[str] = []
    for item in value:
        name = v59._tool(item)
        if name and name not in output:
            output.append(name)
    return output


def _live_evidence(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    assessment = _mapping(canonical.get("assessment"))
    for candidate in (
        canonical.get("live_scanner_evidence"),
        assessment.get("live_scanner_evidence"),
        canonical.get("scanner_run_summary"),
        assessment.get("scanner_run_summary"),
    ):
        if isinstance(candidate, Mapping) and any(
            key in candidate
            for key in (
                "tools_requested",
                "tools_run",
                "failed_tools",
                "unavailable_tools",
                "timed_out_tools",
            )
        ):
            return candidate
    return {}


def _requested_tools(
    canonical: Mapping[str, Any],
    records: list[dict[str, Any]],
) -> list[str]:
    live = _live_evidence(canonical)
    requested = _names(live.get("tools_requested"))
    if requested:
        return requested

    direct: list[str] = []
    for record in records:
        name = v59._tool(record)
        if name and name not in direct:
            direct.append(name)
    if direct:
        return direct

    assessment = _mapping(canonical.get("assessment"))
    for candidate in (
        canonical.get("requested_analyzers"),
        canonical.get("applicable_analyzers"),
        assessment.get("requested_analyzers"),
        assessment.get("applicable_analyzers"),
    ):
        names = _names(candidate)
        if names:
            return names
    return []


def _failure_reason(name: str, live: Mapping[str, Any]) -> str:
    if name in set(_names(live.get("timed_out_tools"))):
        return f"{name} timed out before complete exact-SHA evidence was retained."
    if name in set(_names(live.get("unavailable_tools"))):
        return f"{name} was unavailable for the exact-run scanner execution."
    if name in set(_names(live.get("failed_tools"))):
        return f"{name} failed during the exact-run scanner execution."
    return f"{name} did not retain a complete exact-SHA scanner record."


def _authoritative_truth(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    records = v59._direct_scanner_records(canonical)
    truth: dict[str, dict[str, Any]] = {}
    for record in records:
        state = v59._scanner_state(record)
        if state is not None:
            truth[state["scanner_name"]] = state

    live = _live_evidence(canonical)
    requested = _requested_tools(canonical, records)
    failed = set(_names(live.get("failed_tools")))
    unavailable = set(_names(live.get("unavailable_tools")))
    timed_out = set(_names(live.get("timed_out_tools")))
    failed_or_missing = failed | unavailable | timed_out

    for name in requested:
        state = truth.get(name)
        if state is None:
            truth[name] = {
                "scanner_name": name,
                "status": "failed" if name in failed_or_missing else "missing",
                "completed": False,
                "verified": False,
                "exact_commit_match": False,
                "artifact_retained": False,
                "finding_count": 0,
                "failure_reason": _failure_reason(name, live),
            }
            continue
        if name in failed_or_missing:
            state.update(
                {
                    "status": "failed",
                    "completed": False,
                    "verified": False,
                    "failure_reason": state.get("failure_reason")
                    or _failure_reason(name, live),
                }
            )

    # Commercial Comprehensive reports use the fixed nine-tool contract. Do not
    # invent that denominator for partial fixtures, but do preserve it when the live
    # run explicitly requested the standard population.
    if set(requested) == set(_REQUIRED_TOOLS):
        requested = list(_REQUIRED_TOOLS)
    return truth, requested


def reconcile_authoritative_scanner_truth(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconcile all report aliases from exact-run records plus the live run manifest."""

    output = deepcopy(dict(canonical))
    truth, requested_tools = _authoritative_truth(output)
    requested = len(requested_tools) or len(truth)
    completed = {
        name
        for name, state in truth.items()
        if state.get("completed") is True and name in set(requested_tools or truth)
    }
    incomplete = set(requested_tools) - completed if requested_tools else {
        name for name, state in truth.items() if state.get("completed") is not True
    }

    assessment = _mapping(output.get("assessment"))
    technical = assessment.get("technical_score") or output.get("technical_score")
    try:
        technical_score = int(round(float(technical)))
    except (TypeError, ValueError):
        technical_score = None

    output = v59._normalize_tree(
        output,
        truth=truth,
        completed=completed,
        incomplete=incomplete,
        requested=requested,
        symbols=v59._symbols(output),
        technical_score=technical_score,
    )
    coverage = round(100 * len(completed) / requested) if requested else 0
    output["analyzer_execution_coverage"] = coverage
    output["scanner_execution_coverage"] = coverage
    output["completed_applicable_analyzers"] = len(completed)
    output["incomplete_applicable_analyzers"] = len(incomplete)

    contract = deepcopy(dict(output.get("client_readiness_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "scanner_execution_completion": coverage,
            "analyzer_execution_coverage": coverage,
            "coverage_numerator": len(completed),
            "coverage_denominator": requested,
            "requested_exact_run_scanners": list(requested_tools),
            "completed_exact_commit_scanners": sorted(completed),
            "incomplete_analyzers": sorted(incomplete),
            "authoritative_scanner_record_count": len(truth),
            "authoritative_source": "direct_exact_run_records_plus_live_scanner_manifest",
            "recursive_stale_projection_counts_ignored": True,
            "maturity_label": v59._maturity_label(technical_score),
            "technical_maturity_is_not_operational_readiness": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "approval_required_for_client_delivery": True,
            "cross_format_truth_required": True,
            "identifier_integrity_required": True,
        }
    )
    output["client_readiness_contract"] = contract
    output["scanner_state_reconciled"] = True
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


__all__ = [
    "VERSION",
    "reconcile_authoritative_scanner_truth",
]
