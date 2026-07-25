from __future__ import annotations

import re
from typing import Any

from nico.decision_grade_contract_v1 import (
    DecisionGradeContract,
    EvidenceStatus,
    Finding,
    Priority,
    ScannerExecutionRecord,
)

VERSION = "nico.decision_grade_delta.v1"
_PRIORITY_ORDER = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2, Priority.P3: 3}
_FAILED_EVIDENCE = {
    EvidenceStatus.FAILED,
    EvidenceStatus.TIMED_OUT,
    EvidenceStatus.PERMISSION_UNAVAILABLE,
    EvidenceStatus.CONFLICTED,
    EvidenceStatus.STALE,
}
_RESOLVED_STATES = {"closed", "resolved", "remediated", "accepted", "suppressed"}


def _contract(value: DecisionGradeContract | dict[str, Any]) -> DecisionGradeContract:
    return value if isinstance(value, DecisionGradeContract) else DecisionGradeContract.model_validate(value)


def _score(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, min(100, int(round(value))))
    return None


def _scores(payload: dict[str, Any] | None) -> dict[str, int | None]:
    source = payload or {}
    maturity = source.get("maturity_signal") if isinstance(source.get("maturity_signal"), dict) else {}
    technical = next(
        (
            item
            for item in (
                _score(source.get("technical_score")),
                _score(maturity.get("technical_score")),
                _score(maturity.get("score")),
            )
            if item is not None
        ),
        None,
    )
    adjusted = next(
        (
            item
            for item in (
                _score(source.get("canonical_evidence_adjusted_score")),
                _score(source.get("evidence_adjusted_score")),
                _score(maturity.get("canonical_evidence_adjusted_score")),
                _score(maturity.get("evidence_adjusted_score")),
                _score(maturity.get("presented_score")),
            )
            if item is not None
        ),
        None,
    )
    return {"technical_score": technical, "evidence_adjusted_score": adjusted}


def _score_delta(previous: int | None, current: int | None) -> dict[str, Any]:
    if previous is None or current is None:
        return {"previous": previous, "current": current, "delta": None, "status": "not_comparable"}
    delta = current - previous
    return {
        "previous": previous,
        "current": current,
        "delta": delta,
        "status": "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged",
    }


def _category_gaps(contract: DecisionGradeContract) -> dict[str, list[str]]:
    gaps: dict[str, list[str]] = {}
    for scanner in contract.scanner_executions:
        if scanner.status not in _FAILED_EVIDENCE and scanner.status != EvidenceStatus.PARTIAL:
            continue
        categories = scanner.evidence_categories_affected or ["unknown"]
        for category in categories:
            normalized = str(category or "unknown").strip().casefold()
            gaps.setdefault(normalized, []).append(scanner.scanner_name)
    for evidence in contract.evidence_records:
        if evidence.collection_status not in _FAILED_EVIDENCE and evidence.collection_status != EvidenceStatus.PARTIAL:
            continue
        category = evidence.category.strip().casefold() or "unknown"
        gaps.setdefault(category, []).append(evidence.scanner_or_collector)
    return {key: sorted(set(values)) for key, values in gaps.items()}


def _finding_snapshot(finding: Finding) -> dict[str, Any]:
    return {
        "finding_id": finding.finding_id,
        "fingerprint": finding.fingerprint,
        "title": finding.title,
        "priority": finding.priority.value,
        "category": finding.category,
        "status": finding.current_status,
        "confidence": finding.confidence,
        "evidence_locations": finding.evidence_locations,
    }


def _matched_finding_delta(previous: Finding, current: Finding) -> dict[str, Any]:
    previous_resolved = previous.current_status.casefold() in _RESOLVED_STATES
    current_resolved = current.current_status.casefold() in _RESOLVED_STATES
    previous_rank = _PRIORITY_ORDER[previous.priority]
    current_rank = _PRIORITY_ORDER[current.priority]
    if previous_resolved and not current_resolved:
        change = "reopened"
    elif not previous_resolved and current_resolved:
        change = "closed"
    elif current_rank < previous_rank:
        change = "worsened"
    elif current_rank > previous_rank:
        change = "reduced"
    else:
        change = "unchanged"
    return {
        "change": change,
        "fingerprint": current.fingerprint,
        "previous": _finding_snapshot(previous),
        "current": _finding_snapshot(current),
        "location_changed": previous.evidence_locations != current.evidence_locations,
        "title_changed": previous.title != current.title,
    }


def _scanner_map(values: list[ScannerExecutionRecord]) -> dict[str, ScannerExecutionRecord]:
    return {item.scanner_name.casefold(): item for item in values}


def _scanner_rank(status: EvidenceStatus) -> int:
    return {
        EvidenceStatus.COMPLETE: 0,
        EvidenceStatus.NOT_APPLICABLE: 0,
        EvidenceStatus.EXCLUDED_BY_SCOPE: 0,
        EvidenceStatus.PARTIAL: 1,
        EvidenceStatus.STALE: 2,
        EvidenceStatus.PERMISSION_UNAVAILABLE: 3,
        EvidenceStatus.TIMED_OUT: 4,
        EvidenceStatus.FAILED: 5,
        EvidenceStatus.CONFLICTED: 6,
    }[status]


def _scanner_deltas(previous: DecisionGradeContract, current: DecisionGradeContract) -> list[dict[str, Any]]:
    previous_map = _scanner_map(previous.scanner_executions)
    current_map = _scanner_map(current.scanner_executions)
    output: list[dict[str, Any]] = []
    for name in sorted(set(previous_map) | set(current_map)):
        old = previous_map.get(name)
        new = current_map.get(name)
        if old is None and new is not None:
            change = "new_scanner"
        elif old is not None and new is None:
            change = "scanner_missing"
        elif old is not None and new is not None:
            old_rank = _scanner_rank(old.status)
            new_rank = _scanner_rank(new.status)
            change = "improved" if new_rank < old_rank else "regressed" if new_rank > old_rank else "unchanged"
        else:  # pragma: no cover - set union guarantees one side
            continue
        output.append(
            {
                "scanner_name": name,
                "change": change,
                "previous_status": old.status.value if old else None,
                "current_status": new.status.value if new else None,
                "required": bool((new or old).required),
            }
        )
    return output


def _complexity_value(finding: Finding, contract: DecisionGradeContract) -> float | None:
    texts: list[str] = [finding.factual_statement, finding.technical_interpretation]
    evidence_by_id = {item.evidence_id: item for item in contract.evidence_records}
    for evidence_id in finding.evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if not evidence:
            continue
        texts.extend(
            [
                str(evidence.raw_measurement or ""),
                str(evidence.normalized_measurement or ""),
                str(evidence.evidence_excerpt or ""),
            ]
        )
    for text in texts:
        match = re.search(r"cyclomatic_complexity\s*[=:]\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _complexity_deltas(
    previous: DecisionGradeContract,
    current: DecisionGradeContract,
    matched: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    previous_map = {item.fingerprint: item for item in previous.findings if item.category == "architecture"}
    current_map = {item.fingerprint: item for item in current.findings if item.category == "architecture"}
    output: list[dict[str, Any]] = []
    for item in matched:
        fingerprint = item["fingerprint"]
        old = previous_map.get(fingerprint)
        new = current_map.get(fingerprint)
        if not old or not new:
            continue
        old_value = _complexity_value(old, previous)
        new_value = _complexity_value(new, current)
        if old_value is None or new_value is None:
            continue
        delta = new_value - old_value
        output.append(
            {
                "fingerprint": fingerprint,
                "finding_id": new.finding_id,
                "title": new.title,
                "previous_complexity": old_value,
                "current_complexity": new_value,
                "delta": delta,
                "change": "improved" if delta < 0 else "worsened" if delta > 0 else "unchanged",
                "location_changed": item["location_changed"],
            }
        )
    return output


def _compatibility(previous: DecisionGradeContract, current: DecisionGradeContract) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if previous.identity.repository_identifier.casefold() != current.identity.repository_identifier.casefold():
        reasons.append("repository_mismatch")
    if previous.identity.assessment_type != current.identity.assessment_type:
        reasons.append("assessment_type_mismatch")
    if previous.schema_version.split(".v", 1)[0] != current.schema_version.split(".v", 1)[0]:
        reasons.append("schema_family_mismatch")
    if previous.identity.assessment_id == current.identity.assessment_id:
        reasons.append("same_assessment_identity")
    return not reasons, reasons


def compare_contracts(
    previous: DecisionGradeContract | dict[str, Any] | None,
    current: DecisionGradeContract | dict[str, Any],
    *,
    previous_assessment: dict[str, Any] | None = None,
    current_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_contract = _contract(current)
    if previous is None:
        return {
            "schema_version": VERSION,
            "status": "no_comparable_previous_assessment",
            "comparable": False,
            "reason": "No previous decision-grade contract was supplied.",
            "current_assessment_id": current_contract.identity.assessment_id,
            "synthetic_delta_generated": False,
        }
    previous_contract = _contract(previous)
    compatible, incompatibilities = _compatibility(previous_contract, current_contract)
    if not compatible:
        return {
            "schema_version": VERSION,
            "status": "incompatible",
            "comparable": False,
            "incompatibilities": incompatibilities,
            "previous_assessment_id": previous_contract.identity.assessment_id,
            "current_assessment_id": current_contract.identity.assessment_id,
            "synthetic_delta_generated": False,
        }

    previous_map = {item.fingerprint: item for item in previous_contract.findings}
    current_map = {item.fingerprint: item for item in current_contract.findings}
    current_gaps = _category_gaps(current_contract)
    matched: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []
    not_observed: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []

    for fingerprint in sorted(set(previous_map) & set(current_map)):
        matched.append(_matched_finding_delta(previous_map[fingerprint], current_map[fingerprint]))
    for fingerprint in sorted(set(previous_map) - set(current_map)):
        finding = previous_map[fingerprint]
        category = finding.category.casefold()
        affected = current_gaps.get(category) or current_gaps.get("unknown") or []
        snapshot = _finding_snapshot(finding)
        if affected:
            not_observed.append(
                {
                    "change": "not_observed_due_to_evidence_gap",
                    "previous": snapshot,
                    "missing_or_failed_evidence": affected,
                }
            )
        else:
            closed.append({"change": "closed", "previous": snapshot})
    for fingerprint in sorted(set(current_map) - set(previous_map)):
        new.append({"change": "new", "current": _finding_snapshot(current_map[fingerprint])})

    previous_scores = _scores(previous_assessment)
    current_scores = _scores(current_assessment)
    scanner_deltas = _scanner_deltas(previous_contract, current_contract)
    complexity_deltas = _complexity_deltas(previous_contract, current_contract, matched)
    finding_changes = {
        "new": new,
        "closed": closed,
        "not_observed_due_to_evidence_gap": not_observed,
        "reduced": [item for item in matched if item["change"] == "reduced"],
        "unchanged": [item for item in matched if item["change"] == "unchanged"],
        "worsened": [item for item in matched if item["change"] == "worsened"],
        "reopened": [item for item in matched if item["change"] == "reopened"],
        "resolved_by_status": [item for item in matched if item["change"] == "closed"],
    }
    return {
        "schema_version": VERSION,
        "status": "complete",
        "comparable": True,
        "previous_assessment_id": previous_contract.identity.assessment_id,
        "current_assessment_id": current_contract.identity.assessment_id,
        "previous_commit_sha": previous_contract.identity.assessed_commit_sha,
        "current_commit_sha": current_contract.identity.assessed_commit_sha,
        "score_deltas": {
            "technical_score": _score_delta(previous_scores["technical_score"], current_scores["technical_score"]),
            "evidence_adjusted_score": _score_delta(previous_scores["evidence_adjusted_score"], current_scores["evidence_adjusted_score"]),
        },
        "finding_changes": finding_changes,
        "scanner_changes": scanner_deltas,
        "complexity_changes": complexity_deltas,
        "summary": {
            "new_risks": len(new),
            "closed_risks": len(closed) + len(finding_changes["resolved_by_status"]),
            "reduced_risks": len(finding_changes["reduced"]),
            "unchanged_risks": len(finding_changes["unchanged"]),
            "worsened_risks": len(finding_changes["worsened"]),
            "reopened_risks": len(finding_changes["reopened"]),
            "closure_withheld_for_evidence_gap": len(not_observed),
            "scanner_improvements": sum(item["change"] == "improved" for item in scanner_deltas),
            "scanner_regressions": sum(item["change"] in {"regressed", "scanner_missing"} for item in scanner_deltas),
            "complexity_improvements": sum(item["change"] == "improved" for item in complexity_deltas),
            "complexity_regressions": sum(item["change"] == "worsened" for item in complexity_deltas),
        },
        "synthetic_delta_generated": False,
    }


def delta_markdown(delta: dict[str, Any]) -> str:
    lines = ["# Delta Since Previous Assessment", ""]
    if delta.get("status") != "complete":
        lines.append(str(delta.get("reason") or "The supplied assessments are not comparable."))
        incompatibilities = delta.get("incompatibilities") or []
        if incompatibilities:
            lines.append("")
            lines.append("Incompatibilities: " + ", ".join(str(item) for item in incompatibilities))
        return "\n".join(lines).rstrip() + "\n"
    summary = delta.get("summary") or {}
    scores = delta.get("score_deltas") or {}
    lines.extend(
        [
            f"- Technical score: {_score_line(scores.get('technical_score') or {})}",
            f"- Evidence-adjusted score: {_score_line(scores.get('evidence_adjusted_score') or {})}",
            f"- Risks closed: {summary.get('closed_risks', 0)}",
            f"- New risks: {summary.get('new_risks', 0)}",
            f"- Risks worsened: {summary.get('worsened_risks', 0)}",
            f"- Risks reopened: {summary.get('reopened_risks', 0)}",
            f"- Closures withheld because evidence disappeared or failed: {summary.get('closure_withheld_for_evidence_gap', 0)}",
            f"- Scanner improvements / regressions: {summary.get('scanner_improvements', 0)} / {summary.get('scanner_regressions', 0)}",
            f"- Complexity improvements / regressions: {summary.get('complexity_improvements', 0)} / {summary.get('complexity_regressions', 0)}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _score_line(value: dict[str, Any]) -> str:
    previous = value.get("previous")
    current = value.get("current")
    delta = value.get("delta")
    if delta is None:
        return "not comparable"
    sign = "+" if delta > 0 else ""
    return f"{previous} → {current} ({sign}{delta})"


__all__ = ["VERSION", "compare_contracts", "delta_markdown"]
