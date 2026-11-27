from __future__ import annotations

import hashlib
import json
from nico.report_json_copy import deepcopy
from collections.abc import Iterable, Mapping
from typing import Any

KNOWN_SCANNERS = {
    "bandit", "eslint", "gitleaks", "trufflehog", "semgrep", "typescript",
    "npm-audit", "pip-audit", "osv-scanner", "cppcheck",
}
FINDINGS_EXIT_SCANNERS = {"bandit", "eslint", "gitleaks"}

# Preserve producer metadata, not raw output or a newly calculated report digest.
# These fields must follow the same selected scanner record across projections.
SCANNER_PROVENANCE_FIELDS = (
    "raw_artifact_sha256", "raw_artifact_retention_complete",
    "raw_artifact_capture_complete", "output_capture_complete",
    "returncode_valid", "timed_out", "output_truncated",
    "exact_commit_match", "snapshot_commit_sha", "target_commit_sha",
    "run_id", "scan_id", "evidence_reference", "category", "required",
    "current_run", "execution_observed_for_this_report",
    "verified_for_this_report", "scans_git_history", "full_history_verified",
    "applicable", "evidence_required", "applicability_reason",
    "applicability_evidence", "native_json_output", "no_vulnerabilities_claimed",
    "scanner_tool_version", "coverage_scope",
    "worker_provenance", "cppcheck_source_coverage", "cpp_build_evidence",
)


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
    kind = type(value)
    if kind is dict:
        scanner = _name(value.get("scanner_name") or value.get("scanner") or value.get("tool"))
        if scanner in KNOWN_SCANNERS:
            yield value
        for key, child in value.items():
            if key in {"findings", "issues", "results"} and scanner in KNOWN_SCANNERS:
                continue
            if (type(child) is not str and type(child) is not int and type(child) is not float and type(child) is not bool and type(child) is not type(None)):
                yield from _records(child, depth + 1)
    elif kind is list or kind is tuple:
        for child in value:
            if (type(child) is not str and type(child) is not int and type(child) is not float and type(child) is not bool and type(child) is not type(None)):
                yield from _records(child, depth + 1)
    elif (kind is str or kind is int or kind is float or kind is bool or kind is type(None)):
        return
    elif isinstance(value, Mapping):
        scanner = _name(value.get("scanner_name") or value.get("scanner") or value.get("tool"))
        if scanner in KNOWN_SCANNERS:
            yield value
        for key, child in value.items():
            if key in {"findings", "issues", "results"} and scanner in KNOWN_SCANNERS:
                continue
            if (type(child) is not str and type(child) is not int and type(child) is not float and type(child) is not bool and type(child) is not type(None)):
                yield from _records(child, depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            if (type(child) is not str and type(child) is not int and type(child) is not float and type(child) is not bool and type(child) is not type(None)):
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


def worker_record_has_native_observation(record: Mapping[str, Any]) -> bool:
    return any(key in record for key in (
        "execution_observed_for_this_report", "scanner_execution_receipt", "raw_artifact_capture_complete",
    ))


def declared_artifact_digest(record: Mapping[str, Any]) -> str:
    for name in ("artifact_hash", "raw_artifact_sha256", "sha256", "artifact_sha256"):
        digest = _text(record.get(name)).casefold().removeprefix("sha256:")
        if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
            return digest
    return ""


def declared_commit_values(record: Mapping[str, Any]) -> set[str]:
    return {_text(record.get(key)).casefold() for key in
            ("commit_sha", "snapshot_commit_sha", "target_commit_sha") if _text(record.get(key))}


def _retained_ci_projection(record: Mapping[str, Any]) -> bool:
    """Identify the protected import projection; not a durable verifier."""
    sha = _text(record.get("ci_source_sha")).casefold()
    return (
        _name(record.get("scanner_name") or record.get("scanner") or record.get("tool")) == "typescript"
        and record.get("execution_source") == "authenticated_nico_postbuild_ci"
        and record.get("metadata_authenticated") is True
        and record.get("current_run") is False and record.get("execution_observed_for_this_report") is False
        and all(record.get(k) is True for k in ("output_capture_complete", "returncode_valid", "raw_artifact_retention_complete", "verified_for_this_report"))
        and len(sha) == 40 and declared_commit_values(record) == {sha}
        and all(_text(record.get(k)).isascii() and _text(record.get(k)).isdigit() and _text(record.get(k)).lstrip("0")
                for k in ("ci_run_id", "ci_run_attempt", "ci_artifact_id", "ci_workflow_id"))
        and bool(declared_artifact_digest(record))
    )


def explicit_execution_deficit(record: Mapping[str, Any]) -> bool:
    """A retained report or a findings exit cannot reverse observed failure."""
    status = _text(record.get("status") or record.get("state")).casefold().replace("-", "_")
    worker_observation = worker_record_has_native_observation(record)
    return (
        any(record.get(key) is True for key in ("timed_out", "output_truncated", "output_limit_exceeded"))
        or record.get("returncode_valid") is False
        or ((worker_observation or status in {"failed", "partial", "timeout", "timed_out"}) and any(
            record.get(key) is False for key in (
                "output_capture_complete", "raw_artifact_capture_complete",
                "raw_artifact_retention_complete", "verified_for_this_report",
            )
        ))
        or (record.get("execution_observed_for_this_report") is False and not _retained_ci_projection(record))
    )


def scanner_observation_key(record: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Require one exact scoped native artifact; never match on scanner name alone."""
    scanner = _name(record.get("scanner_name") or record.get("scanner") or record.get("tool"))
    sha = _text(record.get("commit_sha") or record.get("snapshot_commit_sha") or record.get("target_commit_sha")).casefold()
    run_id = _text(record.get("run_id"))
    scan_id = _text(record.get("scan_id"))
    digest = _text(record.get("raw_artifact_sha256")).casefold().removeprefix("sha256:")
    if (
        scanner not in KNOWN_SCANNERS or not run_id or not scan_id
        or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha)
        or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
    ):
        return None
    return scanner, sha, run_id, scan_id, digest


def normalize_record(raw: Mapping[str, Any], commit_sha: str) -> dict[str, Any]:
    item = deepcopy(dict(raw))
    scanner = _name(item.get("scanner_name") or item.get("scanner") or item.get("tool"))
    expected = _text(commit_sha).casefold()
    explicit_commits = declared_commit_values(raw)
    worker_observation = worker_record_has_native_observation(raw)
    observed = next(iter(explicit_commits)) if len(explicit_commits) == 1 else ""
    if not observed and not explicit_commits and not worker_observation and raw.get("exact_commit_match") is True:
        # Preserve an earlier explicit legacy attestation, not an inferred native match.
        observed = expected
    item["scanner_name"] = scanner
    item["tool"] = scanner
    item["commit_sha"] = observed
    item["snapshot_commit_sha"] = observed
    item["exact_commit_match"] = bool(expected and observed == expected and raw.get("exact_commit_match") is not False)
    item["findings"] = list(item.get("findings") or item.get("issues") or item.get("results") or [])
    try:
        finding_count = max(0, int(item.get("finding_count") or len(item["findings"])))
    except (TypeError, ValueError):
        finding_count = len(item["findings"])
    item["finding_count"] = finding_count
    raw_exit = item.get("exit_code") if item.get("exit_code") is not None else item.get("returncode")
    exit_code = raw_exit if isinstance(raw_exit, int) else None
    item["exit_code"] = exit_code
    status = _text(item.get("status") or item.get("state")).casefold().replace("-", "_")
    supplied_digest = declared_artifact_digest(item)
    # A locally derived legacy evidence-summary hash is not a native receipt.
    legacy_hash = _artifact_hash(item) if not worker_observation else ""
    artifact_hash = supplied_digest or legacy_hash
    if len(artifact_hash) != 64 or any(c not in "0123456789abcdef" for c in artifact_hash.casefold()):
        artifact_hash = ""
    item["artifact_hash"] = artifact_hash

    completed_status = status in {
        "complete", "completed", "success", "passed", "completed_clean", "completed_with_findings"
    }
    findings_exit = scanner in FINDINGS_EXIT_SCANNERS and exit_code == 1
    retained_result = bool(artifact_hash and item["exact_commit_match"])
    retention_declared = "raw_artifact_retention_complete" in item
    retention_valid = item.get("raw_artifact_retention_complete") is True if retention_declared else True
    completed = bool(
        retained_result and retention_valid and not explicit_execution_deficit(item)
        and (completed_status or findings_exit)
    )
    verification_fields = ("verified", "verified_complete", "verified_for_this_report", "output_capture_complete")
    verification_declared = any(field_name in item for field_name in verification_fields)
    verified_signal = any(item.get(field_name) is True for field_name in verification_fields)
    verified = bool(completed and retention_valid and (verified_signal if verification_declared else retained_result))

    if status == "not_applicable":
        # Preserve the producer's applicability observation and inventory. This is
        # not completion credit; the independent acceptance gate validates its basis.
        item.update({
            "status": "not_applicable", "state": "not_applicable",
            "completed": False, "verified": False, "verified_complete": False,
            "verified_for_this_report": False,
        })
    elif completed:
        item["status"] = (
            "completed_with_findings"
            if item["findings"] or finding_count > 0 or findings_exit
            else "completed"
        )
        item["completed"] = True
        item["verified"] = verified
        item["verified_complete"] = verified
        item["failure_reason"] = ""
        item["failure_message"] = ""
        item["reason"] = ""
    else:
        item["completed"] = False
        item["verified"] = False
        item["verified_complete"] = False
        item["verified_for_this_report"] = False
        if status in {"missing", "unavailable", "not_installed", "not_available", "not_applicable"}:
            item["status"] = "unavailable"
        elif item.get("timed_out") is True or status in {"timeout", "timed_out"}:
            item["status"] = "timed_out"
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
    item["state"] = item["status"]
    item["required"] = item.get("required") is not False
    return item


def reconcile_scanner_records(canonical: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    identity = result.get("identity") if isinstance(result.get("identity"), Mapping) else {}
    commit_sha = _text(identity.get("commit_sha") or result.get("commit_sha")).casefold()
    run_id = _text(identity.get("run_id") or result.get("run_id"))
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

    candidates = [
        row for row in candidates
        if not (run_id and _text(row.get("run_id")) and _text(row.get("run_id")) != run_id)
    ]
    incomplete_native: dict[tuple[str, ...], Mapping[str, Any]] = {}
    for raw in candidates:
        key = scanner_observation_key(raw)
        if (key and run_id and key[1] == commit_sha and key[2] == run_id
                and type(raw.get("execution_observed_for_this_report")) is bool
                and type(raw.get("output_capture_complete")) is bool
                and explicit_execution_deficit(raw)):
            incomplete_native.setdefault(key, raw)

    by_name: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        authoritative = incomplete_native.get(scanner_observation_key(candidate), candidate)
        normalized = normalize_record(authoritative, commit_sha)
        name = normalized.get("scanner_name")
        if name not in KNOWN_SCANNERS:
            continue
        current = by_name.get(name)
        richness = lambda value: (
            int(value.get("verified_complete") is True),
            int(value.get("completed") is True),
            int(value.get("raw_artifact_retention_complete") is True),
            int(bool(value.get("artifact_hash"))),
            int(value.get("finding_count") or len(value.get("findings") or [])),
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
        "version": "nico.v2.scanner-reconciliation.v3",
        "record_count": len(records),
        "completed_count": sum(item.get("completed") is True for item in records),
        "incomplete_count": sum(item.get("completed") is not True for item in records),
        "returncode_alias_supported": True,
        "finding_count_alias_supported": True,
        "exact_sha_artifact_required": True,
        "retained_exact_sha_artifact_is_verification_default": True,
    }
    return result


__all__ = ["normalize_record", "reconcile_scanner_records"]
