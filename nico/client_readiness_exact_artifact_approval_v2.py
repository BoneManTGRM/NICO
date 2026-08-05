from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico.client_readiness_exact_artifact_approval import (
    REQUIRED_ARTIFACTS,
    REQUIRED_GATES,
    VERSION,
    build_approval_subject as _build_v1_subject,
    evaluate_exact_artifact_approval,
    validate_exact_artifact_approval,
)

_REPORT_FILENAMES = {
    "markdown": "comprehensive-report.md",
    "html": "comprehensive-report.html",
    "pdf": "comprehensive-report.pdf",
    "json": "comprehensive-report.json",
}


def _manifest_mapping(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, Mapping):
        return {
            str(name): deepcopy(dict(record))
            for name, record in value.items()
            if isinstance(record, Mapping)
        }
    if isinstance(value, list):
        output: dict[str, dict[str, Any]] = {}
        for record in value:
            if not isinstance(record, Mapping):
                continue
            name = str(record.get("logical_name") or "").strip()
            if name:
                output[name] = deepcopy(dict(record))
        return output
    return {}


def build_approval_subject(
    *,
    identity: Mapping[str, Any],
    report_artifact_digests: Mapping[str, Any],
    artifact_manifest: Any,
    readiness_gates: Any,
) -> dict[str, Any]:
    """Derive generated report rows while requiring detached artifact records."""

    manifest = _manifest_mapping(artifact_manifest)
    for name, filename in _REPORT_FILENAMES.items():
        digest = report_artifact_digests.get(name)
        if not isinstance(digest, Mapping):
            continue
        manifest[name] = {
            "filename": str(manifest.get(name, {}).get("filename") or filename),
            "sha256": str(digest.get("sha256") or ""),
            "size_bytes": int(digest.get("size_bytes") or 0),
        }
    return _build_v1_subject(
        identity=identity,
        report_artifact_digests=report_artifact_digests,
        artifact_manifest=manifest,
        readiness_gates=readiness_gates,
    )


__all__ = [
    "REQUIRED_ARTIFACTS",
    "REQUIRED_GATES",
    "VERSION",
    "build_approval_subject",
    "evaluate_exact_artifact_approval",
    "validate_exact_artifact_approval",
]
