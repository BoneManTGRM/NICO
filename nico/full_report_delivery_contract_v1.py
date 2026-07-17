from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "full_report_delivery_contract_v1"
FORMATS = ("pdf", "html", "markdown")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_delivery_record(
    release: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    *,
    assessment_id: str,
    report_format: str,
) -> dict[str, Any]:
    release_data = deepcopy(dict(release))
    artifact_data = deepcopy(dict(artifacts))
    fmt = str(report_format or "").strip().lower()
    issues: list[str] = []

    if fmt not in FORMATS:
        issues.append("unsupported_format")
    if not release_data.get("client_delivery_allowed"):
        issues.append("release_not_approved")
    if not artifact_data.get("client_delivery_allowed"):
        issues.append("artifacts_not_approved")

    release_id = str(release_data.get("assessment_id") or assessment_id)
    artifact_id = str(artifact_data.get("assessment_id") or assessment_id)
    if release_id != artifact_id:
        issues.append("assessment_identity_mismatch")

    release_locale = str(release_data.get("locale") or "en").lower()
    artifact_locale = str(artifact_data.get("locale") or release_locale).lower()
    if release_locale != artifact_locale:
        issues.append("locale_mismatch")

    records = _mapping(artifact_data.get("artifacts"))
    record = _mapping(records.get(fmt)) if fmt in FORMATS else {}
    for field in ("artifact_id", "filename", "content_type", "byte_length", "sha256"):
        if not record.get(field):
            issues.append(f"missing_{field}")

    allowed = not issues
    return {
        "version": VERSION,
        "assessment_id": assessment_id,
        "locale": release_locale,
        "format": fmt,
        "status": "available" if allowed else "blocked",
        "issues": issues,
        "client_delivery_allowed": allowed,
        "artifact": deepcopy(record) if allowed else None,
    }


def attach_delivery_contract(result: dict[str, Any], *, assessment_id: str) -> dict[str, Any]:
    release = _mapping(result.get("full_production_release"))
    artifacts = _mapping(result.get("full_artifact_manifest"))
    formats = {
        fmt: build_delivery_record(
            release,
            artifacts,
            assessment_id=assessment_id,
            report_format=fmt,
        )
        for fmt in FORMATS
    }
    all_available = all(item["client_delivery_allowed"] for item in formats.values())
    result["full_delivery_contract"] = {
        "version": VERSION,
        "assessment_id": assessment_id,
        "formats": formats,
        "all_formats_available": all_available,
        "client_delivery_allowed": all_available,
    }
    result["client_delivery_allowed"] = bool(result.get("client_delivery_allowed")) and all_available
    return result


__all__ = ["FORMATS", "VERSION", "attach_delivery_contract", "build_delivery_record"]
