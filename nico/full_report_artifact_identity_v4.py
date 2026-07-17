from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

VERSION = "full_report_artifact_identity_v4"
_REQUIRED_FORMATS = ("pdf", "html", "markdown")


@dataclass(frozen=True)
class ArtifactIdentity:
    format: str
    artifact_id: str
    sha256: str
    byte_length: int
    content_type: str
    filename: str


def _locale(value: Any) -> str:
    raw = str(value or "en").lower().replace("_", "-")
    return "es" if raw.startswith("es") else "en"


def _bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value or "").encode("utf-8")


def _safe_token(value: Any) -> str:
    token = "".join(character.lower() if character.isalnum() else "-" for character in str(value or ""))
    return "-".join(part for part in token.split("-") if part) or "unknown"


def build_full_artifact_identity(
    *,
    assessment_id: Any,
    locale: Any,
    format: str,
    content: Any,
    report_version: Any,
) -> ArtifactIdentity:
    normalized_format = str(format).lower().strip()
    if normalized_format not in _REQUIRED_FORMATS:
        raise ValueError(f"Unsupported Full report format: {format}")
    normalized_locale = _locale(locale)
    payload = _bytes(content)
    digest = hashlib.sha256(payload).hexdigest()
    assessment_token = _safe_token(assessment_id)
    version_token = _safe_token(report_version)
    extension = "md" if normalized_format == "markdown" else normalized_format
    content_type = {
        "pdf": "application/pdf",
        "html": "text/html; charset=utf-8",
        "markdown": "text/markdown; charset=utf-8",
    }[normalized_format]
    artifact_id = f"full-{assessment_token}-{normalized_locale}-{normalized_format}-{digest[:16]}"
    filename = f"nico-full-{assessment_token}-{normalized_locale}-{version_token}.{extension}"
    return ArtifactIdentity(
        format=normalized_format,
        artifact_id=artifact_id,
        sha256=digest,
        byte_length=len(payload),
        content_type=content_type,
        filename=filename,
    )


def build_full_artifact_manifest(
    result: Mapping[str, Any],
    exports: Mapping[str, Any],
    *,
    assessment_id: Any,
    locale: Any = "en",
) -> dict[str, Any]:
    report_version = result.get("report_version") or result.get("version") or "unknown"
    identities: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for format in _REQUIRED_FORMATS:
        content = exports.get(format)
        if content is None:
            issues.append(f"Missing persisted Full {format} artifact.")
            continue
        identity = build_full_artifact_identity(
            assessment_id=assessment_id,
            locale=locale,
            format=format,
            content=content,
            report_version=report_version,
        )
        identities[format] = {
            "artifact_id": identity.artifact_id,
            "sha256": identity.sha256,
            "byte_length": identity.byte_length,
            "content_type": identity.content_type,
            "filename": identity.filename,
        }

    release = result.get("full_production_release") or {}
    release_allowed = bool(release.get("client_delivery_allowed"))
    manifest_ready = not issues and set(identities) == set(_REQUIRED_FORMATS)
    client_delivery_allowed = release_allowed and manifest_ready
    if release_allowed and not manifest_ready:
        issues.append("Release authority contradicted persisted artifact completeness.")

    return {
        "version": VERSION,
        "assessment_id": str(assessment_id),
        "locale": _locale(locale),
        "report_version": str(report_version),
        "required_formats": list(_REQUIRED_FORMATS),
        "artifacts": identities,
        "issues": issues,
        "persisted_artifacts_complete": manifest_ready,
        "client_delivery_allowed": client_delivery_allowed,
        "mobile_download_contract": {
            "content_disposition": "attachment",
            "stable_filename_required": True,
            "content_length_required": True,
            "sha256_required": True,
            "range_requests_allowed": True,
        },
    }


def validate_download_response(identity: Mapping[str, Any], headers: Mapping[str, Any]) -> tuple[str, ...]:
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    issues: list[str] = []
    expected_type = str(identity.get("content_type") or "")
    expected_length = str(identity.get("byte_length") or "")
    expected_filename = str(identity.get("filename") or "")
    if normalized.get("content-type") != expected_type:
        issues.append("Download content type does not match persisted artifact identity.")
    if normalized.get("content-length") != expected_length:
        issues.append("Download content length does not match persisted artifact identity.")
    disposition = normalized.get("content-disposition", "")
    if "attachment" not in disposition.lower() or expected_filename not in disposition:
        issues.append("Download content disposition does not expose the stable artifact filename.")
    if normalized.get("x-content-sha256") != str(identity.get("sha256") or ""):
        issues.append("Download checksum does not match persisted artifact identity.")
    return tuple(issues)


__all__ = [
    "ArtifactIdentity",
    "VERSION",
    "build_full_artifact_identity",
    "build_full_artifact_manifest",
    "validate_download_response",
]
