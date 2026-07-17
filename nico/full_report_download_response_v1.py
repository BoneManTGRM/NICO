from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "full_report_download_response_v1"
_REQUIRED_HEADERS = (
    "Content-Type",
    "Content-Disposition",
    "Content-Length",
    "ETag",
    "Accept-Ranges",
    "Cache-Control",
)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def build_download_response(
    delivery_record: Mapping[str, Any],
    *,
    requested_assessment_id: str,
    requested_format: str,
) -> dict[str, Any]:
    record = _mapping(delivery_record)
    fmt = str(requested_format or "").strip().lower()
    issues: list[str] = []

    if not record.get("client_delivery_allowed"):
        issues.append("delivery_not_approved")
    if str(record.get("assessment_id") or "") != str(requested_assessment_id or ""):
        issues.append("assessment_identity_mismatch")
    if str(record.get("format") or "").lower() != fmt:
        issues.append("format_mismatch")

    artifact = _mapping(record.get("artifact"))
    filename = str(artifact.get("filename") or "")
    content_type = str(artifact.get("content_type") or "")
    byte_length = int(artifact.get("byte_length") or 0)
    checksum = str(artifact.get("sha256") or "")
    artifact_id = str(artifact.get("artifact_id") or "")

    for field, value in (
        ("artifact_id", artifact_id),
        ("filename", filename),
        ("content_type", content_type),
        ("byte_length", byte_length),
        ("sha256", checksum),
    ):
        if not value:
            issues.append(f"missing_{field}")

    if filename and ("/" in filename or "\\" in filename or filename.startswith(".")):
        issues.append("unsafe_filename")
    if byte_length < 1:
        issues.append("invalid_byte_length")

    allowed = not issues
    headers = {}
    if allowed:
        headers = {
            "Content-Type": content_type,
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(byte_length),
            "ETag": f'"sha256:{checksum}"',
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store, max-age=0",
            "X-NICO-Artifact-ID": artifact_id,
            "X-NICO-Assessment-ID": str(requested_assessment_id),
            "X-NICO-Report-Format": fmt,
        }

    return {
        "version": VERSION,
        "status": "ready" if allowed else "blocked",
        "assessment_id": requested_assessment_id,
        "format": fmt,
        "issues": issues,
        "headers": headers,
        "required_headers_present": allowed and all(name in headers for name in _REQUIRED_HEADERS),
        "range_requests_supported": allowed and headers.get("Accept-Ranges") == "bytes",
        "client_delivery_allowed": allowed,
    }


def attach_download_responses(result: dict[str, Any], *, assessment_id: str) -> dict[str, Any]:
    contract = _mapping(result.get("full_delivery_contract"))
    formats = _mapping(contract.get("formats"))
    responses = {
        fmt: build_download_response(
            _mapping(formats.get(fmt)),
            requested_assessment_id=assessment_id,
            requested_format=fmt,
        )
        for fmt in ("pdf", "html", "markdown")
    }
    all_ready = all(item["client_delivery_allowed"] for item in responses.values())
    result["full_download_responses"] = {
        "version": VERSION,
        "assessment_id": assessment_id,
        "formats": responses,
        "all_formats_ready": all_ready,
        "client_delivery_allowed": all_ready,
    }
    result["client_delivery_allowed"] = bool(result.get("client_delivery_allowed")) and all_ready
    return result


__all__ = ["VERSION", "attach_download_responses", "build_download_response"]
