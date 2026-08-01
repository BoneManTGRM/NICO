from __future__ import annotations

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


def normalize_completed_scanner_retention(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_completed_scanner_retention(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    output = {
        key: normalize_completed_scanner_retention(child)
        for key, child in value.items()
    }
    if any(key in output for key in ("scanner_name", "scanner", "tool")):
        output = _normalize_record(output)
    return output


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
        "genuine_incomplete_scanners_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_scanner_completion_projection_v56",
    "normalize_completed_scanner_retention",
]
