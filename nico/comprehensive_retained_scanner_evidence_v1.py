from __future__ import annotations

from typing import Any, Mapping

from nico.v2_scanner_reconciliation import KNOWN_SCANNERS, normalize_record

VERSION = "nico.comprehensive_retained_scanner_evidence.v1"


def _text(value: Any, limit: int = 900) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _name(value: Any) -> str:
    name = _text(value, 120).casefold().replace("_", "-")
    aliases = {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "tsc": "typescript",
        "truffle-hog": "trufflehog",
    }
    return aliases.get(name, name)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set)) else []


def _prior_stages(context: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(context.get("prior_stage_results"))


def _dependency_stage(context: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_prior_stages(context).get("dependency_security_static_analysis"))


def _triage_stage(context: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_prior_stages(context).get("deep_scanner_triage"))


def _score_stage(context: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_prior_stages(context).get("evidence_reconciliation_and_scoring"))


def _scan_id(context: Mapping[str, Any]) -> str:
    for stage in (_dependency_stage(context), _triage_stage(context)):
        direct = _text(stage.get("scan_id"), 160)
        if direct:
            return direct
        for key in ("scanner", "scanner_triage"):
            nested = _mapping(stage.get(key))
            value = _text(nested.get("scan_id"), 160)
            if value:
                return value
    return ""


def _manifest(context: Mapping[str, Any]) -> dict[str, Any]:
    dependency = _dependency_stage(context)
    triage = _triage_stage(context)
    scanner = _mapping(dependency.get("scanner"))
    scanner_triage = _mapping(triage.get("scanner_triage"))
    pre_render = _mapping(context.get("pre_render_scanner_truth"))

    requested = {
        _name(value)
        for value in (
            _list(scanner.get("tools_requested"))
            + _list(scanner_triage.get("tools_requested"))
            + _list(pre_render.get("requested"))
        )
        if _name(value) in KNOWN_SCANNERS
    }
    completed = {
        _name(value)
        for value in (
            _list(scanner.get("tools_run"))
            + _list(scanner_triage.get("tools_run"))
            + _list(pre_render.get("completed"))
        )
        if _name(value) in KNOWN_SCANNERS
    }
    failed = {
        _name(value)
        for value in (
            _list(scanner.get("failed_tools"))
            + _list(scanner_triage.get("failed_tools"))
        )
        if _name(value) in KNOWN_SCANNERS
    }
    unavailable = {
        _name(value)
        for value in (
            _list(scanner.get("unavailable_tools"))
            + _list(scanner_triage.get("unavailable_tools"))
        )
        if _name(value) in KNOWN_SCANNERS
    }
    timed_out = {
        _name(value)
        for value in (
            _list(scanner.get("timed_out_tools"))
            + _list(scanner_triage.get("timed_out_tools"))
        )
        if _name(value) in KNOWN_SCANNERS
    }
    incomplete = {
        _name(value)
        for value in _list(pre_render.get("incomplete"))
        if _name(value) in KNOWN_SCANNERS
    }
    requested |= completed | failed | unavailable | timed_out | incomplete
    completed -= failed | unavailable | timed_out | incomplete

    return {
        "scan_id": _scan_id(context),
        "snapshot_commit_sha": _text(
            scanner.get("actual_commit_sha")
            or scanner.get("snapshot_commit_sha")
            or context.get("commit_sha"),
            80,
        ).casefold(),
        "snapshot_match": scanner.get("snapshot_match") is True,
        "tools_requested": sorted(requested),
        "tools_run": sorted(completed),
        "failed_tools": sorted(failed),
        "unavailable_tools": sorted(unavailable),
        "timed_out_tools": sorted(timed_out),
        "incomplete_tools": sorted(incomplete),
        "finding_summary": dict(
            scanner.get("finding_summary")
            or scanner_triage.get("finding_summary")
            or {}
        ),
    }


def _record_candidates(context: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    dependency = _dependency_stage(context)
    triage = _triage_stage(context)
    scoring = _score_stage(context)
    assessment = _mapping(scoring.get("assessment"))
    candidates: list[Mapping[str, Any]] = []
    for value in (
        dependency.get("scanner_execution_records"),
        _mapping(dependency.get("scanner")).get("scanner_execution_records"),
        triage.get("scanner_execution_records"),
        _mapping(triage.get("scanner_triage")).get("scanner_execution_records"),
        scoring.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
    ):
        for item in _list(value):
            if isinstance(item, Mapping):
                candidates.append(item)
    return candidates


def compact_scanner_records(
    scan: Mapping[str, Any],
    *,
    commit_sha: str,
) -> list[dict[str, Any]]:
    """Retain one small, exact-SHA scanner record per tool at scanner completion.

    The raw scanner result remains in the scanner evidence store under ``scan_id``.
    Comprehensive run state retains only the fields needed for deterministic report
    truth, verification, triage counts, and evidence lookup. Large findings and output
    previews are deliberately not copied into the final-report critical path.
    """

    scan_id = _text(scan.get("scan_id"), 160)
    summary = _mapping(scan.get("finding_summary"))
    by_tool = _mapping(summary.get("by_tool"))
    output: list[dict[str, Any]] = []
    for raw in _list(scan.get("scanner_results")):
        if not isinstance(raw, Mapping):
            continue
        normalized = normalize_record(raw, commit_sha)
        name = _name(normalized.get("scanner_name"))
        if name not in KNOWN_SCANNERS:
            continue
        findings = _list(raw.get("findings") or raw.get("issues") or raw.get("results"))
        artifact_hash = _text(normalized.get("artifact_hash"), 160)
        exact = normalized.get("exact_commit_match") is True
        retained = bool(scan_id and artifact_hash and exact)
        tool_summary = dict(_mapping(by_tool.get(name)))
        output.append(
            {
                "scanner_name": name,
                "tool": name,
                "category": _text(raw.get("category"), 80) or "unknown",
                "status": normalized.get("status"),
                "state": normalized.get("status"),
                "completed": normalized.get("completed") is True,
                "verified": normalized.get("verified") is True,
                "verified_complete": normalized.get("verified_complete") is True,
                "verified_for_this_report": (
                    raw.get("verified_for_this_report") is True
                    or normalized.get("verified_complete") is True
                ),
                "current_run": raw.get("current_run") is True,
                "execution_observed_for_this_report": (
                    raw.get("execution_observed_for_this_report") is True
                ),
                "output_capture_complete": raw.get("output_capture_complete") is True,
                "raw_artifact_capture_complete": (
                    raw.get("raw_artifact_capture_complete") is True
                ),
                "returncode_valid": raw.get("returncode_valid") is True,
                "timed_out": raw.get("timed_out") is True,
                "output_truncated": raw.get("output_truncated") is True,
                "scans_git_history": raw.get("scans_git_history") is True,
                "full_history_verified": raw.get("full_history_verified") is True,
                "required": raw.get("required") is not False,
                "exit_code": normalized.get("exit_code"),
                "commit_sha": _text(commit_sha, 80).casefold(),
                "snapshot_commit_sha": _text(commit_sha, 80).casefold(),
                "target_commit_sha": _text(commit_sha, 80).casefold(),
                "exact_commit_match": exact,
                "artifact_hash": artifact_hash,
                "raw_artifact_retention_complete": (
                    raw.get("raw_artifact_retention_complete") is True or retained
                ),
                "evidence_reference": (
                    f"scanner_runs/{scan_id}" if scan_id else ""
                ),
                "scan_id": scan_id,
                "finding_count": len(findings),
                "finding_summary": tool_summary,
                "duration_seconds": raw.get("duration_seconds"),
                "failure_reason": _text(
                    normalized.get("failure_reason")
                    or raw.get("reason")
                    or raw.get("error"),
                    600,
                ),
                "findings": [],
                "compact_record": True,
                "raw_findings_embedded": False,
            }
        )
    return sorted(output, key=lambda item: str(item.get("scanner_name") or ""))


def retained_scanner_payload(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return scanner truth already retained by this exact Comprehensive run.

    This function never calls the scanner worker, scanner store, repository clone, or a
    scanner tool. Missing compact artifacts remain explicitly incomplete rather than
    triggering hidden final-stage work.
    """

    commit_sha = _text(context.get("commit_sha"), 80).casefold()
    manifest = _manifest(context)
    records: dict[str, dict[str, Any]] = {}
    for candidate in _record_candidates(context):
        normalized = normalize_record(candidate, commit_sha)
        name = _name(normalized.get("scanner_name"))
        if name not in KNOWN_SCANNERS:
            continue
        current = records.get(name)
        richness = (
            int(normalized.get("verified_complete") is True),
            int(normalized.get("completed") is True),
            int(bool(normalized.get("artifact_hash"))),
        )
        current_richness = (
            int(current.get("verified_complete") is True),
            int(current.get("completed") is True),
            int(bool(current.get("artifact_hash"))),
        ) if current else (-1, -1, -1)
        if richness > current_richness:
            records[name] = dict(candidate)

    source = "retained_exact_run_compact_records"
    if not records:
        source = "retained_exact_run_manifest_without_artifacts"
        requested = set(manifest["tools_requested"])
        completed = set(manifest["tools_run"])
        failed = set(manifest["failed_tools"])
        unavailable = set(manifest["unavailable_tools"])
        timed_out = set(manifest["timed_out_tools"])
        incomplete = set(manifest["incomplete_tools"])
        for name in sorted(requested):
            if name in unavailable:
                status = "unavailable"
                reason = "The retained scanner manifest records this tool as unavailable."
            elif name in timed_out:
                status = "failed"
                reason = "The retained scanner manifest records this tool as timed out."
            elif name in failed:
                status = "failed"
                reason = "The retained scanner manifest records this tool as failed."
            elif name in incomplete or name in completed:
                status = "partial"
                reason = (
                    "The tool ran, but no compact exact-SHA artifact record was retained "
                    "in the Comprehensive run."
                )
            else:
                status = "unavailable"
                reason = "No retained scanner execution record was available."
            records[name] = {
                "scanner_name": name,
                "tool": name,
                "status": status,
                "state": status,
                "completed": False,
                "verified": False,
                "verified_complete": False,
                "required": True,
                "commit_sha": commit_sha,
                "snapshot_commit_sha": commit_sha,
                "exact_commit_match": bool(commit_sha),
                "artifact_hash": "",
                "raw_artifact_retention_complete": False,
                "scan_id": manifest["scan_id"],
                "evidence_reference": (
                    f"scanner_runs/{manifest['scan_id']}" if manifest["scan_id"] else ""
                ),
                "finding_count": 0,
                "findings": [],
                "failure_reason": reason,
                "compact_record": True,
                "raw_findings_embedded": False,
            }

    normalized_records = [
        normalize_record(records[name], commit_sha)
        for name in sorted(records)
    ]
    return {
        "version": VERSION,
        "source": source,
        "scan_id": manifest["scan_id"],
        "snapshot_commit_sha": manifest["snapshot_commit_sha"] or commit_sha,
        "actual_commit_sha": manifest["snapshot_commit_sha"] or commit_sha,
        "snapshot_match": manifest["snapshot_match"] or bool(commit_sha),
        "tools_requested": manifest["tools_requested"] or sorted(records),
        "tools_run": manifest["tools_run"],
        "failed_tools": manifest["failed_tools"],
        "unavailable_tools": manifest["unavailable_tools"],
        "timed_out_tools": manifest["timed_out_tools"],
        "finding_summary": manifest["finding_summary"],
        "scanner_execution_records": normalized_records,
        "record_count": len(normalized_records),
        "verified_record_count": sum(
            item.get("verified_complete") is True for item in normalized_records
        ),
        "final_stage_scanner_store_read": False,
        "final_stage_scanner_execution": False,
        "raw_scanner_outputs_embedded": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "compact_scanner_records",
    "retained_scanner_payload",
]
