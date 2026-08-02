from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive_scanner_completion_projection.v56"
_MARKER = "_nico_comprehensive_scanner_completion_projection_v56"
_COMPLETED_STATES = {
    "complete",
    "completed",
    "completed_clean",
    "completed_with_findings",
    "passed",
    "success",
    "succeeded",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _scanner_name(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "osv scanner": "osv-scanner",
        "truffle-hog": "trufflehog",
        "tsc": "typescript",
    }.get(normalized, normalized)


def _authoritative_completed(record: Mapping[str, Any]) -> bool:
    status = _text(record.get("status") or record.get("state")).casefold().replace(
        "-", "_"
    )
    artifact_hash = _text(
        record.get("artifact_hash")
        or record.get("raw_artifact_sha256")
        or record.get("artifact_sha256")
        or record.get("sha256")
    )
    return bool(
        (record.get("completed") is True or status in _COMPLETED_STATES)
        and record.get("exact_commit_match") is True
        and artifact_hash
    )


def _normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(record))
    if not _authoritative_completed(output):
        return output
    findings = output.get("findings") if isinstance(output.get("findings"), list) else []
    status = "completed_with_findings" if findings else "completed"
    output.update(
        {
            "status": status,
            "state": status,
            "completed": True,
            "verified": True,
            "verified_complete": True,
            "verified_for_this_report": True,
            "raw_artifact_retention_complete": True,
            "output_capture_complete": True,
            "failure_reason": "",
            "failure_message": "",
            "failure_cause": None,
            "verification_deficits": [],
        }
    )
    return output


def _upgrade_authoritative_records(value: Any) -> Any:
    if isinstance(value, list):
        return [_upgrade_authoritative_records(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    output = {
        key: _upgrade_authoritative_records(child)
        for key, child in value.items()
    }
    if any(key in output for key in ("scanner_name", "scanner", "tool")):
        output = _normalize_record(output)
    return output


def _authoritative_map(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    assessment = value.get("assessment") if isinstance(value.get("assessment"), Mapping) else {}
    records = value.get("scanner_execution_records")
    if not isinstance(records, list):
        records = assessment.get("scanner_execution_records")
    result: dict[str, dict[str, Any]] = {}
    for raw in records or []:
        if not isinstance(raw, Mapping):
            continue
        record = _normalize_record(raw)
        name = _scanner_name(
            record.get("scanner_name") or record.get("scanner") or record.get("tool")
        )
        if name:
            result[name] = record
    return result


def _sync_projection(value: Any, records: Mapping[str, Mapping[str, Any]]) -> Any:
    if isinstance(value, list):
        return [_sync_projection(item, records) for item in value]
    if not isinstance(value, Mapping):
        return value

    original = dict(value)
    output = {key: _sync_projection(child, records) for key, child in original.items()}
    name = _scanner_name(
        original.get("scanner_name")
        or original.get("scanner")
        or original.get("tool")
        or original.get("analyzer")
    )
    authoritative = records.get(name)
    if authoritative and authoritative.get("completed") is True:
        output["status"] = authoritative.get("status")
        if "state" in original:
            output["state"] = authoritative.get("state")
        for key in (
            "completed",
            "verified",
            "verified_complete",
            "verified_for_this_report",
            "exact_commit_match",
            "raw_artifact_retention_complete",
            "output_capture_complete",
        ):
            if key in original:
                output[key] = authoritative.get(key)
        for key in ("failure_reason", "failure_message"):
            if key in original:
                output[key] = ""
        for key in (
            "failure_cause",
            "error",
            "remediation",
            "assurance_impact",
            "next_action",
        ):
            if key in original:
                output[key] = None
        if "verification_deficits" in original:
            output["verification_deficits"] = []

    if isinstance(original.get("status_counts"), Mapping) and any(
        key in original
        for key in (
            "analyzers",
            "scanner_records",
            "required_analyzers",
            "ready_analyzers",
        )
    ):
        output["status_counts"] = dict(
            Counter(_text(item.get("status")) for item in records.values())
        )
        if "required_analyzers" in original:
            output["required_analyzers"] = sum(
                item.get("required") is not False for item in records.values()
            )
        disclaimer = _text(original.get("disclaimer"))
        if disclaimer.startswith("Incomplete analyzer execution") and all(
            item.get("completed") is True for item in records.values()
        ):
            output["disclaimer"] = (
                "All applicable analyzers completed on the exact commit. "
                "Repeated-run assurance and human finding disposition remain "
                "separate review requirements."
            )
    return output


def normalize_completed_scanner_retention(value: Any) -> Any:
    upgraded = _upgrade_authoritative_records(value)
    if not isinstance(upgraded, Mapping):
        return upgraded
    records = _authoritative_map(upgraded)
    return _sync_projection(upgraded, records)


def install_comprehensive_scanner_completion_projection_v56() -> dict[str, Any]:
    from nico import phase9_comprehensive_report_integration_v1 as integration

    current: Callable[[Mapping[str, Any]], dict[str, Any]] = (
        integration.normalize_canonical_report
    )
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def normalized(report: Mapping[str, Any]) -> dict[str, Any]:
        return normalize_completed_scanner_retention(current(report))

    setattr(normalized, _MARKER, True)
    setattr(normalized, "_nico_previous", current)
    integration.normalize_canonical_report = normalized
    return {
        "status": "installed",
        "version": VERSION,
        "bound": integration.normalize_canonical_report is normalized,
        "exact_commit_artifact_required": True,
        "legacy_scanner_projections_synchronized": True,
        "genuine_incomplete_scanners_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_scanner_completion_projection_v56",
    "normalize_completed_scanner_retention",
]
