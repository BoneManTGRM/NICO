from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from typing import Any, Mapping

from fastapi import FastAPI

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v4 as v4
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

VERSION = "nico.comprehensive-native-providers.v5"

_DISPOSITIONS = (
    "verified_material",
    "review_required",
    "approved_or_nonblocking",
    "excluded_test_only",
)
_TEST_PARTS = {"test", "tests", "fixture", "fixtures", "example", "examples", "sample", "samples"}


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _tool_results(scan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    values = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    output: dict[str, dict[str, Any]] = {}
    for raw in values:
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("scanner_name") or raw.get("tool") or raw.get("scanner"), 120).casefold()
        if name:
            output[name] = raw
    return output


def _summary_by_tool(scan: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    summary = scan.get("finding_summary") if isinstance(scan.get("finding_summary"), dict) else {}
    by_tool = summary.get("by_tool") if isinstance(summary.get("by_tool"), dict) else {}
    return {
        _text(tool, 120).casefold(): {
            key: _int(raw.get(key))
            for key in ("raw", "material", "review_required", "approved_or_nonblocking", "excluded_test_only")
        }
        for tool, raw in by_tool.items()
        if isinstance(raw, dict)
    }


def _path(finding: Mapping[str, Any]) -> str:
    source = finding.get("source") if isinstance(finding.get("source"), Mapping) else {}
    value = (
        finding.get("dependency_path")
        or finding.get("source_path")
        or finding.get("file_path")
        or finding.get("filename")
        or finding.get("path")
        or finding.get("filePath")
        or source.get("path")
        or ""
    )
    return str(value).replace("\\", "/").strip()


def _line(finding: Mapping[str, Any]) -> int | None:
    source = finding.get("source") if isinstance(finding.get("source"), Mapping) else {}
    start = finding.get("start") if isinstance(finding.get("start"), Mapping) else {}
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    extra_start = extra.get("start") if isinstance(extra.get("start"), Mapping) else {}
    for value in (
        finding.get("line"),
        finding.get("line_number"),
        finding.get("start_line"),
        source.get("line"),
        start.get("line"),
        extra_start.get("line"),
    ):
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def _column(finding: Mapping[str, Any]) -> int | None:
    source = finding.get("source") if isinstance(finding.get("source"), Mapping) else {}
    start = finding.get("start") if isinstance(finding.get("start"), Mapping) else {}
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    extra_start = extra.get("start") if isinstance(extra.get("start"), Mapping) else {}
    for value in (
        finding.get("column"),
        finding.get("start_column"),
        source.get("column"),
        start.get("col"),
        start.get("column"),
        extra_start.get("col"),
        extra_start.get("column"),
    ):
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def _rule(finding: Mapping[str, Any]) -> str:
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    vulnerability = finding.get("vulnerability") if isinstance(finding.get("vulnerability"), Mapping) else {}
    return _text(
        finding.get("rule_id")
        or finding.get("check_id")
        or finding.get("test_id")
        or finding.get("code")
        or finding.get("advisory_id")
        or finding.get("id")
        or vulnerability.get("id")
        or extra.get("rule_id")
        or extra.get("message"),
        300,
    )


def _message(finding: Mapping[str, Any]) -> str:
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    vulnerability = finding.get("vulnerability") if isinstance(finding.get("vulnerability"), Mapping) else {}
    return _text(
        finding.get("message")
        or finding.get("description")
        or finding.get("summary")
        or finding.get("title")
        or finding.get("Match")
        or finding.get("match")
        or extra.get("message")
        or vulnerability.get("summary")
        or vulnerability.get("details")
        or _rule(finding)
        or "Scanner candidate retained without a human-readable message.",
        2000,
    )


def _severity(finding: Mapping[str, Any]) -> str:
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    metadata = extra.get("metadata") if isinstance(extra.get("metadata"), Mapping) else {}
    text = " ".join(
        _text(value, 200).casefold()
        for value in (
            finding.get("severity"),
            finding.get("issue_severity"),
            finding.get("level"),
            finding.get("risk_severity"),
            extra.get("severity"),
            metadata.get("severity"),
        )
    )
    if "critical" in text:
        return "critical"
    if "high" in text or "error" in text:
        return "high"
    if "medium" in text or "moderate" in text or "warning" in text:
        return "medium"
    if "low" in text or "info" in text:
        return "low"
    return "unknown"


def _confidence(finding: Mapping[str, Any]) -> str:
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    text = _text(
        finding.get("confidence")
        or finding.get("issue_confidence")
        or extra.get("confidence"),
        120,
    ).casefold()
    if "high" in text:
        return "high"
    if "medium" in text or "moderate" in text:
        return "medium"
    if "low" in text:
        return "low"
    return "unknown"


def _test_or_example(path: str) -> bool:
    parts = [part.casefold() for part in re.split(r"[\\/]+", path) if part]
    filename = parts[-1] if parts else ""
    return bool(
        any(part in _TEST_PARTS for part in parts)
        or filename.startswith("test_")
        or filename.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _disposition(category: str, finding: Mapping[str, Any], path: str, severity: str) -> str:
    explicit = _text(finding.get("disposition"), 120).casefold()
    aliases = {
        "material": "verified_material",
        "confirmed": "verified_material",
        "verified": "verified_material",
        "verified_material": "verified_material",
        "review": "review_required",
        "needs_review": "review_required",
        "review_required": "review_required",
        "verified_non_material": "approved_or_nonblocking",
        "approved": "approved_or_nonblocking",
        "nonblocking": "approved_or_nonblocking",
        "approved_or_nonblocking": "approved_or_nonblocking",
        "excluded": "excluded_test_only",
        "test_only": "excluded_test_only",
        "excluded_test_only": "excluded_test_only",
    }
    if explicit in aliases:
        return aliases[explicit]
    scope = _text(finding.get("scope"), 120).casefold()
    if _test_or_example(path) or scope in {"test", "tests", "testing", "development", "dev", "non_production"}:
        return "excluded_test_only"
    if category == "secret":
        return "verified_material" if bool(finding.get("Verified") or finding.get("verified")) else "review_required"
    if category == "static" and severity in {"critical", "high"}:
        return "verified_material"
    return "review_required"


def _fingerprint(
    *,
    commit_sha: str,
    scanner: str,
    category: str,
    rule_id: str,
    path: str,
    line: int | None,
    message: str,
    disposition: str,
) -> str:
    canonical = {
        "commit_sha": commit_sha.casefold(),
        "scanner": scanner.casefold(),
        "category": category.casefold(),
        "rule_id": rule_id.casefold(),
        "path": path.casefold(),
        "line": line or 0,
        "message": message.casefold(),
        "disposition": disposition,
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _normalized_record(
    *,
    commit_sha: str,
    scanner: str,
    category: str,
    finding: Mapping[str, Any],
) -> dict[str, Any]:
    path = _path(finding)
    line = _line(finding)
    column = _column(finding)
    rule_id = _rule(finding)
    message = _message(finding)
    severity = _severity(finding)
    confidence = _confidence(finding)
    disposition = _disposition(category, finding, path, severity)
    fingerprint = _fingerprint(
        commit_sha=commit_sha,
        scanner=scanner,
        category=category,
        rule_id=rule_id,
        path=path,
        line=line,
        message=message,
        disposition=disposition,
    )
    evidence_quality = "exact_source" if path and line else "source_path" if path else "payload_without_source"
    return {
        "finding_id": f"NICO-SCAN-{fingerprint[:16].upper()}",
        "raw_fingerprint": fingerprint,
        "scanner": scanner,
        "category": category,
        "rule_id": rule_id or "unclassified",
        "severity": severity,
        "confidence": confidence,
        "source_path": path,
        "line": line,
        "column": column,
        "evidence": message,
        "disposition": disposition,
        "evidence_quality": evidence_quality,
        "occurrence_count": 1,
        "exact_commit_sha": commit_sha,
        "human_review_required": disposition == "review_required",
    }


def _aggregate_record(
    *,
    commit_sha: str,
    scanner: str,
    category: str,
    disposition: str,
    occurrence_count: int,
) -> dict[str, Any]:
    message = (
        f"{occurrence_count} {disposition.replace('_', ' ')} scanner candidate(s) were retained by count, "
        "but their raw payloads were unavailable to the canonical finding register."
    )
    fingerprint = _fingerprint(
        commit_sha=commit_sha,
        scanner=scanner,
        category=category,
        rule_id="count-only",
        path="",
        line=None,
        message=message,
        disposition=disposition,
    )
    return {
        "finding_id": f"NICO-SCAN-{fingerprint[:16].upper()}",
        "raw_fingerprint": fingerprint,
        "scanner": scanner,
        "category": category,
        "rule_id": "count-only",
        "severity": "unknown",
        "confidence": "unknown",
        "source_path": "",
        "line": None,
        "column": None,
        "evidence": message,
        "disposition": disposition,
        "evidence_quality": "count_only",
        "occurrence_count": occurrence_count,
        "exact_commit_sha": commit_sha,
        "human_review_required": disposition == "review_required",
    }


def build_canonical_scanner_finding_register(
    scan: Mapping[str, Any],
    commit_sha: str,
) -> dict[str, Any]:
    by_tool = _summary_by_tool(scan)
    results = _tool_results(scan)
    records: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []

    for scanner in sorted(set(by_tool) | set(results)):
        result = results.get(scanner, {})
        category = _text(result.get("category"), 80).casefold() or (
            "dependency" if scanner in v4._DEPENDENCY_TOOLS
            else "secret" if scanner in v4._SECRET_TOOLS
            else "static" if scanner in v4._STATIC_TOOLS
            else "unknown"
        )
        detailed = [
            _normalized_record(
                commit_sha=commit_sha,
                scanner=scanner,
                category=category,
                finding=finding,
            )
            for finding in (result.get("findings") or [])
            if isinstance(finding, Mapping)
        ]
        records.extend(detailed)

        expected = by_tool.get(scanner, {})
        observed = {key: 0 for key in _DISPOSITIONS}
        mapping = {
            "verified_material": "material",
            "review_required": "review_required",
            "approved_or_nonblocking": "approved_or_nonblocking",
            "excluded_test_only": "excluded_test_only",
        }
        for record in detailed:
            observed[record["disposition"]] += _int(record.get("occurrence_count"))

        for disposition, summary_key in mapping.items():
            missing = max(0, _int(expected.get(summary_key)) - observed[disposition])
            if missing:
                records.append(
                    _aggregate_record(
                        commit_sha=commit_sha,
                        scanner=scanner,
                        category=category,
                        disposition=disposition,
                        occurrence_count=missing,
                    )
                )
        expected_raw = _int(expected.get("raw"))
        accounted_raw = sum(
            _int(record.get("occurrence_count"))
            for record in records
            if record.get("scanner") == scanner
        )
        if expected_raw and accounted_raw != expected_raw:
            discrepancies.append(
                {
                    "scanner": scanner,
                    "expected_raw": expected_raw,
                    "accounted_raw": accounted_raw,
                }
            )

    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        fingerprint = str(record["raw_fingerprint"])
        if fingerprint not in deduped:
            deduped[fingerprint] = deepcopy(record)
            deduped[fingerprint]["source_record_count"] = 1
        else:
            deduped[fingerprint]["occurrence_count"] += _int(record.get("occurrence_count"))
            deduped[fingerprint]["source_record_count"] += 1

    canonical = sorted(
        deduped.values(),
        key=lambda item: (
            str(item.get("category")),
            str(item.get("scanner")),
            str(item.get("source_path")),
            _int(item.get("line")),
            str(item.get("rule_id")),
            str(item.get("finding_id")),
        ),
    )
    totals = {
        "raw": 0,
        "material": 0,
        "review_required": 0,
        "approved_or_nonblocking": 0,
        "excluded_test_only": 0,
        "exact_source": 0,
        "source_path": 0,
        "payload_without_source": 0,
        "count_only": 0,
    }
    # Applicable scanner categories are canonical even when they contain zero
    # candidates.  Omitting a zero category makes downstream publication unable
    # to distinguish an empty result from missing/corrupt scanner truth.
    summary: dict[str, dict[str, int]] = {
        category: dict.fromkeys(totals, 0)
        for category in ("dependency", "secret", "static")
    }
    disposition_to_key = {
        "verified_material": "material",
        "review_required": "review_required",
        "approved_or_nonblocking": "approved_or_nonblocking",
        "excluded_test_only": "excluded_test_only",
    }
    for record in canonical:
        count = _int(record.get("occurrence_count"))
        category = str(record.get("category") or "unknown")
        category_summary = summary.setdefault(category, dict.fromkeys(totals, 0))
        disposition_key = disposition_to_key[str(record.get("disposition"))]
        category_summary["raw"] += count
        category_summary[disposition_key] += count
        totals["raw"] += count
        totals[disposition_key] += count
        quality = str(record.get("evidence_quality") or "payload_without_source")
        if quality in totals:
            category_summary[quality] += count
            totals[quality] += count

    expected_total = sum(_int(item.get("raw")) for item in by_tool.values())
    if expected_total != totals["raw"]:
        discrepancies.append({"scanner": "*", "expected_raw": expected_total, "accounted_raw": totals["raw"]})
    integrity_status = "complete" if not discrepancies else "blocked"
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "status": integrity_status,
        "exact_commit_sha": commit_sha,
        "findings": canonical,
        "summary_by_category": summary,
        "totals": totals,
        "count_parity_verified": not discrepancies,
        "discrepancies": discrepancies,
        "canonical_digest_sha256": digest,
        "raw_payload_retention_complete": totals["count_only"] == 0,
    }


def _candidate_volume_penalty(register: Mapping[str, Any]) -> tuple[int, dict[str, int]]:
    summary = register.get("summary_by_category") if isinstance(register.get("summary_by_category"), Mapping) else {}
    by_category: dict[str, int] = {}
    for category, raw in summary.items():
        if not isinstance(raw, Mapping):
            continue
        review = _int(raw.get("review_required"))
        by_category[str(category)] = 0 if review == 0 else min(7, math.ceil(math.log10(review + 1) * 2.5))
    return min(18, sum(by_category.values())), by_category


def _ci_operational_health(repo: Mapping[str, Any]) -> dict[str, Any]:
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), Mapping) else {}
    successful = _int(workflow.get("successful_runs"))
    non_success = _int(workflow.get("non_success_runs"))
    total = successful + non_success
    success_rate = round(successful * 100 / total) if total else None
    if success_rate is None:
        status = "unavailable"
    elif success_rate >= 95:
        status = "strong"
    elif success_rate >= 80:
        status = "moderate"
    else:
        status = "weak"
    return {
        "status": status,
        "score": success_rate,
        "successful_runs": successful,
        "non_success_runs": non_success,
        "observed_run_count": total,
        "score_effect": "operational_context_only",
        "technical_configuration_score_affected": False,
    }


def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
    baseline = v4.canonical_scoring_provider(context)
    if baseline.get("status") != "complete":
        return baseline

    scan = legacy._scan(context)
    register = build_canonical_scanner_finding_register(scan, str(context.get("commit_sha") or ""))
    if register["status"] != "complete":
        return legacy._result(
            context,
            "blocked",
            reason="canonical_scanner_finding_count_mismatch",
            canonical_scanner_finding_register=register,
            unavailable_data_notes=[
                "Scanner finding counts could not be reconciled to the canonical finding register."
            ],
        )

    result = deepcopy(baseline)
    assessment = deepcopy(dict(result.get("assessment") or {}))
    technical = _int(
        assessment.get("technical_score")
        or (assessment.get("maturity_signal") or {}).get("technical_score")
        or (assessment.get("maturity_signal") or {}).get("score")
    )
    incomplete = list((assessment.get("score_contract") or {}).get("incomplete_analyzers") or [])
    volume_penalty, category_penalties = _candidate_volume_penalty(register)
    count_only_categories = sum(
        1
        for raw in register["summary_by_category"].values()
        if isinstance(raw, Mapping) and _int(raw.get("count_only")) > 0
    )
    payload_penalty = min(6, count_only_categories * 2)
    execution_penalty = min(12, len(incomplete) * 4)
    assurance_penalty = min(30, volume_penalty + payload_penalty + execution_penalty)
    evidence_adjusted = max(0, technical - assurance_penalty)

    coverage = deepcopy(dict(assessment.get("evidence_coverage") or {}))
    coverage.update(
        {
            "candidate_volume_penalty": volume_penalty,
            "candidate_volume_penalty_by_category": category_penalties,
            "missing_raw_payload_penalty": payload_penalty,
            "incomplete_analyzer_penalty": execution_penalty,
            "candidate_volume_affects_evidence_adjusted_score": True,
            "candidate_volume_affects_technical_score": False,
            "canonical_finding_register_status": register["status"],
            "canonical_finding_count": register["totals"]["raw"],
            "canonical_finding_digest_sha256": register["canonical_digest_sha256"],
        }
    )
    assessment["evidence_coverage"] = coverage
    assessment["canonical_scanner_finding_register"] = register
    assessment["scanner_finding_summary"] = register["summary_by_category"]
    assessment["canonical_evidence_adjusted_score"] = evidence_adjusted
    assessment["evidence_adjusted_score"] = evidence_adjusted

    maturity = deepcopy(dict(assessment.get("maturity_signal") or {}))
    maturity["canonical_evidence_adjusted_score"] = evidence_adjusted
    maturity["evidence_adjusted_score"] = evidence_adjusted
    maturity["evidence_readiness_score"] = evidence_adjusted
    assessment["maturity_signal"] = maturity

    contract = deepcopy(dict(assessment.get("score_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "technical_score": technical,
            "evidence_adjusted_score": evidence_adjusted,
            "candidate_volume_affects_technical_score": False,
            "candidate_volume_affects_evidence_adjusted_score": True,
            "candidate_volume_penalty": volume_penalty,
            "missing_raw_payload_penalty": payload_penalty,
            "incomplete_analyzer_penalty": execution_penalty,
            "assurance_penalty": assurance_penalty,
            "canonical_finding_register_required": True,
            "canonical_finding_count_parity_required": True,
            "canonical_finding_count_parity_verified": register["count_parity_verified"],
        }
    )
    assessment["score_contract"] = contract

    repo = legacy._repo(context)
    operational = _ci_operational_health(repo)
    assessment["ci_cd_operational_health"] = operational
    sections = [deepcopy(item) for item in assessment.get("sections") or [] if isinstance(item, Mapping)]
    for section in sections:
        if section.get("id") == "ci_cd":
            section["configuration_maturity_score"] = section.get("presented_score")
            section["operational_health"] = operational
            section["summary"] = (
                "CI/CD configuration maturity is exact-SHA technical evidence. "
                "Observed workflow outcomes are reported separately as mutable operational health."
            )
    assessment["sections"] = sections
    assessment["executive_summary"] = (
        f"Exact-SHA technical maturity is {technical}/100. Evidence-adjusted readiness is "
        f"{evidence_adjusted}/100 after bounded penalties for unresolved candidate volume, "
        "missing raw candidate payloads, and incomplete applicable analyzers. "
        "Unresolved candidates are not presented as confirmed defects."
    )

    result["assessment"] = assessment
    evidence = deepcopy(dict(result.get("evidence") or {}))
    evidence.update(
        {
            "technical_score": technical,
            "canonical_technical_score": technical,
            "evidence_adjusted_score": evidence_adjusted,
            "canonical_evidence_adjusted_score": evidence_adjusted,
            "candidate_volume_penalty": volume_penalty,
            "missing_raw_payload_penalty": payload_penalty,
            "incomplete_analyzer_penalty": execution_penalty,
            "canonical_scanner_finding_count": register["totals"]["raw"],
            "canonical_scanner_finding_digest_sha256": register["canonical_digest_sha256"],
            "canonical_scanner_finding_count_parity_verified": register["count_parity_verified"],
            "ci_cd_operational_health_score": operational["score"],
            "ci_cd_operational_health_status": operational["status"],
        }
    )
    result["evidence"] = evidence
    result["summary"] = (
        "Canonical scoring completed from exact-SHA technical evidence and a count-reconciled "
        "scanner finding register. Unresolved candidate volume now changes evidence-adjusted "
        "readiness without being misrepresented as confirmed defect severity."
    )
    return result


def scanner_triage_provider(context: dict[str, Any]) -> dict[str, Any]:
    scan = legacy._scan(context)
    if scan.get("status") != "complete":
        return legacy._result(context, "blocked", reason="complete_scanner_evidence_required")
    register = build_canonical_scanner_finding_register(scan, str(context.get("commit_sha") or ""))
    if register["status"] != "complete":
        return legacy._result(
            context,
            "blocked",
            reason="canonical_scanner_finding_count_mismatch",
            canonical_scanner_finding_register=register,
        )
    return legacy._result(
        context,
        summary=(
            "Every retained scanner candidate was normalized into a deterministic canonical register "
            "or explicitly represented as count-only evidence when the raw payload was unavailable."
        ),
        scanner_triage={
            "finding_summary": scan.get("finding_summary") or {},
            "canonical_scanner_finding_register_reference": {
                "artifact_schema": register["artifact_schema"],
                "status": register["status"],
                "exact_commit_sha": register["exact_commit_sha"],
                "canonical_digest_sha256": register["canonical_digest_sha256"],
                "canonical_finding_count": register["totals"]["raw"],
                "count_parity_verified": register["count_parity_verified"],
                "raw_payload_retention_complete": register["raw_payload_retention_complete"],
            },
            "tools_run": scan.get("tools_run") or [],
            "failed_tools": scan.get("failed_tools") or [],
            "timed_out_tools": scan.get("timed_out_tools") or [],
            "unavailable_tools": scan.get("unavailable_tools") or [],
        },
        evidence={
            "canonical_finding_count": register["totals"]["raw"],
            "material": register["totals"]["material"],
            "review": register["totals"]["review_required"],
            "approved": register["totals"]["approved_or_nonblocking"],
            "excluded": register["totals"]["excluded_test_only"],
            "count_only": register["totals"]["count_only"],
            "count_parity_verified": register["count_parity_verified"],
            "canonical_digest_sha256": register["canonical_digest_sha256"],
        },
        unavailable_data_notes=(
            []
            if register["raw_payload_retention_complete"]
            else [
                "One or more scanner categories retained candidate counts without raw payloads; "
                "those candidates remain review-required and reduce evidence-adjusted readiness."
            ]
        ),
    )


def native_comprehensive_providers() -> dict[str, legacy.Provider]:
    providers = v4.native_comprehensive_providers()
    providers["canonical_scoring"] = canonical_scoring_provider
    providers["scanner_triage"] = scanner_triage_provider
    return providers


def install_native_comprehensive_providers(app: FastAPI) -> dict[str, legacy.Provider]:
    v4.install_native_comprehensive_providers(app)
    existing = getattr(app.state, PROVIDER_STATE_KEY, None)
    providers = dict(existing) if isinstance(existing, dict) else {}
    providers.update(native_comprehensive_providers())
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    status = dict(getattr(app.state, "nico_native_comprehensive_provider_status", {}) or {})
    status.update(
        {
            "artifact_schema": VERSION,
            "category_specific_scoring_bound": providers.get("canonical_scoring") is canonical_scoring_provider,
            "canonical_scanner_finding_register_bound": True,
            "canonical_scanner_finding_count_parity_fail_closed": True,
            "candidate_volume_affects_technical_score": False,
            "candidate_volume_affects_evidence_adjusted_score": True,
            "ci_cd_configuration_and_operational_health_separated": True,
            "same_sha_score_deterministic": True,
            "mutable_operational_history_affects_score": False,
            "score_override_allowed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    app.state.nico_native_comprehensive_provider_status = status
    return providers


__all__ = [
    "VERSION",
    "build_canonical_scanner_finding_register",
    "canonical_scoring_provider",
    "install_native_comprehensive_providers",
    "native_comprehensive_providers",
    "scanner_triage_provider",
]
