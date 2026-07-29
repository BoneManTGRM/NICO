from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.phase12_report_remediation_v1 import remediate_assessment
from nico.phase14_analyzer_evidence_v1 import apply_analyzer_evidence

VERSION = "nico.phase15.production-integration.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_FINDING_SURFACES = (
    "canonical_findings",
    "decision_grade_findings_register",
    "findings_register",
    "findings",
    "executive_risk_register",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _valid_sha(value: Any) -> str:
    text = _text(value).lower()
    return text if _SHA_RE.fullmatch(text) else ""


def _commit_sha(payload: Mapping[str, Any]) -> str:
    candidates = [payload.get("commit_sha"), payload.get("immutable_revision"), payload.get("assessed_revision")]
    for key in ("identity", "assessment_identity"):
        identity = payload.get(key)
        if isinstance(identity, Mapping):
            candidates.extend((identity.get("commit_sha"), identity.get("immutable_revision")))
    for value in candidates:
        resolved = _valid_sha(value)
        if resolved:
            return resolved
    return ""


def _combined_findings(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for key in _FINDING_SURFACES:
        values = payload.get(key)
        if isinstance(values, list):
            output.extend(deepcopy(dict(item)) for item in values if isinstance(item, Mapping))
    return output


def _scanner_name(record: Mapping[str, Any]) -> str:
    return _text(record.get("scanner") or record.get("tool") or record.get("name")).casefold()


def _legacy_scanner_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    evidence = payload.get("evidence_health_summary")
    if isinstance(evidence, Mapping):
        for key in ("scanner_records", "records", "incomplete_scanner_records"):
            values = evidence.get(key)
            if isinstance(values, list):
                records.extend(deepcopy(dict(item)) for item in values if isinstance(item, Mapping))
    for key in ("scanner_records", "scanner_execution_records", "analyzer_records"):
        values = payload.get(key)
        if isinstance(values, list):
            records.extend(deepcopy(dict(item)) for item in values if isinstance(item, Mapping))
    return records


def normalize_production_scanner_records(
    records: Iterable[Mapping[str, Any]], *, expected_sha: str
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(records, start=1):
        item = deepcopy(dict(raw))
        name = _scanner_name(item)
        if not name:
            continue
        status = _text(item.get("status")).casefold().replace("-", "_").replace(" ", "_")
        raw_exit = item.get("raw_exit_code", item.get("exit_code"))
        verified = item.get("verified_complete") is True or item.get("capture_complete") is True
        artifact = item.get("artifact_sha256") or item.get("output_sha256") or item.get("artifact_hash")
        if name == "bandit" and raw_exit in (0, 1) and artifact and (
            verified or item.get("json_parseable") is True or item.get("exact_commit_match") is True
        ):
            status = "completed"
        elif status in {"completed_clean", "completed_with_findings", "passed", "pass", "ok", "complete"}:
            status = "completed"
        elif status == "partial":
            status = "capture_truncated"

        commit_sha = _valid_sha(item.get("commit_sha") or item.get("target_sha") or item.get("immutable_revision"))
        if not commit_sha and item.get("exact_commit_match") is True:
            commit_sha = expected_sha
        result = {
            **item,
            "scanner": name,
            "status": status or "unknown",
            "commit_sha": commit_sha or expected_sha,
            "run_sequence": int(item.get("run_sequence") or index),
            "capture_complete": bool(item.get("capture_complete") is True or item.get("verified_complete") is True),
            "artifact_sha256": artifact,
            "exit_code": raw_exit,
            "coverage": deepcopy(item.get("coverage") or item.get("coverage_scope") or {}),
        }
        if status == "not_applicable":
            result["not_applicable_reason"] = _text(
                item.get("not_applicable_reason") or item.get("scope_reason") or item.get("reason")
            ) or "Analyzer is not applicable to the assessed repository scope."
        normalized.append(result)
    return normalized


def integrate_production_truth(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    commit_sha = _commit_sha(result)
    combined = _combined_findings(result)
    if combined:
        result["findings_register"] = combined
        result = remediate_assessment(result, commit_sha=commit_sha)

    raw_records = _legacy_scanner_records(result)
    if commit_sha and raw_records:
        records = normalize_production_scanner_records(raw_records, expected_sha=commit_sha)
        required = {"bandit", "eslint", "gitleaks"}
        required.update(
            _scanner_name(item)
            for item in records
            if item.get("required") is True and _scanner_name(item)
        )
        result = apply_analyzer_evidence(
            result,
            expected_sha=commit_sha,
            records=records,
            required_scanners=sorted(required),
        )
        reconciliation = result["evidence_health_summary"]["phase14_analyzer_evidence"]
        analyzers = deepcopy(reconciliation["analyzers"])
        result["evidence_health_summary"]["scanner_records"] = analyzers
        result["evidence_health_summary"]["completed_scanners"] = [
            item["scanner"] for item in analyzers if item["status"] in {"completed", "success"}
        ]
        result["evidence_health_summary"]["incomplete_scanner_records"] = [
            item for item in analyzers if not item["acceptance_ready"]
        ]

    canonical = list(result.get("canonical_findings") or result.get("findings_register") or [])
    result["executive_risk_register"] = deepcopy(canonical[:7])
    result["priority_findings"] = deepcopy(canonical[:5])
    result["phase15_production_integration"] = {
        "version": VERSION,
        "canonical_population_applied": bool(canonical),
        "canonical_finding_count": len(canonical),
        "analyzer_contract_applied": bool(commit_sha and raw_records),
        "bandit_record_ingested": any(_scanner_name(item) == "bandit" for item in raw_records),
        "legacy_report_surfaces_replaced": True,
    }
    return result


__all__ = ["VERSION", "integrate_production_truth", "normalize_production_scanner_records"]
