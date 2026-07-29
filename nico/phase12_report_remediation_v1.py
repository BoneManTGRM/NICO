from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.phase9_production_report_gate_v1 import acceptance_key, contextual_title, finding_semantic_key, normalized_filename

VERSION = "nico.phase12.report-remediation.v1"
_STATUS_RANK = {"completed": 5, "success": 5, "not_applicable": 4, "partial": 3, "timed_out": 2, "failed": 1, "unknown": 0}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _criteria(values: Any) -> list[Any]:
    if isinstance(values, str):
        values = [part.strip() for part in values.split(";") if part.strip()]
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    output: list[Any] = []
    for value in values:
        key = acceptance_key(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _quality(item: Mapping[str, Any]) -> tuple[int, int, int]:
    populated = sum(bool(_text(item.get(key))) for key in ("cost_of_inaction", "residual_risk", "recommendation", "owner_role", "location"))
    mapped = int(bool(item.get("roadmap_ids") or item.get("roadmap") or item.get("backlog_id") or item.get("backlog")))
    return populated, mapped, len(_criteria(item.get("acceptance_criteria")))


def _specific_title(item: Mapping[str, Any]) -> str:
    title = _text(item.get("decision_title") or item.get("title"))
    location = _text(item.get("location"))
    symbol = _text(item.get("symbol") or item.get("function") or item.get("component"))
    lowered = title.casefold()
    if lowered == "high-complexity code hotspot":
        anchor = symbol or (location.split(":", 1)[0].rsplit("/", 1)[-1] if location else "code path")
        return f"Reduce complexity in {anchor}"
    if lowered == "delivery workflow reliability issue":
        return "Classify and eliminate recurring CI workflow failures"
    if lowered == "tls certificate verification disabled":
        return f"Verify TLS validation at {location or 'the reported call site'}"
    return contextual_title(item)


def _unsupported_tls_aggregate(item: Mapping[str, Any]) -> bool:
    title = _text(item.get("decision_title") or item.get("title")).casefold()
    if "tls certificate verification disabled" not in title:
        return False
    location = _text(item.get("location")).casefold()
    evidence = _text(item.get("evidence") or item.get("fact")).casefold()
    internal_rule_locations = ("phase5_report_truth", "scanner_evidence_pipeline", "test_phase5_report_truth", "tests/")
    return any(token in location for token in internal_rule_locations) and "verify=false" not in evidence and "ssl_context" not in evidence


def canonical_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    for raw in findings:
        item = deepcopy(dict(raw))
        if _unsupported_tls_aggregate(item):
            continue
        item["acceptance_criteria"] = _criteria(item.get("acceptance_criteria"))
        item["title"] = _specific_title(item)
        item["decision_title"] = item["title"]
        if _text(item.get("location")) == "location-not-retained" and _text(item.get("priority")).upper() == "P1":
            item["priority"] = "P2"
            item["severity"] = "medium"
            item["status"] = "review_limited"
        key = finding_semantic_key(item)
        if key not in selected:
            selected[key] = item
            order.append(key)
        elif _quality(item) > _quality(selected[key]):
            selected[key] = item
    return [selected[key] for key in order]


def _scanner_name(record: Mapping[str, Any]) -> str:
    return _text(record.get("scanner") or record.get("name") or record.get("tool")).casefold()


def canonical_scanner_records(records: Iterable[Mapping[str, Any]], *, commit_sha: str = "") -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for raw in records:
        item = deepcopy(dict(raw))
        name = _scanner_name(item)
        if not name:
            continue
        exact = not commit_sha or _text(item.get("commit_sha") or item.get("target_sha")) in {"", commit_sha}
        status = _text(item.get("status") or "unknown").casefold()
        score = (int(exact), _STATUS_RANK.get(status, 0), int(bool(item.get("artifact_hash") or item.get("output_sha256"))))
        current = best.get(name)
        if current is None or score > tuple(current.get("_selection_score") or (0, 0, 0)):
            item["_selection_score"] = score
            best[name] = item
    output = []
    for name in sorted(best):
        item = best[name]
        item.pop("_selection_score", None)
        output.append(item)
    return output


def _replace_findings_surfaces(assessment: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    for key in ("decision_grade_findings_register", "findings_register", "findings", "canonical_findings"):
        if key in assessment or key in {"findings_register", "canonical_findings"}:
            assessment[key] = deepcopy(findings)
    assessment["executive_risk_register"] = deepcopy(findings[:7])
    assessment["executive_risk_overflow_count"] = max(0, len(findings) - 7)
    assessment["executive_risk_register_limit"] = 7


def remediate_assessment(assessment: Mapping[str, Any], *, commit_sha: str = "") -> dict[str, Any]:
    result = deepcopy(dict(assessment))
    source = result.get("decision_grade_findings_register") or result.get("findings_register") or result.get("findings") or result.get("executive_risk_register") or []
    findings = canonical_findings(item for item in source if isinstance(item, Mapping))
    _replace_findings_surfaces(result, findings)
    evidence = result.get("evidence_health_summary")
    if isinstance(evidence, Mapping):
        summary = deepcopy(dict(evidence))
        records = summary.get("scanner_records") or summary.get("records") or summary.get("incomplete_scanner_records") or []
        if isinstance(records, list):
            canonical = canonical_scanner_records((item for item in records if isinstance(item, Mapping)), commit_sha=commit_sha)
            summary["scanner_records"] = canonical
            summary["incomplete_scanner_records"] = [item for item in canonical if _text(item.get("status")).casefold() not in {"completed", "success", "not_applicable"}]
            summary["completed_scanners"] = [_scanner_name(item) for item in canonical if _text(item.get("status")).casefold() in {"completed", "success"}]
        result["evidence_health_summary"] = summary
    result["phase12_report_remediation"] = {
        "version": VERSION,
        "canonical_finding_count": len(findings),
        "semantic_duplicates_removed": True,
        "acceptance_criteria_deduplicated": True,
        "generic_titles_replaced": True,
        "unsupported_internal_tls_aggregate_findings_removed": True,
        "stale_scanner_records_reconciled": True,
    }
    return result


def remediate_filename(filename: str, approval_state: str) -> str:
    return normalized_filename(filename, approval_state)


__all__ = ["VERSION", "canonical_findings", "canonical_scanner_records", "remediate_assessment", "remediate_filename"]
