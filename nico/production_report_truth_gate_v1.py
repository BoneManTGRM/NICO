from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from nico.report_artifact_filename_v1 import normalize_report_artifact_filenames

VERSION = "nico.production-report-truth-gate.v1"
_TERMINAL_BAD = {"failed", "missing", "unavailable", "error", "timed_out", "timeout"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _name(value: Any) -> str:
    return _text(value).casefold().replace("_", "-")


def _status(record: Mapping[str, Any]) -> str:
    return _text(record.get("status") or record.get("state")).casefold().replace("-", "_")


def _record_rank(record: Mapping[str, Any]) -> tuple[int, ...]:
    status = _status(record)
    artifact = _text(record.get("artifact_hash"))
    return (
        int(record.get("current_run") is True),
        int(record.get("execution_observed_for_this_report") is True),
        int(record.get("exact_commit_match") is True),
        int(record.get("verified_complete") is True),
        int(record.get("verified_for_this_report") is True or record.get("verified") is True),
        int(status.startswith("completed")),
        int(bool(artifact and artifact not in {"missing", "unavailable"})),
        int(status not in _TERMINAL_BAD),
    )


def _canonical_scanners(canonical: Mapping[str, Any], assessment: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source in (
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
        canonical.get("scanner_records"),
        assessment.get("scanner_records"),
    ):
        for raw in source or []:
            if isinstance(raw, Mapping):
                candidates.append(deepcopy(dict(raw)))

    selected: dict[str, dict[str, Any]] = {}
    for record in candidates:
        scanner = _name(record.get("scanner_name") or record.get("tool"))
        if not scanner:
            continue
        prior = selected.get(scanner)
        if prior is None or _record_rank(record) > _record_rank(prior):
            selected[scanner] = record

    output: list[dict[str, Any]] = []
    for scanner in sorted(selected):
        record = selected[scanner]
        status = _status(record) or "unknown"
        record["scanner_name"] = scanner
        record["tool"] = scanner
        record["status"] = status
        record["state"] = status
        record["completed"] = status.startswith("completed")
        artifact = _text(record.get("artifact_hash"))
        exact = record.get("exact_commit_match") is True
        capture = record.get("raw_artifact_retention_complete") is True or (
            not record.get("timed_out") and not record.get("output_truncated") and status.startswith("completed")
        )
        record["raw_artifact_retention_complete"] = bool(capture)
        record["verified_complete"] = bool(
            status.startswith("completed")
            and exact
            and capture
            and artifact
            and artifact not in {"missing", "unavailable"}
            and (not record.get("scans_git_history") or record.get("full_history_verified") is True)
        )
        output.append(record)
    return output


def _score_pair(canonical: Mapping[str, Any], assessment: Mapping[str, Any]) -> tuple[int | float | None, int | float | None]:
    for stage in reversed(list(canonical.get("stage_summaries") or [])):
        if not isinstance(stage, Mapping) or _text(stage.get("stage_id")) != "evidence_reconciliation_and_scoring":
            continue
        technical = stage.get("technical_score")
        adjusted = stage.get("canonical_evidence_adjusted_score", stage.get("evidence_adjusted_score"))
        if isinstance(technical, (int, float)) and not isinstance(technical, bool):
            return technical, adjusted if isinstance(adjusted, (int, float)) and not isinstance(adjusted, bool) else technical

    truth = assessment.get("comprehensive_score_truth")
    if isinstance(truth, Mapping):
        technical = truth.get("technical_score", truth.get("score"))
        adjusted = truth.get("canonical_evidence_adjusted_score", truth.get("evidence_adjusted_score"))
        if isinstance(technical, (int, float)) and not isinstance(technical, bool):
            return technical, adjusted if isinstance(adjusted, (int, float)) and not isinstance(adjusted, bool) else technical

    technical = assessment.get("technical_score")
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    return (
        technical if isinstance(technical, (int, float)) and not isinstance(technical, bool) else None,
        adjusted if isinstance(adjusted, (int, float)) and not isinstance(adjusted, bool) else None,
    )


def _strip_scanner_lines(values: Any, scanner_names: set[str]) -> list[Any]:
    output: list[Any] = []
    for value in values or []:
        text = _text(value).casefold()
        if any(name in text and any(token in text for token in ("status=", "exact-sha", "completion requirements", "did not run", "missing", "failed", "partial")) for name in scanner_names):
            continue
        output.append(value)
    return output


def _scanner_line(record: Mapping[str, Any]) -> str:
    name = _name(record.get("scanner_name") or record.get("tool"))
    status = _status(record)
    return (
        f"{name}: status={status}; exact_commit_match={record.get('exact_commit_match') is True}; "
        f"verified_complete={record.get('verified_complete') is True}; findings={len(record.get('findings') or [])}; "
        f"artifact_hash={_text(record.get('artifact_hash')) or 'unavailable'}"
    )


def _finding_key(finding: Mapping[str, Any]) -> tuple[str, str, str, str]:
    location = _text(finding.get("location") or finding.get("primary_location")).casefold()
    title = _text(finding.get("title") or finding.get("decision_title") or finding.get("interpretation")).casefold()
    category = _text(finding.get("category")).casefold()
    fact = _text(finding.get("fact") or finding.get("evidence") or finding.get("layer_1_evidence")).casefold()
    fact = re.sub(r"\s+", " ", fact)
    return category, location, title, fact


def _finding_rank(finding: Mapping[str, Any]) -> tuple[int, ...]:
    identifier = _text(finding.get("finding_id") or finding.get("id"))
    return (
        int(identifier.startswith("RISK-P")),
        int(bool(finding.get("acceptance_criteria"))),
        int(bool(_text(finding.get("cost_of_inaction")))),
        int(bool(_text(finding.get("residual_risk")))),
        len(str(finding)),
    )


def _dedupe_text(values: Any) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()
    for value in values or []:
        key = re.sub(r"\s+", " ", _text(value)).casefold()
        key = re.sub(r"\s*\[method:[^\]]+\]", "", key)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _dedupe_findings(values: Any) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for raw in values or []:
        if not isinstance(raw, Mapping):
            continue
        finding = deepcopy(dict(raw))
        finding["acceptance_criteria"] = _dedupe_text(finding.get("acceptance_criteria"))
        key = _finding_key(finding)
        prior = selected.get(key)
        if prior is None or _finding_rank(finding) > _finding_rank(prior):
            selected[key] = finding
    return list(selected.values())


def reconcile_production_report_truth(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or result))
    assessment = deepcopy(dict(canonical.get("assessment") or {}))

    scanners = _canonical_scanners(canonical, assessment)
    scanner_names = {_name(item.get("scanner_name")) for item in scanners}
    by_category: dict[str, list[dict[str, Any]]] = {}
    for record in scanners:
        by_category.setdefault(_text(record.get("category")).casefold(), []).append(record)

    sections: list[dict[str, Any]] = []
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        section = deepcopy(dict(raw))
        for field in ("evidence", "findings", "unavailable"):
            section[field] = _strip_scanner_lines(section.get(field), scanner_names)
        section_id = _text(section.get("id") or section.get("label")).casefold()
        categories: list[str] = []
        if "static" in section_id:
            categories = ["static"]
        elif "secret" in section_id:
            categories = ["secret"]
        elif "depend" in section_id or "library" in section_id:
            categories = ["dependency"]
        relevant = [record for category in categories for record in by_category.get(category, [])]
        section.setdefault("evidence", [])
        section["evidence"].extend(_scanner_line(record) for record in relevant)
        incomplete = [record for record in relevant if record.get("verified_complete") is not True]
        section["unavailable"].extend(
            f"{_name(record.get('scanner_name'))} exact-SHA evidence remains {_status(record)}: {_text(record.get('reason') or record.get('failure_or_unavailable_reason')) or 'completion requirements were not met'}"
            for record in incomplete
        )
        sections.append(section)

    technical, adjusted = _score_pair(canonical, assessment)
    if technical is not None:
        assessment["technical_score"] = technical
        assessment["score"] = technical
        assessment["presented_score"] = technical
        maturity = deepcopy(dict(assessment.get("maturity_signal") or {}))
        maturity["score"] = technical
        maturity["presented_score"] = technical
        maturity["technical_score"] = technical
        assessment["maturity_signal"] = maturity
    if adjusted is not None:
        assessment["evidence_adjusted_score"] = adjusted
        assessment["canonical_evidence_adjusted_score"] = adjusted
    if technical is not None and adjusted is not None:
        assessment["comprehensive_score_truth"] = {
            "technical_score": technical,
            "evidence_adjusted_score": adjusted,
            "canonical_evidence_adjusted_score": adjusted,
            "source": "evidence_reconciliation_and_scoring",
        }

    assessment["sections"] = sections
    assessment["scanner_execution_records"] = deepcopy(scanners)
    canonical["scanner_execution_records"] = deepcopy(scanners)

    findings = _dedupe_findings(canonical.get("canonical_findings") or canonical.get("findings_register"))
    canonical["canonical_findings"] = findings
    canonical["findings_register"] = deepcopy(findings)
    canonical["executive_risk_register"] = deepcopy(findings[:7])
    canonical["priority_findings"] = deepcopy(findings[:5])

    stages: list[dict[str, Any]] = []
    for raw in canonical.get("stage_summaries") or []:
        if not isinstance(raw, Mapping):
            continue
        stage = deepcopy(dict(raw))
        if _text(stage.get("stage_id")) == "decision_report_generation" and technical is not None and adjusted is not None:
            stage["report_contract_status"] = "passed"
            stage["report_contract_reason"] = None
        if _text(stage.get("stage_id")) == "evidence_reconciliation_and_scoring":
            stage["technical_score"] = technical
            stage["evidence_adjusted_score"] = adjusted
            stage["canonical_evidence_adjusted_score"] = adjusted
        stages.append(stage)
    canonical["stage_summaries"] = stages
    canonical["assessment"] = assessment

    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update({
        "production_report_truth_gate_version": VERSION,
        "single_scanner_record_per_tool": True,
        "single_score_truth": technical is not None and adjusted is not None,
        "duplicate_finding_identities_removed": True,
    })
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical
    result = normalize_report_artifact_filenames(result)
    return result


__all__ = ["VERSION", "reconcile_production_report_truth"]
