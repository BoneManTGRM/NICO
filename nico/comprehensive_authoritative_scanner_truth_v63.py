from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_authoritative_scanner_truth_v62 import (
    reconcile_authoritative_scanner_truth as reconcile_v62,
)

VERSION = "nico.comprehensive_authoritative_scanner_truth.v63"
_MACHINE_COVERAGE_RE = re.compile(
    r"(?P<prefix>\b(?:analy[sz]er|scanner)(?:_execution)?_"
    r"(?:coverage|completion)(?:_percent)?\s*[:=]\s*)\d{1,3}",
    re.I,
)
_INCOMPLETE_ENTRY_RE = re.compile(
    r"\bincomplete_(?:analy[sz]ers|scanners)\[\d+\]\s*[:=]\s*"
    r"(?P<tool>[A-Za-z0-9_. -]+)",
    re.I,
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _names(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    output: list[str] = []
    for raw in value:
        name = " ".join(str(raw or "").split()).strip().casefold().replace("_", "-")
        if name and name not in output:
            output.append(name)
    return output


def _contract_truth(output: Mapping[str, Any]) -> tuple[list[str], list[str], list[str], int]:
    contract = _mapping(output.get("client_readiness_contract"))
    requested = _names(contract.get("requested_exact_run_scanners"))
    completed = _names(contract.get("completed_exact_commit_scanners"))
    incomplete = _names(contract.get("incomplete_analyzers"))
    try:
        denominator = int(contract.get("coverage_denominator") or len(requested))
    except (TypeError, ValueError):
        denominator = len(requested)
    denominator = max(denominator, len(requested), len(completed) + len(incomplete))
    coverage = round(100 * len(completed) / denominator) if denominator else 0
    return requested, completed, incomplete, coverage


def _repair_text(value: str, *, coverage: int, incomplete: set[str]) -> str | None:
    match = _INCOMPLETE_ENTRY_RE.search(value)
    if match:
        tool = " ".join(match.group("tool").split()).strip().casefold().replace("_", "-")
        if tool not in incomplete:
            return None
    return _MACHINE_COVERAGE_RE.sub(
        lambda match: f"{match.group('prefix')}{coverage}",
        value,
    )


def _repair_projection(node: Any, *, coverage: int, incomplete: set[str]) -> Any:
    if isinstance(node, str):
        return _repair_text(node, coverage=coverage, incomplete=incomplete)
    if isinstance(node, list):
        repaired: list[Any] = []
        for item in node:
            value = _repair_projection(item, coverage=coverage, incomplete=incomplete)
            if value is not None:
                repaired.append(value)
        return repaired
    if isinstance(node, Mapping):
        return {
            str(key): _repair_projection(value, coverage=coverage, incomplete=incomplete)
            for key, value in node.items()
        }
    return node


def _record_by_name(output: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    assessment = _mapping(output.get("assessment"))
    source = output.get("scanner_execution_records")
    if not isinstance(source, list):
        source = assessment.get("scanner_execution_records")
    records: dict[str, dict[str, Any]] = {}
    for raw in source or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        name = " ".join(
            str(
                item.get("scanner_name")
                or item.get("scanner")
                or item.get("tool")
                or item.get("name")
                or ""
            ).split()
        ).strip().casefold().replace("_", "-")
        if name:
            records[name] = item
    return records


def _sync_structured_contracts(
    output: dict[str, Any],
    *,
    requested: list[str],
    completed: list[str],
    incomplete: list[str],
    coverage: int,
) -> dict[str, Any]:
    denominator = max(len(requested), len(completed) + len(incomplete))
    records = _record_by_name(output)
    assessment = deepcopy(dict(_mapping(output.get("assessment"))))

    for key in ("analyzer_execution_coverage", "scanner_execution_coverage"):
        output[key] = coverage
        assessment[key] = coverage
    for key in ("completed_applicable_analyzers", "completed_applicable_scanners"):
        if key in output or key in assessment:
            output[key] = len(completed)
            assessment[key] = len(completed)
    for key in ("incomplete_applicable_analyzers", "incomplete_applicable_scanners"):
        if key in output or key in assessment:
            output[key] = len(incomplete)
            assessment[key] = len(incomplete)

    evidence_coverage = deepcopy(dict(_mapping(assessment.get("evidence_coverage"))))
    evidence_coverage.update(
        {
            "applicable_analyzers": denominator,
            "completed_verified_analyzers": len(completed),
            "incomplete_analyzers": list(incomplete),
            "analyzer_completion_percent": coverage,
            "analyzer_execution_coverage": coverage,
        }
    )
    assessment["evidence_coverage"] = evidence_coverage

    completion_contract = deepcopy(dict(_mapping(assessment.get("evidence_completion_contract"))))
    analyzer_completion = deepcopy(dict(_mapping(completion_contract.get("analyzer_completion"))))
    analyzer_completion.update(
        {
            "total": denominator,
            "completed": len(completed),
            "percent": coverage,
        }
    )
    analyzer_completion.setdefault("label", "Successful analyzer completion")
    analyzer_completion.setdefault(
        "definition",
        "Configured analyzers that completed successfully. Failed or partial analyzers remain visible and can block approval.",
    )
    completion_contract["analyzer_completion"] = analyzer_completion
    completion_contract["single_source_of_truth"] = True
    completion_contract["exact_run_scanner_truth_synchronized"] = True
    assessment["evidence_completion_contract"] = completion_contract

    health = deepcopy(dict(_mapping(assessment.get("evidence_health_summary"))))
    incomplete_rows: list[dict[str, Any]] = []
    for name in incomplete:
        item = deepcopy(records.get(name) or {"scanner": name})
        item.setdefault("scanner", name)
        item.setdefault("required", True)
        incomplete_rows.append(item)
    status_counts: dict[str, int] = {}
    for name in completed:
        raw_status = str(records.get(name, {}).get("status") or "complete").casefold().replace("-", "_")
        status = "complete" if raw_status in {"complete", "completed", "success", "succeeded", "passed"} else raw_status
        status_counts[status] = status_counts.get(status, 0) + 1
    for item in incomplete_rows:
        status = str(item.get("status") or item.get("state") or "incomplete").casefold().replace("-", "_")
        status_counts[status] = status_counts.get(status, 0) + 1
    health.update(
        {
            "completed_scanners": list(completed),
            "incomplete_scanners": incomplete_rows,
            "scanner_status_counts": status_counts,
            "required_scanner_failures": list(incomplete),
            "structured_execution_records_present": bool(records),
            "authoritative_exact_run_scanner_truth": True,
            "confidence_effect": (
                "No requested exact-run scanner remains incomplete; review candidates still require human disposition."
                if not incomplete
                else "Required scanner limitations remain visible and constrain evidence assurance until disposition."
            ),
        }
    )
    assessment["evidence_health_summary"] = health
    output["assessment"] = assessment

    contract = deepcopy(dict(_mapping(output.get("client_readiness_contract"))))
    contract.update(
        {
            "version": VERSION,
            "scanner_execution_completion": coverage,
            "analyzer_execution_coverage": coverage,
            "coverage_numerator": len(completed),
            "coverage_denominator": denominator,
            "requested_exact_run_scanners": list(requested),
            "completed_exact_commit_scanners": list(completed),
            "incomplete_analyzers": list(incomplete),
            "structured_evidence_completion_synchronized": True,
            "stage_summary_scanner_truth_synchronized": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    output["client_readiness_contract"] = contract
    return output


def reconcile_authoritative_scanner_truth(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile scanner truth plus every structured and rendered coverage projection.

    V62 made exact-run records and the requested-tools manifest authoritative. V63
    additionally repairs structured evidence-completion contracts and stage-summary
    evidence strings that legacy report assembly can restore after the first truth pass.
    No scanner is promoted to complete unless V62 already classified it as an exact-run
    completed scanner.
    """

    output = reconcile_v62(canonical)
    requested, completed, incomplete, coverage = _contract_truth(output)
    output = _sync_structured_contracts(
        output,
        requested=requested,
        completed=completed,
        incomplete=incomplete,
        coverage=coverage,
    )
    output = _repair_projection(
        output,
        coverage=coverage,
        incomplete=set(incomplete),
    )
    output["scanner_state_reconciled"] = True
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


__all__ = ["VERSION", "reconcile_authoritative_scanner_truth"]
