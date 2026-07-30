from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from nico.report_artifact_filename import normalize_report_artifact_filenames

VERSION = "nico.production-report-truth-gate.v2"
_TERMINAL_BAD = {"failed", "missing", "unavailable", "error", "timed_out", "timeout"}
_SCORE_MISMATCH_REASONS = {
    "canonical_score_truth_mismatch",
    "canonical_scores_mismatch",
    "score_truth_mismatch",
    "cross_format_score_mismatch",
    "cross_format_score_truth_mismatch",
}
_RISK_REFERENCE_FIELDS = {
    "related_risks",
    "risk_ids",
    "finding_ids",
    "related_findings",
    "related_finding_ids",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _name(value: Any) -> str:
    return _text(value).casefold().replace("_", "-")


def _status(record: Mapping[str, Any]) -> str:
    return _text(record.get("status") or record.get("state")).casefold().replace("-", "_")


def _numeric(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


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


def _canonical_scanners(
    canonical: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> list[dict[str, Any]]:
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
        current = record.get("current_run") is True
        observed = record.get("execution_observed_for_this_report") is True
        exact = record.get("exact_commit_match") is True
        verified_signal = (
            record.get("verified_for_this_report") is True
            or record.get("verified") is True
        )
        capture = record.get("raw_artifact_retention_complete") is True or (
            record.get("output_capture_complete") is True
            and not record.get("timed_out")
            and not record.get("output_truncated")
        )
        history_ok = (
            not record.get("scans_git_history")
            or record.get("full_history_verified") is True
        )
        record["raw_artifact_retention_complete"] = bool(capture)
        record["verified_complete"] = bool(
            status.startswith("completed")
            and current
            and observed
            and exact
            and verified_signal
            and capture
            and artifact
            and artifact not in {"missing", "unavailable"}
            and history_ok
        )

        deficits: list[str] = []
        if not status.startswith("completed"):
            deficits.append(f"status={status}")
        if not current:
            deficits.append("current_run_not_proven")
        if not observed:
            deficits.append("execution_not_observed_for_this_report")
        if not exact:
            deficits.append("exact_commit_match_not_proven")
        if not verified_signal:
            deficits.append("scanner_verification_not_proven")
        if not capture:
            deficits.append("complete_artifact_capture_not_proven")
        if not artifact or artifact in {"missing", "unavailable"}:
            deficits.append("artifact_hash_missing")
        if not history_ok:
            deficits.append("full_git_history_not_verified")
        record["verification_deficits"] = deficits
        output.append(record)
    return output


def _score_pair(
    canonical: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> tuple[int | float | None, int | float | None]:
    for stage in reversed(list(canonical.get("stage_summaries") or [])):
        if not isinstance(stage, Mapping) or _text(stage.get("stage_id")) != "evidence_reconciliation_and_scoring":
            continue
        technical = _numeric(stage.get("technical_score"))
        adjusted = _numeric(
            stage.get("canonical_evidence_adjusted_score", stage.get("evidence_adjusted_score"))
        )
        if technical is not None:
            return technical, adjusted if adjusted is not None else technical

    truth = assessment.get("comprehensive_score_truth")
    if isinstance(truth, Mapping):
        technical = _numeric(truth.get("technical_score", truth.get("score")))
        adjusted = _numeric(
            truth.get("canonical_evidence_adjusted_score", truth.get("evidence_adjusted_score"))
        )
        if technical is not None:
            return technical, adjusted if adjusted is not None else technical

    technical = _numeric(assessment.get("technical_score"))
    adjusted = _numeric(
        assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    )
    return technical, adjusted


def _strip_scanner_lines(values: Any, scanner_names: set[str]) -> list[Any]:
    output: list[Any] = []
    for value in values or []:
        text = _text(value).casefold()
        if any(
            name in text
            and any(
                token in text
                for token in (
                    "status=",
                    "exact-sha",
                    "completion requirements",
                    "did not run",
                    "missing",
                    "failed",
                    "partial",
                )
            )
            for name in scanner_names
        ):
            continue
        output.append(value)
    return output


def _scanner_line(record: Mapping[str, Any]) -> str:
    name = _name(record.get("scanner_name") or record.get("tool"))
    status = _status(record)
    return (
        f"{name}: status={status}; current_run={record.get('current_run') is True}; "
        f"exact_commit_match={record.get('exact_commit_match') is True}; "
        f"verified_complete={record.get('verified_complete') is True}; "
        f"findings={len(record.get('findings') or [])}; "
        f"artifact_hash={_text(record.get('artifact_hash')) or 'unavailable'}"
    )


def _finding_evidence_identity(finding: Mapping[str, Any]) -> str:
    explicit_parts: list[str] = []
    for key in (
        "evidence_identity",
        "advisory_id",
        "vulnerability_id",
        "cve",
        "ghsa",
        "package",
        "installed_version",
        "test_id",
        "rule_id",
        "code",
        "symbol",
        "function",
    ):
        value = _text(finding.get(key))
        if value:
            explicit_parts.append(f"{key}={value.casefold()}")
    if explicit_parts:
        return "|".join(explicit_parts)
    fact = _text(
        finding.get("fact")
        or finding.get("evidence")
        or finding.get("layer_1_evidence")
    ).casefold()
    return re.sub(r"\s+", " ", fact)


def _finding_key(finding: Mapping[str, Any]) -> tuple[str, str, str, str]:
    location = _text(finding.get("location") or finding.get("primary_location")).casefold()
    title = _text(
        finding.get("title")
        or finding.get("decision_title")
        or finding.get("interpretation")
    ).casefold()
    category = _text(finding.get("category")).casefold()
    return category, location, title, _finding_evidence_identity(finding)


def _finding_rank(finding: Mapping[str, Any]) -> tuple[int, ...]:
    identifier = _text(finding.get("finding_id") or finding.get("id"))
    return (
        int(identifier.startswith("RISK-P")),
        int(bool(finding.get("acceptance_criteria"))),
        int(bool(_text(finding.get("cost_of_inaction")))),
        int(bool(_text(finding.get("residual_risk")))),
        len(str(finding)),
    )


def _split_criterion_clauses(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    output: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(text):
        if character == "[":
            depth += 1
        elif character == "]" and depth:
            depth -= 1
        elif character == ";" and depth == 0:
            clause = text[start:index].strip(" ;")
            if clause:
                output.append(clause)
            start = index + 1
    final = text[start:].strip(" ;")
    if final:
        output.append(final)
    return output


def _criterion_display_and_key(value: str) -> tuple[str, str]:
    annotations = re.findall(r"\[method:[^\]]+\]", value, flags=re.IGNORECASE)
    base = re.sub(r"\s*\[method:[^\]]+\]", "", value, flags=re.IGNORECASE).strip(" ;")
    key = re.sub(r"\s+", " ", base).casefold()
    display = base
    if annotations:
        display = f"{base} {annotations[0]}".strip()
    return display, key


def _dedupe_text(values: Any) -> list[str]:
    selected: dict[str, str] = {}
    order: list[str] = []
    for value in values or []:
        for clause in _split_criterion_clauses(value):
            display, key = _criterion_display_and_key(clause)
            if not key:
                continue
            if key not in selected:
                order.append(key)
                selected[key] = display
            elif "[method:" not in selected[key].casefold() and "[method:" in display.casefold():
                selected[key] = display
    return [selected[key] for key in order]


def _dedupe_findings(
    values: Any,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    normalized: list[tuple[tuple[str, str, str, str], dict[str, Any]]] = []
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for raw in values or []:
        if not isinstance(raw, Mapping):
            continue
        finding = deepcopy(dict(raw))
        finding["acceptance_criteria"] = _dedupe_text(finding.get("acceptance_criteria"))
        key = _finding_key(finding)
        normalized.append((key, finding))
        prior = selected.get(key)
        if prior is None or _finding_rank(finding) > _finding_rank(prior):
            selected[key] = finding

    aliases: dict[str, str] = {}
    for key, finding in normalized:
        old_id = _text(finding.get("finding_id") or finding.get("id"))
        retained = selected[key]
        retained_id = _text(retained.get("finding_id") or retained.get("id"))
        if old_id and retained_id:
            aliases[old_id] = retained_id
    return list(selected.values()), aliases


def _normalize_risk_id_values(value: Any, aliases: Mapping[str, str]) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, str):
        matches = re.findall(r"RISK-[A-Za-z0-9_-]+", value)
        raw_items.extend(matches or [value])
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            raw_items.extend(_normalize_risk_id_values(item, aliases))
    elif value is not None:
        raw_items.append(_text(value))

    output: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        item = _text(raw)
        mapped = _text(aliases.get(item, item))
        key = mapped.casefold()
        if mapped and key not in seen:
            seen.add(key)
            output.append(mapped)
    return output


def _normalize_risk_references(value: Any, aliases: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key.casefold() in _RISK_REFERENCE_FIELDS:
                output[key] = _normalize_risk_id_values(raw_value, aliases)
            else:
                output[key] = _normalize_risk_references(raw_value, aliases)
        return output
    if isinstance(value, list):
        return [_normalize_risk_references(item, aliases) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_risk_references(item, aliases) for item in value)
    return deepcopy(value)


def _contract_reason(record: Mapping[str, Any]) -> str:
    return _text(record.get("reason") or record.get("report_contract_reason")).casefold()


def _contract_status(record: Mapping[str, Any]) -> str:
    return _text(record.get("status") or record.get("report_contract_status")).casefold()


def _repair_score_contract(
    record: Mapping[str, Any],
    technical: int | float | None,
    adjusted: int | float | None,
) -> tuple[dict[str, Any], bool]:
    repaired = deepcopy(dict(record))
    reason = _contract_reason(repaired)
    if technical is None or adjusted is None or reason not in _SCORE_MISMATCH_REASONS:
        return repaired, False
    if "report_contract_status" in repaired:
        repaired["report_contract_status"] = "passed"
        repaired["report_contract_reason"] = None
    else:
        repaired["status"] = "passed"
        repaired["reason"] = None
    repaired["score_truth_reconciled"] = True
    repaired["technical_score"] = technical
    repaired["evidence_adjusted_score"] = adjusted
    return repaired, True


def _blocking_contract_reasons(
    canonical: Mapping[str, Any],
    assessment: Mapping[str, Any],
    package: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    records: list[Mapping[str, Any]] = []
    for candidate in (
        package.get("report_contract"),
        canonical.get("report_contract"),
        assessment.get("report_contract"),
    ):
        if isinstance(candidate, Mapping):
            records.append(candidate)
    records.extend(
        item
        for item in canonical.get("stage_summaries") or []
        if isinstance(item, Mapping) and _text(item.get("stage_id")) == "decision_report_generation"
    )
    for record in records:
        status = _contract_status(record)
        if status in {"blocked", "failed", "error", "rejected"}:
            reasons.append(_contract_reason(record) or status)
    return list(dict.fromkeys(reasons))


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
            f"{_name(record.get('scanner_name'))} exact-SHA evidence remains {_status(record)}: "
            f"{'; '.join(record.get('verification_deficits') or []) or _text(record.get('reason') or record.get('failure_or_unavailable_reason')) or 'completion requirements were not met'}"
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
        result["technical_score"] = technical
    if adjusted is not None:
        assessment["evidence_adjusted_score"] = adjusted
        assessment["canonical_evidence_adjusted_score"] = adjusted
        result["evidence_adjusted_score"] = adjusted
        result["canonical_evidence_adjusted_score"] = adjusted
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

    findings, aliases = _dedupe_findings(
        canonical.get("canonical_findings") or canonical.get("findings_register")
    )
    canonical["canonical_findings"] = findings
    canonical["findings_register"] = deepcopy(findings)
    canonical["executive_risk_register"] = deepcopy(findings[:7])
    canonical["priority_findings"] = deepcopy(findings[:5])
    canonical["assessment"] = assessment
    canonical = _normalize_risk_references(canonical, aliases)
    assessment = deepcopy(dict(canonical.get("assessment") or assessment))

    score_contract_repairs = 0
    stages: list[dict[str, Any]] = []
    for raw in canonical.get("stage_summaries") or []:
        if not isinstance(raw, Mapping):
            continue
        stage = deepcopy(dict(raw))
        stage_id = _text(stage.get("stage_id"))
        if stage_id == "decision_report_generation":
            stage, repaired = _repair_score_contract(stage, technical, adjusted)
            score_contract_repairs += int(repaired)
        if stage_id == "evidence_reconciliation_and_scoring":
            if technical is not None:
                stage["technical_score"] = technical
            if adjusted is not None:
                stage["evidence_adjusted_score"] = adjusted
                stage["canonical_evidence_adjusted_score"] = adjusted
            stage["finding_register_count"] = len(findings)
        stages.append(stage)
    canonical["stage_summaries"] = stages

    for owner, key in ((canonical, "report_contract"), (assessment, "report_contract"), (result, "report_contract")):
        candidate = owner.get(key)
        if isinstance(candidate, Mapping):
            repaired, did_repair = _repair_score_contract(candidate, technical, adjusted)
            owner[key] = repaired
            score_contract_repairs += int(did_repair)

    canonical["assessment"] = assessment
    blocking_reasons = _blocking_contract_reasons(canonical, assessment, result)
    explicit_required = [record for record in scanners if record.get("required") is True]
    all_scanners_verified = bool(scanners) and all(
        record.get("verified_complete") is True for record in scanners
    )
    required_scanners_verified = bool(explicit_required) and all(
        record.get("verified_complete") is True for record in explicit_required
    )
    client_delivery_allowed = bool(
        canonical.get("client_delivery_allowed")
        or assessment.get("client_delivery_allowed")
        or result.get("client_delivery_allowed")
    )
    human_review_required = not client_delivery_allowed
    readiness_contract = {
        "version": VERSION,
        "automated_report_truth_ready": bool(
            technical is not None
            and adjusted is not None
            and not blocking_reasons
            and len(scanner_names) == len(scanners)
        ),
        "single_score_truth": technical is not None and adjusted is not None,
        "single_scanner_record_per_tool": len(scanner_names) == len(scanners),
        "all_observed_scanners_verified": all_scanners_verified,
        "explicit_required_scanner_count": len(explicit_required),
        "explicit_required_scanners_verified": required_scanners_verified,
        "duplicate_finding_identities_removed": True,
        "roadmap_risk_references_normalized": True,
        "report_contract_status": "blocked" if blocking_reasons else "passed",
        "report_contract_blocking_reasons": blocking_reasons,
        "score_contract_repairs_applied": score_contract_repairs,
        "internal_human_approval_required": human_review_required,
        "client_delivery_allowed": client_delivery_allowed,
    }
    canonical["client_readiness_contract"] = deepcopy(readiness_contract)
    assessment["client_readiness_contract"] = deepcopy(readiness_contract)
    canonical["assessment"] = assessment

    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "production_report_truth_gate_version": VERSION,
            "single_scanner_record_per_tool": len(scanner_names) == len(scanners),
            "single_score_truth": technical is not None and adjusted is not None,
            "duplicate_finding_identities_removed": True,
            "roadmap_risk_references_normalized": True,
            "score_contract_repairs_applied": score_contract_repairs,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical
    result["client_readiness_contract"] = deepcopy(readiness_contract)
    return normalize_report_artifact_filenames(result)


__all__ = ["VERSION", "reconcile_production_report_truth"]
