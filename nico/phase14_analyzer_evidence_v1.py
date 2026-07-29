from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

VERSION = "nico.phase14.analyzer-evidence.v2"
TERMINAL_SUCCESS = {"completed", "success", "not_applicable"}
TERMINAL_FAILURE = {"failed", "timed_out", "capture_truncated", "unsupported_target"}
DEFAULT_REQUIRED_SCANNERS = ("bandit", "eslint", "gitleaks")


class AnalyzerEvidenceError(ValueError):
    pass


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _sha(value: Any, label: str) -> str:
    text = _text(value).lower()
    if len(text) != 40 or any(ch not in "0123456789abcdef" for ch in text):
        raise AnalyzerEvidenceError(f"{label} must be a full commit SHA")
    return text


def _digest(value: Any, label: str) -> str:
    text = _text(value).lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise AnalyzerEvidenceError(f"{label} must be a SHA-256 digest")
    return text


def classify_status(record: Mapping[str, Any]) -> str:
    status = _text(record.get("status")).casefold()
    if status in TERMINAL_SUCCESS | TERMINAL_FAILURE:
        return status
    exit_reason = _text(record.get("exit_reason") or record.get("failure_cause")).casefold()
    if "timeout" in exit_reason:
        return "timed_out"
    if "truncat" in exit_reason or record.get("capture_complete") is False:
        return "capture_truncated"
    if "unsupported" in exit_reason:
        return "unsupported_target"
    if record.get("exit_code") not in (None, 0):
        return "failed"
    return "unknown"


def normalize_record(record: Mapping[str, Any], *, expected_sha: str) -> dict[str, Any]:
    item = deepcopy(dict(record))
    name = _text(item.get("scanner") or item.get("name") or item.get("tool")).casefold()
    if not name:
        raise AnalyzerEvidenceError("scanner name is required")
    commit_sha = _sha(item.get("commit_sha") or item.get("target_sha"), f"{name}.commit_sha")
    if commit_sha != _sha(expected_sha, "expected_sha"):
        raise AnalyzerEvidenceError(f"{name} evidence is bound to a different commit")
    status = classify_status(item)
    item.update({"scanner": name, "commit_sha": commit_sha, "status": status})
    item["run_sequence"] = int(item.get("run_sequence") or 0)
    if status in TERMINAL_SUCCESS:
        item["artifact_sha256"] = _digest(
            item.get("artifact_sha256") or item.get("output_sha256") or item.get("artifact_hash"),
            f"{name}.artifact_sha256",
        )
        if item.get("capture_complete") is not True:
            raise AnalyzerEvidenceError(f"{name} successful evidence must be fully captured")
    item["confirmed_client_defect"] = bool(item.get("confirmed_client_defect")) if status in TERMINAL_SUCCESS else False
    item["coverage"] = deepcopy(item.get("coverage") or {})
    return item


def _trailing_successes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda item: (item.get("run_sequence", 0), item.get("artifact_sha256", "")))
    trailing: list[dict[str, Any]] = []
    for item in reversed(ordered):
        if item["status"] not in TERMINAL_SUCCESS:
            break
        trailing.append(item)
    trailing.reverse()
    return trailing


def _failure_explanation(status: str) -> tuple[str | None, str | None, str | None]:
    messages = {
        "missing": (
            "Required analyzer evidence is missing.",
            "Assurance is constrained; no client defect is inferred.",
            "Run the analyzer twice against the exact assessment commit and retain complete hashed artifacts.",
        ),
        "failed": (
            "The analyzer process exited unsuccessfully.",
            "Its result cannot support or create a confirmed client finding.",
            "Repair the analyzer invocation and repeat two exact-SHA runs.",
        ),
        "timed_out": (
            "The analyzer exceeded its bounded execution window.",
            "Coverage is incomplete and assurance must be reduced.",
            "Tune scope or timeout limits, then repeat two exact-SHA runs.",
        ),
        "capture_truncated": (
            "Analyzer output was not captured completely.",
            "Counts and findings may be incomplete and cannot be treated as decision-grade evidence.",
            "Persist the complete output, hash it, and repeat two exact-SHA runs.",
        ),
        "unsupported_target": (
            "The target is unsupported by this analyzer.",
            "This is an evidence limitation, not a confirmed defect.",
            "Mark the analyzer not applicable with documented scope or use a supported replacement.",
        ),
        "unknown": (
            "Analyzer state could not be classified.",
            "The evidence is non-decision-grade.",
            "Record an explicit terminal state, complete capture, exact SHA, and artifact digest.",
        ),
    }
    return messages.get(status, (None, None, None))


def reconcile_analyzers(
    records: Iterable[Mapping[str, Any]],
    *,
    expected_sha: str,
    required_scanners: Iterable[str] = DEFAULT_REQUIRED_SCANNERS,
    consecutive_passes_required: int = 2,
) -> dict[str, Any]:
    commit_sha = _sha(expected_sha, "expected_sha")
    if consecutive_passes_required < 1:
        raise AnalyzerEvidenceError("consecutive_passes_required must be at least 1")
    required = {_text(name).casefold() for name in required_scanners if _text(name)}
    by_scanner: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        item = normalize_record(record, expected_sha=commit_sha)
        by_scanner.setdefault(item["scanner"], []).append(item)

    summaries: list[dict[str, Any]] = []
    ready = True
    for scanner in sorted(required | set(by_scanner)):
        scanner_records = by_scanner.get(scanner, [])
        ordered = sorted(scanner_records, key=lambda item: item.get("run_sequence", 0))
        trailing = _trailing_successes(ordered)
        latest = ordered[-1] if ordered else {"status": "missing", "coverage": {}}
        complete = scanner not in required or len(trailing) >= consecutive_passes_required
        if scanner in required and not complete:
            ready = False
        cause, impact, remediation = _failure_explanation(latest.get("status", "missing"))
        summaries.append(
            {
                "scanner": scanner,
                "required": scanner in required,
                "status": latest.get("status", "missing"),
                "successful_passes": sum(item["status"] in TERMINAL_SUCCESS for item in ordered),
                "consecutive_successful_passes": len(trailing),
                "consecutive_passes_required": consecutive_passes_required,
                "acceptance_ready": complete,
                "artifact_sha256": [item.get("artifact_sha256") for item in trailing],
                "coverage": deepcopy(latest.get("coverage") or {}),
                "client_defect_allowed": latest.get("status") in TERMINAL_SUCCESS,
                "failure_cause": cause,
                "assurance_impact": impact,
                "remediation": remediation,
            }
        )

    result = {
        "schema": VERSION,
        "commit_sha": commit_sha,
        "required_scanners": sorted(required),
        "consecutive_passes_required": consecutive_passes_required,
        "acceptance_ready": ready,
        "analyzers": summaries,
    }
    result["evidence_manifest_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def apply_analyzer_evidence(
    assessment: Mapping[str, Any],
    *,
    expected_sha: str,
    records: Iterable[Mapping[str, Any]] | None = None,
    required_scanners: Iterable[str] = DEFAULT_REQUIRED_SCANNERS,
) -> dict[str, Any]:
    result = deepcopy(dict(assessment))
    evidence = result.get("evidence_health_summary")
    evidence_map = deepcopy(dict(evidence)) if isinstance(evidence, Mapping) else {}
    source_records = list(records) if records is not None else list(
        evidence_map.get("scanner_records") or evidence_map.get("records") or []
    )
    reconciliation = reconcile_analyzers(
        (item for item in source_records if isinstance(item, Mapping)),
        expected_sha=expected_sha,
        required_scanners=required_scanners,
    )
    evidence_map["phase14_analyzer_evidence"] = reconciliation
    evidence_map["acceptance_ready"] = reconciliation["acceptance_ready"]
    evidence_map["incomplete_analyzers"] = [
        item for item in reconciliation["analyzers"] if item["required"] and not item["acceptance_ready"]
    ]
    result["evidence_health_summary"] = evidence_map
    result["delivery_gate"] = deepcopy(dict(result.get("delivery_gate") or {}))
    result["delivery_gate"]["analyzer_evidence_ready"] = reconciliation["acceptance_ready"]
    result["delivery_gate"]["analyzer_evidence_manifest_sha256"] = reconciliation["evidence_manifest_sha256"]
    return result


__all__ = [
    "VERSION",
    "DEFAULT_REQUIRED_SCANNERS",
    "AnalyzerEvidenceError",
    "classify_status",
    "normalize_record",
    "reconcile_analyzers",
    "apply_analyzer_evidence",
]
