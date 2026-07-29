from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

KNOWN_SCANNERS = {
    "bandit", "eslint", "gitleaks", "trufflehog", "semgrep", "typescript",
    "npm-audit", "pip-audit", "osv-scanner",
}
FINDINGS_EXIT_SCANNERS = {"bandit", "eslint", "gitleaks"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _name(value: Any) -> str:
    name = _text(value).casefold().replace("_", "-")
    aliases = {
        "npm audit": "npm-audit", "pip audit": "pip-audit", "osv": "osv-scanner",
        "tsc": "typescript", "truffle-hog": "trufflehog",
    }
    return aliases.get(name, name)


def _records(value: Any, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 10:
        return
    if isinstance(value, Mapping):
        scanner = _name(value.get("scanner_name") or value.get("scanner") or value.get("tool"))
        if scanner in KNOWN_SCANNERS:
            yield value
        for key, child in value.items():
            if key in {"findings", "issues", "results"} and scanner in KNOWN_SCANNERS:
                continue
            yield from _records(child, depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _records(child, depth + 1)


def _artifact_hash(record: Mapping[str, Any]) -> str:
    existing = _text(
        record.get("artifact_hash")
        or record.get("raw_artifact_sha256")
        or record.get("sha256")
        or record.get("artifact_sha256")
        or record.get("deterministic_fingerprint")
    )
    if existing:
        return existing
    retained = {
        "scanner": _name(record.get("scanner_name") or record.get("scanner") or record.get("tool")),
        "commit_sha": _text(record.get("commit_sha") or record.get("snapshot_commit_sha") or record.get("target_commit_sha")),
        "exit_code": record.get("exit_code") if record.get("exit_code") is not None else record.get("returncode"),
        "findings": record.get("findings") or record.get("issues") or record.get("results") or [],
        "stdout": record.get("stdout") or record.get("output") or "",
        "stderr": record.get("stderr") or "",
    }
    if not retained["findings"] and not retained["stdout"] and not retained["stderr"]:
        return ""
    payload = json.dumps(retained, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_record(raw: Mapping[str, Any], commit_sha: str) -> dict[str, Any]:
    item = deepcopy(dict(raw))
    scanner = _name(item.get("scanner_name") or item.get("scanner") or item.get("tool"))
    expected = _text(commit_sha).casefold()
    observed = _text(
        item.get("commit_sha")
        or item.get("snapshot_commit_sha")
        or item.get("target_commit_sha")
        or expected
    ).casefold()
    item["scanner_name"] = scanner
    item["tool"] = scanner
    item["commit_sha"] = observed
    item["snapshot_commit_sha"] = observed
    item["exact_commit_match"] = bool(expected and observed == expected)
    item["findings"] = list(item.get("findings") or item.get("issues") or item.get("results") or [])
    raw_exit = item.get("exit_code") if item.get("exit_code") is not None else item.get("returncode")
    exit_code = raw_exit if isinstance(raw_exit, int) else None
    item["exit_code"] = exit_code
    status = _text(item.get("status") or item.get("state")).casefold().replace("-", "_")
    artifact_hash = _artifact_hash(item)
    item["artifact_hash"] = artifact_hash

    completed_status = status in {
        "complete", "completed", "success", "passed", "completed_clean", "completed_with_findings"
    }
    findings_exit = scanner in FINDINGS_EXIT_SCANNERS and exit_code == 1
    retained_result = bool(artifact_hash and item["exact_commit_match"])
    retention_declared = "raw_artifact_retention_complete" in item
    retention_valid = item.get("raw_artifact_retention_complete") is True if retention_declared else True
    completed = bool(retained_result and retention_valid and (completed_status or findings_exit))
    verified_signal = any(
        item.get(field_name) is True
        for field_name in ("verified", "verified_complete", "verified_for_this_report", "output_capture_complete")
    )

    if completed:
        item["status"] = "completed_with_findings" if item["findings"] or findings_exit else "completed"
        item["completed"] = True
        item["verified"] = bool(verified_signal)
        item["verified_complete"] = bool(verified_signal)
        item["failure_reason"] = ""
        item["failure_message"] = ""
        item["reason"] = ""
    else:
        item["completed"] = False
        item["verified"] = False
        item["verified_complete"] = False
        if status in {"missing", "unavailable", "not_installed", "not_available", "not_applicable"}:
            item["status"] = "unavailable"
        elif status in {"partial", "review_limited"} or completed_status:
            item["status"] = "partial"
        else:
            item["status"] = "failed"
        item["failure_reason"] = _text(
            item.get("failure_reason")
            or item.get("failure_or_unavailable_reason")
            or item.get("failure_message")
            or item.get("reason")
            or item.get("error")
            or item.get("stderr")
        ) or "No complete retained exact-SHA scanner artifact was available."
    item["required"] = item.get("required") is not False
    return item


def reconcile_scanner_records(canonical: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    identity = result.get("identity") if isinstance(result.get("identity"), Mapping) else {}
    commit_sha = _text(identity.get("commit_sha") or result.get("commit_sha")).casefold()
    assessment = deepcopy(dict(result.get("assessment") or {}))

    candidates: list[Mapping[str, Any]] = []
    for source in (
        result.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
        result.get("analyzer_evidence_report"),
        result.get("analyzer_evidence_ui"),
        assessment.get("evidence_health_summary"),
        result.get("stage_summaries"),
        result.get("scanner_results"),
        assessment.get("scanner_results"),
    ):
        candidates.extend(_records(source))

    by_name: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        normalized = normalize_record(candidate, commit_sha)
        name = normalized.get("scanner_name")
        if name not in KNOWN_SCANNERS:
            continue
        current = by_name.get(name)
        richness = lambda value: (
            int(value.get("verified_complete") is True),
            int(value.get("completed") is True),
            int(value.get("raw_artifact_retention_complete") is True),
            int(bool(value.get("artifact_hash"))),
            len(value.get("findings") or []),
            len(_text(value.get("stdout"))) + len(_text(value.get("stderr"))),
        )
        if current is None or richness(normalized) > richness(current):
            by_name[name] = normalized

    records = [by_name[name] for name in sorted(by_name)]
    result["scanner_execution_records"] = deepcopy(records)
    assessment["scanner_execution_records"] = deepcopy(records)
    assessment["incomplete_scanner_records"] = [item for item in records if not item.get("completed")]
    assessment["completed_scanner_records"] = [item for item in records if item.get("completed")]
    result["assessment"] = assessment
    result["v2_scanner_reconciliation"] = {
        "version": "nico.v2.scanner-reconciliation.v2",
        "record_count": len(records),
        "completed_count": sum(item.get("completed") is True for item in records),
        "incomplete_count": sum(item.get("completed") is not True for item in records),
        "returncode_alias_supported": True,
        "exact_sha_artifact_required": True,
    }
    return result


__all__ = ["normalize_record", "reconcile_scanner_records"]
