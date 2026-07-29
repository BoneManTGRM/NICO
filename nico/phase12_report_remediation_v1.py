from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.phase9_production_report_gate_v1 import acceptance_key, contextual_title, normalized_filename

VERSION = "nico.phase13.canonical-findings.v2"
_STATUS_RANK = {"completed": 5, "success": 5, "not_applicable": 4, "partial": 3, "timed_out": 2, "failed": 1, "unknown": 0}
_GENERIC_FAMILIES = {
    "high-complexity code hotspot": "complexity_hotspot",
    "complexity hotspot": "complexity_hotspot",
    "delivery workflow reliability issue": "ci_reliability",
    "dependency vulnerability requires disposition": "dependency_candidate",
    "tls certificate verification disabled": "tls_verification",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_text(value: Any) -> str:
    text = _text(value).casefold()
    text = re.sub(r"\bRISK(?:-P[0-3])?-[A-Z0-9]+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[0-9a-f]{40,64}\b", "", text, flags=re.IGNORECASE)
    return " ".join(text.split()).strip(" ;·-")


def _path_line(item: Mapping[str, Any]) -> tuple[str, str]:
    location = item.get("location")
    if isinstance(location, Mapping):
        path = location.get("path") or location.get("file") or location.get("file_path")
        line = location.get("line") or location.get("start_line") or item.get("line")
        return _text(path).replace("\\", "/").casefold(), _text(line or "repository").casefold()
    raw = _text(location).replace("\\", "/")
    match = re.match(r"^(.*?):(\d+)(?::\d+)?$", raw)
    if match:
        return match.group(1).casefold(), match.group(2)
    return raw.casefold(), _text(item.get("line") or "repository").casefold()


def _family(item: Mapping[str, Any]) -> str:
    raw = _normalized_text(item.get("interpretation") or item.get("decision_title") or item.get("title"))
    if raw in _GENERIC_FAMILIES:
        return _GENERIC_FAMILIES[raw]
    rule = _normalized_text(item.get("rule_id") or item.get("rule") or item.get("check_id"))
    return rule or raw or "unspecified"


def canonical_fingerprint(item: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    path, line = _path_line(item)
    category = _normalized_text(item.get("category") or "uncategorized")
    symbol = _normalized_text(item.get("symbol") or item.get("function") or item.get("component"))
    return path, line, category, symbol, _family(item)


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
            output.append(deepcopy(value))
    return output


def _list_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [deepcopy(item) for item in value]
    return [deepcopy(value)]


def _dedupe_values(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    output: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        if key not in seen:
            seen.add(key)
            output.append(deepcopy(value))
    return output


def _quality(item: Mapping[str, Any]) -> tuple[int, int, int, int, str]:
    populated = sum(
        bool(_text(item.get(key)))
        for key in (
            "cost_of_inaction",
            "residual_risk",
            "recommendation",
            "owner_role",
            "business_impact",
            "evidence",
            "location",
        )
    )
    mapped = sum(bool(item.get(key)) for key in ("roadmap_ids", "roadmap", "backlog_id", "backlog"))
    criteria = len(_criteria(item.get("acceptance_criteria")))
    evidence_count = len(_list_values(item.get("evidence_records") or item.get("supporting_evidence")))
    stable_id = _text(item.get("finding_id") or item.get("id"))
    return populated, mapped, criteria, evidence_count, stable_id


def _specific_title(item: Mapping[str, Any]) -> str:
    title = _text(item.get("decision_title") or item.get("title") or item.get("interpretation"))
    location = _text(item.get("location"))
    symbol = _text(item.get("symbol") or item.get("function") or item.get("component"))
    family = _family(item)
    if family == "complexity_hotspot":
        anchor = symbol or (location.split(":", 1)[0].rsplit("/", 1)[-1] if location else "code path")
        return f"Reduce complexity in {anchor}"
    if family == "ci_reliability":
        return "Classify and eliminate recurring CI workflow failures"
    if family == "tls_verification":
        return f"Verify TLS validation at {location or 'the reported call site'}"
    return contextual_title(item) or title


def _unsupported_tls_aggregate(item: Mapping[str, Any]) -> bool:
    if _family(item) != "tls_verification":
        return False
    location = _text(item.get("location")).casefold()
    evidence = _text(item.get("evidence") or item.get("fact")).casefold()
    internal_rule_locations = ("phase5_report_truth", "scanner_evidence_pipeline", "test_phase5_report_truth", "tests/")
    return any(token in location for token in internal_rule_locations) and "verify=false" not in evidence and "ssl_context" not in evidence


def _merge_records(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    preferred, secondary = (right, left) if _quality(right) > _quality(left) else (left, right)
    merged = deepcopy(dict(preferred))
    for key, value in secondary.items():
        if key not in merged or merged.get(key) in (None, "", [], {}):
            merged[key] = deepcopy(value)

    merged["acceptance_criteria"] = _criteria(
        _list_values(preferred.get("acceptance_criteria")) + _list_values(secondary.get("acceptance_criteria"))
    )
    for key in ("roadmap_ids", "roadmap", "backlog_ids", "backlog", "affected_files", "affected_symbols"):
        values = _list_values(preferred.get(key)) + _list_values(secondary.get(key))
        if values:
            merged[key] = _dedupe_values(values)

    aliases = _list_values(preferred.get("finding_aliases")) + _list_values(secondary.get("finding_aliases"))
    aliases += [preferred.get("finding_id") or preferred.get("id"), secondary.get("finding_id") or secondary.get("id")]
    merged["finding_aliases"] = [value for value in _dedupe_values(aliases) if _text(value)]

    evidence_records = _list_values(preferred.get("evidence_records") or preferred.get("supporting_evidence"))
    evidence_records += _list_values(secondary.get("evidence_records") or secondary.get("supporting_evidence"))
    for source in (preferred, secondary):
        compact = {
            key: deepcopy(source.get(key))
            for key in ("finding_id", "id", "tool", "rule_id", "evidence", "fact", "location", "symbol")
            if source.get(key) not in (None, "", [], {})
        }
        if compact:
            evidence_records.append(compact)
    merged["supporting_evidence"] = _dedupe_values(evidence_records)
    merged["canonical_fingerprint"] = hashlib.sha256(
        json.dumps(canonical_fingerprint(merged), separators=(",", ":")).encode()
    ).hexdigest()[:20]
    merged["title"] = _specific_title(merged)
    merged["decision_title"] = merged["title"]
    return merged


def canonical_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str, str]] = []
    for raw in findings:
        item = deepcopy(dict(raw))
        if _unsupported_tls_aggregate(item):
            continue
        item["acceptance_criteria"] = _criteria(item.get("acceptance_criteria"))
        if _text(item.get("location")) == "location-not-retained" and _text(item.get("priority")).upper() == "P1":
            item["priority"] = "P2"
            item["severity"] = "medium"
            item["status"] = "review_limited"
        key = canonical_fingerprint(item)
        if key not in selected:
            item["finding_aliases"] = [value for value in [item.get("finding_id") or item.get("id")] if _text(value)]
            item["canonical_fingerprint"] = hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()[:20]
            item["title"] = _specific_title(item)
            item["decision_title"] = item["title"]
            selected[key] = item
            order.append(key)
        else:
            selected[key] = _merge_records(selected[key], item)
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
    result["phase13_canonical_findings"] = {
        "version": VERSION,
        "canonical_finding_count": len(findings),
        "semantic_duplicates_removed": True,
        "supporting_evidence_merged": True,
        "finding_aliases_retained": True,
        "acceptance_criteria_deduplicated": True,
        "generic_titles_replaced": True,
        "unsupported_internal_tls_aggregate_findings_removed": True,
        "stale_scanner_records_reconciled": True,
        "preferred_record_order_stable": True,
    }
    return result


def remediate_filename(filename: str, approval_state: str) -> str:
    return normalized_filename(filename, approval_state)


__all__ = [
    "VERSION",
    "canonical_fingerprint",
    "canonical_findings",
    "canonical_scanner_records",
    "remediate_assessment",
    "remediate_filename",
]
