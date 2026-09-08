"""Transport retained artifacts without rendering, normalizing or approving them."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from typing import Any

_TEXT_ARTIFACTS = {
    "markdown_report": "markdown",
    "html_report": "html",
    "canonical_json": "canonical_json",
    "findings_csv": "findings_csv",
    "evidence_csv": "evidence_csv",
    "candidate_register_json": "candidate_register_json",
    "remediation_backlog_json": "remediation_backlog_json",
}
_RESERVED = {"evidence-manifest.json", "artifact-identity.json"}


def retained_report_zip(report: Mapping[str, Any]) -> bytes:
    """The caller must validate run ownership and canonical lifecycle first.

    These are the existing files identified by the detached manifest, not a new
    report projection. Refuse absent or mismatched members rather than rebuilding.
    """
    manifest_text = report.get("evidence_manifest_json")
    if not isinstance(manifest_text, str) or not manifest_text:
        raise ValueError("retained_manifest_missing")
    manifest_bytes = manifest_text.encode("utf-8")
    if hashlib.sha256(manifest_bytes).hexdigest() != report.get("evidence_manifest_sha256"):
        raise ValueError("retained_manifest_hash_mismatch")
    manifest = json.loads(manifest_text)
    entries = manifest.get("artifacts") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise ValueError("retained_manifest_entries_missing")
    members: dict[str, bytes] = {"evidence-manifest.json": manifest_bytes}
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("retained_manifest_entry_invalid")
        kind, name = entry.get("artifact_type"), entry.get("filename")
        if kind not in {*_TEXT_ARTIFACTS, "comprehensive_pdf"} or kind in seen:
            raise ValueError("retained_manifest_artifact_invalid")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,240}", name)
                or name in {".", ".."} or name in _RESERVED or name in members):
            raise ValueError("retained_manifest_filename_invalid")
        if kind == "comprehensive_pdf":
            data = base64.b64decode(str(report.get("pdf_base64") or ""), validate=True)
            if not data.startswith(b"%PDF"):
                raise ValueError("retained_pdf_invalid")
        else:
            value = report.get(_TEXT_ARTIFACTS[kind])
            if not isinstance(value, str) or not value:
                raise ValueError("retained_artifact_missing")
            data = value.encode("utf-8")
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise ValueError("retained_artifact_hash_mismatch")
        members[name] = data
        seen.add(kind)
    if seen != {*_TEXT_ARTIFACTS, "comprehensive_pdf"}:
        raise ValueError("retained_artifact_set_incomplete")
    identity = report.get("draft_artifact_identity")
    if not isinstance(identity, Mapping) or not identity:
        raise ValueError("retained_artifact_identity_missing")
    # This existing identity is returned outside the detached manifest, avoiding a
    # self-referential manifest hash. It does not assert fresh review or approval.
    members["artifact-identity.json"] = json.dumps(
        dict(identity), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    return output.getvalue()
