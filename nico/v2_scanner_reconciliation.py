from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

KNOWN_SCANNERS = {
    "bandit", "eslint", "gitleaks", "trufflehog", "semgrep", "typescript",
    "npm-audit", "pip-audit", "osv-scanner",
}
FINDINGS_EXIT_SCANNERS = {"bandit", "eslint", "gitleaks", "trufflehog"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _name(value: Any) -> str:
    name = _text(value).lower().replace("_", "-")
    aliases = {"npm audit": "npm-audit", "pip audit": "pip-audit", "osv": "osv-scanner", "tsc": "typescript", "truffle-hog": "trufflehog"}
    return aliases.get(name, name)


def _records(value: Any, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 8:
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
    existing = _text(record.get("artifact_hash") or record.get("sha256") or record.get("artifact_sha256"))
    if existing:
        return existing
    retained = {
        "scanner": _name(record.get("scanner_name") or record.get("scanner") or record.get("tool")),
        "commit_sha": _text(record.get("commit_sha") or record.get("snapshot_commit_sha")),
        "exit_code": record.get("exit_code"),
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
    item["scanner_name"] = scanner
    item["commit_sha"] = _text(item.get("commit_sha") or item.get("snapshot_commit_sha") or commit_sha)
    item["exact_commit_match"] = item["commit_sha"] == commit_sha
    item["findings"] = list(item.get("findings") or item.get("issues") or item.get("results") or [])
    exit_code = item.get("exit_code") if isinstance(item.get("exit_code"), int) else None
    status = _text(item.get("status") or item.get("state")).lower().replace("-", "_")
    artifact_hash = _artifact_hash(item)
    item["artifact_hash"] = artifact_hash

    completed_status = status in {"complete", "completed", "success", "passed", "completed_clean", "completed_with_findings"}
    findings_exit = scanner in FINDINGS_EXIT_SCANNERS and exit_code == 1
    retained_result = bool(artifact_hash and item["exact_commit_match"])
    completed = bool(completed_status or (findings_exit and retained_result))

    if completed:
        item["status"] = "completed_with_findings" if item["findings"] or findings_exit else "completed"
        item["completed"] = True
        item["verified"] = retained_result
        item["verified_complete"] = retained_result
        item["failure_reason"] = ""
        item["failure_message"] = ""
    else:
        item["completed"] = False
        item["verified"] = False
        item["verified_complete"] = False
        if status in {"partial", "review_limited"}:
            item["status"] = "partial"
        elif status in {"missing", "unavailable", "not_installed", "not_available"}:
            item["status"] = "unavailable"
        else:
            item["status"] = "failed"
        item["failure_reason"] = _text(item.get("failure_reason") or item.get("failure_message") or item.get("error") or item.get("stderr")) or "No valid exact-SHA scanner artifact was retained."
    return item


def reconcile_scanner_records(canonical: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    identity = result.get("identity") if isinstance(result.get("identity"), Mapping) else {}
    commit_sha = _text(identity.get("commit_sha") or result.get("commit_sha"))
    assessment = deepcopy(dict(result.get("assessment") or {}))

    candidates: list[Mapping[str, Any]] = []
    for source in (
        result.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
        result.get("analyzer_evidence_report"),
        result.get("analyzer_evidence_ui"),
        assessment.get("evidence_health_summary"),
        result.get("stage_summaries"),
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
            1 if value.get("verified_complete") else 0,
            1 if value.get("completed") else 0,
            1 if value.get("artifact_hash") else 0,
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
    return result


__all__ = ["normalize_record", "reconcile_scanner_records"]
