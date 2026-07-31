from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.canonical_section_status_v1 import normalize_scored_sections

VERSION = "nico.client-assessment-truth.v3"

_PATH_KEYS = {
    "path",
    "file",
    "file_path",
    "filename",
    "filepath",
    "source_path",
    "dependency_path",
    "manifest",
    "lockfile",
    "location",
    "source_location",
}
_SKIP_RECURSIVE_KEYS = {
    "pdf_base64",
    "markdown",
    "html",
    "raw_output",
    "stdout",
    "stderr",
    "secret",
    "match",
}
_REPOSITORY_ROOTS = (
    "apps/",
    "nico/",
    "scripts/",
    "src/",
    "lib/",
    "packages/",
    "services/",
    "config/",
    "docs/",
    ".github/",
)
_CONFIGURATION_ERROR_PATTERNS = (
    re.compile(r"definition for rule ['\"][^'\"]+['\"] was not found", re.IGNORECASE),
    re.compile(r"failed to load (?:plugin|config|configuration)", re.IGNORECASE),
    re.compile(r"cannot find module .*(?:eslint|typescript|plugin)", re.IGNORECASE),
    re.compile(r"eslint configuration .* not found", re.IGNORECASE),
    re.compile(r"configuration for rule .* is invalid", re.IGNORECASE),
    re.compile(r"unknown rule ['\"][^'\"]+['\"]", re.IGNORECASE),
)
_TLS_EXECUTABLE_PATTERNS = (
    re.compile(r"\b(?:requests|httpx)\s*\.\s*(?:get|post|put|patch|delete|request)\s*\([^\n]{0,400}\bverify\s*=\s*False\b", re.IGNORECASE),
    re.compile(r"\bverify\s*=\s*False\b", re.IGNORECASE),
    re.compile(r"\brejectUnauthorized\s*:\s*false\b", re.IGNORECASE),
    re.compile(r"\bCERT_NONE\b"),
    re.compile(r"\bcheck_hostname\s*=\s*False\b", re.IGNORECASE),
    re.compile(r"_create_unverified_context\s*\(", re.IGNORECASE),
)
_TLS_DEFINITION_PATH_PARTS = (
    "finding",
    "scanner",
    "detector",
    "pattern",
    "rule",
    "report_truth",
    "remediation",
)


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _scanner_name(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "tsc": "typescript",
        "truffle-hog": "trufflehog",
    }.get(normalized, normalized)


def normalize_repository_path(value: Any) -> str:
    """Return a repository-relative path without worker or checkout prefixes."""

    raw = _text(value, 4000).replace("\\", "/")
    if not raw or raw in {"location-not-retained", "not retained", "unknown"}:
        return raw
    if "://" in raw and not raw.startswith("file://"):
        return raw
    raw = re.sub(r"^file://", "", raw)
    raw = re.sub(r"/{2,}", "/", raw)

    location_suffix = ""
    match = re.match(r"^(.*?)(:\d+(?::\d+)?)$", raw)
    if match:
        raw, location_suffix = match.group(1), match.group(2)

    raw = re.sub(r"^.*?/nico-snapshot-scan-[^/]+/repo/", "", raw)
    raw = re.sub(r"^/tmp/[^/]+/repo/", "", raw)
    raw = re.sub(r"^/home/runner/work/[^/]+/[^/]+/", "", raw)
    raw = re.sub(r"^/github/workspace/", "", raw)
    raw = re.sub(r"^/workspace/", "", raw)
    raw = raw.removeprefix("./")

    if raw.startswith("/"):
        positions = [raw.find(f"/{root}") for root in _REPOSITORY_ROOTS]
        positions = [position for position in positions if position >= 0]
        if positions:
            raw = raw[min(positions) + 1 :]

    return raw.lstrip("/") + location_suffix


def _normalize_location_text(value: Any) -> str:
    text = _text(value, 4000)
    return normalize_repository_path(text)


def _normalize_paths(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if depth > 9:
        return deepcopy(value)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for child_key, child in value.items():
            normalized_key = str(child_key).casefold()
            if normalized_key in _SKIP_RECURSIVE_KEYS:
                output[str(child_key)] = deepcopy(child)
            elif normalized_key in _PATH_KEYS and isinstance(child, str):
                output[str(child_key)] = _normalize_location_text(child)
            else:
                output[str(child_key)] = _normalize_paths(
                    child,
                    key=str(child_key),
                    depth=depth + 1,
                )
        return output
    if isinstance(value, list):
        return [_normalize_paths(item, key=key, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_paths(item, key=key, depth=depth + 1) for item in value)
    if isinstance(value, str) and any(marker in key.casefold() for marker in ("path", "file", "location")):
        return _normalize_location_text(value)
    return deepcopy(value)


def scanner_configuration_error(value: Any) -> bool:
    if isinstance(value, Mapping):
        message = _text(
            value.get("message")
            or value.get("description")
            or value.get("title")
            or value.get("observed_evidence")
            or value.get("failure_reason")
            or value.get("error")
        )
    else:
        message = _text(value)
    return any(pattern.search(message) for pattern in _CONFIGURATION_ERROR_PATTERNS)


def _normalize_scanner_finding(value: Mapping[str, Any]) -> dict[str, Any]:
    finding = _normalize_paths(value)
    if scanner_configuration_error(finding):
        finding["finding_classification"] = "scanner_configuration_error"
        finding["client_actionable"] = False
        finding["material"] = False
    return finding


def _normalize_scanner_record(value: Mapping[str, Any]) -> dict[str, Any]:
    record = _normalize_paths(value)
    scanner = _scanner_name(record.get("scanner_name") or record.get("tool") or record.get("scanner"))
    record["scanner_name"] = scanner
    findings = [
        _normalize_scanner_finding(item)
        for item in record.get("findings") or []
        if isinstance(item, Mapping)
    ]
    configuration = [item for item in findings if item.get("finding_classification") == "scanner_configuration_error"]
    actionable = [item for item in findings if item.get("finding_classification") != "scanner_configuration_error"]
    record["findings"] = actionable
    record["raw_finding_count"] = len(findings)
    record["client_actionable_finding_count"] = len(actionable)

    if configuration:
        record["scanner_configuration_findings"] = configuration
        record["scanner_configuration_error_count"] = len(configuration)
        record["raw_state"] = record.get("raw_state") or record.get("state") or record.get("status")
        record["state"] = "partial" if actionable else "configuration_failed"
        record["status"] = record["state"]
        record["completed"] = False
        record["verified"] = False
        record["verified_complete"] = False
        record["verified_for_this_report"] = False
        record["failure_reason"] = (
            f"{scanner} produced {len(configuration)} configuration error(s); "
            "the analyzer result is not valid source-code evidence."
        )
        record["assurance_status"] = "review_limited"
        record["client_finding_created_from_configuration_error"] = False
    return record


def _record_list(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    for candidate in (
        canonical.get("requested_scanner_records"),
        assessment.get("requested_scanner_records"),
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
    ):
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, Mapping)]
    return []


def _sync_scanner_truth(canonical: dict[str, Any]) -> None:
    records = [_normalize_scanner_record(item) for item in _record_list(canonical)]
    applicable = [item for item in records if item.get("applicable") is not False]
    not_applicable = [item for item in records if item.get("applicable") is False]
    completed = [item for item in applicable if item.get("completed") is True]
    incomplete = [item for item in applicable if item.get("completed") is not True]
    configuration_issues = [
        {
            "scanner_name": item.get("scanner_name"),
            "state": item.get("state"),
            "reason": item.get("failure_reason"),
            "count": int(item.get("scanner_configuration_error_count") or 0),
        }
        for item in applicable
        if int(item.get("scanner_configuration_error_count") or 0) > 0
    ]

    canonical["requested_scanner_records"] = deepcopy(records)
    canonical["scanner_execution_records"] = deepcopy(applicable)
    canonical["not_applicable_scanner_records"] = deepcopy(not_applicable)
    canonical["scanner_configuration_issues"] = configuration_issues

    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    assessment["requested_scanner_records"] = deepcopy(records)
    assessment["scanner_execution_records"] = deepcopy(applicable)
    assessment["completed_scanner_records"] = deepcopy(completed)
    assessment["incomplete_scanner_records"] = deepcopy(incomplete)
    assessment["not_applicable_scanner_records"] = deepcopy(not_applicable)
    summary = deepcopy(dict(assessment.get("scanner_applicability_summary") or {}))
    summary.update(
        {
            "requested_scanners": len(records),
            "applicable_scanners": len(applicable),
            "completed_applicable_scanners": len(completed),
            "incomplete_applicable_scanners": len(incomplete),
            "not_applicable_scanners": len(not_applicable),
            "scanner_configuration_issue_count": sum(item["count"] for item in configuration_issues),
            "configuration_errors_are_not_code_findings": True,
        }
    )
    assessment["scanner_applicability_summary"] = summary
    canonical["assessment"] = assessment


def _iter_mappings(value: Any, *, depth: int = 0) -> Iterable[dict[str, Any]]:
    if depth > 10:
        return
    if isinstance(value, dict):
        yield value
        for key, item in value.items():
            if str(key).casefold() in _SKIP_RECURSIVE_KEYS:
                continue
            yield from _iter_mappings(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_mappings(item, depth=depth + 1)


def _contains_score_sync(canonical: Mapping[str, Any]) -> bool:
    for item in _iter_mappings(deepcopy(dict(canonical))):
        if item.get("final_report_input_scores_synchronized") is True:
            return True
    return False


def _repair_stale_report_contracts(canonical: dict[str, Any]) -> int:
    if not _contains_score_sync(canonical):
        return 0
    repaired = 0
    for item in _iter_mappings(canonical):
        status = _text(item.get("report_contract_status")).casefold()
        reason = _text(item.get("report_contract_reason")).casefold()
        if status != "blocked" or "score" not in reason or "mismatch" not in reason:
            continue
        item["pre_reconciliation_report_contract"] = {
            "status": item.get("report_contract_status"),
            "reason": item.get("report_contract_reason"),
        }
        item["report_contract_status"] = "reconciled"
        item["report_contract_reason"] = "canonical_score_truth_reconciled_before_final_render"
        item["report_contract_reconciled"] = True
        repaired += 1
    return repaired


def _normalize_sections(canonical: dict[str, Any]) -> None:
    assessment = normalize_scored_sections(
        canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    )
    sections: list[dict[str, Any]] = []
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        section = deepcopy(dict(raw))
        score = section.get("presented_score", section.get("score"))
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            section.setdefault("execution_status", "evidence_evaluated")
            section.setdefault("assurance_status", "evidence_bound")
            section["execution_and_assurance_separated"] = True
        sections.append(section)
    assessment["sections"] = sections
    canonical["assessment"] = assessment


def executable_tls_evidence(item: Mapping[str, Any]) -> bool:
    path = normalize_repository_path(
        item.get("path")
        or item.get("file_path")
        or item.get("location")
        or item.get("source_path")
    ).casefold()
    if path.startswith("tests/") or "/tests/" in f"/{path}":
        return False
    if any(part in path for part in _TLS_DEFINITION_PATH_PARTS):
        return False
    evidence = "\n".join(
        _text(item.get(key), 4000)
        for key in (
            "source_excerpt",
            "code_excerpt",
            "snippet",
            "source_line",
            "line_text",
            "observed_evidence",
            "message",
        )
        if item.get(key)
    )
    return any(pattern.search(evidence) for pattern in _TLS_EXECUTABLE_PATTERNS)


def normalize_client_assessment_truth(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize client-visible scanner, path, score, and report-contract truth."""

    canonical = _normalize_paths(value)
    _sync_scanner_truth(canonical)
    _normalize_sections(canonical)
    repaired_contracts = _repair_stale_report_contracts(canonical)

    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "client_assessment_truth_version": VERSION,
            "repository_relative_paths_only": True,
            "scanner_configuration_errors_are_not_code_findings": True,
            "execution_status_separate_from_assurance": True,
            "stale_score_mismatch_contracts_reconciled": repaired_contracts,
            "tls_pattern_requires_executable_source_evidence": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    return canonical


__all__ = [
    "VERSION",
    "executable_tls_evidence",
    "normalize_client_assessment_truth",
    "normalize_repository_path",
    "scanner_configuration_error",
]
