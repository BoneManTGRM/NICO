"""Exact-member, frozen review transport for the explicit v2 PDF composer.

Not installed in a route. The caller must establish final-surface acceptance and
persist the returned complete family and its trusted digest atomically.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any

from nico import ordinary_review_bundle_v2 as core
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256

SCHEMA = "nico.ordinary-report-files.v2"
MAX_FAMILY_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024
MANIFEST_NAME = "report-files-manifest.json"
EXPORT_NAMES = {
    "findings_csv": "findings.csv",
    "evidence_csv": "evidence.csv",
    "candidate_register_json": "candidate-register.json",
    "remediation_backlog_json": "remediation-backlog.json",
    "markdown_report": "report.md",
    "html_report": "report.html",
    "canonical_json": "canonical.json",
}


def _json_object(data: bytes) -> Any:
    def reject_constant(_value):
        raise ValueError("report_files_json_constant")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("report_files_duplicate_json_key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)


def _canonical_identity(data: bytes, identity: Mapping[str, str]) -> None:
    canonical = _json_object(data)
    if not isinstance(canonical, Mapping) or canonical_sha256(canonical) != identity["canonical_truth_sha256"]:
        raise ValueError("report_files_canonical_truth_mismatch")
    source = canonical.get("identity")
    if not isinstance(source, Mapping) or any(source.get(key) != identity[key] for key in
                                             ("run_id", "repository", "commit_sha", "report_language")):
        raise ValueError("report_files_canonical_identity_mismatch")
    if (canonical.get("client_delivery_allowed") is not False
            or canonical.get("human_review_required") is not True
            or canonical.get("report_finality") != "automated_draft"
            or canonical.get("approval_status") != "pending_human_approval"):
        raise ValueError("report_files_canonical_review_only")


def build_report_files(bundle: Mapping[str, Any], exports: Mapping[str, str], *,
                       expected_identity: Mapping[str, str], expected_bundle_manifest_sha256: str) -> dict[str, Any]:
    core.validate_review_bundle(bundle, expected_identity=expected_identity,
                                expected_manifest_sha256=expected_bundle_manifest_sha256)
    if set(exports) != set(EXPORT_NAMES):
        raise ValueError("report_files_export_population")
    identity = core._identity(expected_identity)
    files = []
    for file in bundle["files"]:
        files.append(("pdf_volume", file["filename"], base64.b64decode(file["pdf_base64"], validate=True)))
    for kind, filename in EXPORT_NAMES.items():
        value = exports[kind]
        if not isinstance(value, str) or not value or len(value.encode()) > MAX_TEXT_BYTES:
            raise ValueError("report_files_export_invalid")
        files.append((kind, filename, value.encode()))
    files.extend([
        ("bundle_manifest", "bundle-manifest.json", core._json(bundle["manifest"])),
        ("artifact_identity", "artifact-identity.json", core._json({
            "artifact_schema": SCHEMA, "identity": identity,
            "bundle_manifest_sha256": expected_bundle_manifest_sha256,
            "approval_status": "pending_human_approval", "client_delivery_allowed": False,
        })),
    ])
    manifest = {"artifact_schema": SCHEMA, "identity": identity,
                "bundle_manifest_sha256": expected_bundle_manifest_sha256,
                "approval_status": "pending_human_approval", "client_delivery_allowed": False,
                "artifacts": [{"artifact_type": kind, "filename": filename,
                               "sha256": core._sha(data), "size_bytes": len(data)}
                              for kind, filename, data in files]}
    family = {"artifact_schema": SCHEMA, "manifest": manifest, "manifest_sha256": core._sha(core._json(manifest)),
              "files": [{"filename": filename, "content_base64": base64.b64encode(data).decode("ascii")}
                        for _, filename, data in files]}
    validate_report_files(family, expected_identity=identity, expected_manifest_sha256=family["manifest_sha256"])
    return family


def _validated_members(family: Mapping[str, Any], expected_identity: Mapping[str, str], expected_manifest_sha256: str) -> dict[str, bytes]:
    identity = core._identity(expected_identity)
    if set(family) != {"artifact_schema", "manifest", "manifest_sha256", "files"} or family["artifact_schema"] != SCHEMA:
        raise ValueError("report_files_schema")
    manifest = family["manifest"]
    if set(manifest) != {"artifact_schema", "identity", "bundle_manifest_sha256", "approval_status", "client_delivery_allowed", "artifacts"}:
        raise ValueError("report_files_manifest_fields")
    if family["manifest_sha256"] != expected_manifest_sha256 or core._sha(core._json(manifest)) != expected_manifest_sha256:
        raise ValueError("report_files_manifest_digest")
    if manifest["artifact_schema"] != SCHEMA or manifest["identity"] != identity:
        raise ValueError("report_files_identity")
    if manifest["approval_status"] != "pending_human_approval" or manifest["client_delivery_allowed"] is not False:
        raise ValueError("report_files_review_only")
    entries, files = manifest["artifacts"], family["files"]
    if not isinstance(entries, list) or not isinstance(files, list) or len(entries) != len(files) or not 10 <= len(files) <= core.MAX_VOLUMES + 9:
        raise ValueError("report_files_population")
    volume_count = len(files) - 9
    names = [f"volume-{number:03d}-{identity['report_language']}.pdf" for number in range(1, volume_count + 1)]
    kinds = ["pdf_volume"] * volume_count + list(EXPORT_NAMES) + ["bundle_manifest", "artifact_identity"]
    names.extend([*EXPORT_NAMES.values(), "bundle-manifest.json", "artifact-identity.json"])
    members = {}
    size = text_size = 0
    for entry, file, filename, kind in zip(entries, files, names, kinds, strict=True):
        if set(entry) != {"artifact_type", "filename", "sha256", "size_bytes"} or set(file) != {"filename", "content_base64"}:
            raise ValueError("report_files_member_fields")
        if entry["filename"] != filename or file["filename"] != filename or entry["artifact_type"] != kind:
            raise ValueError("report_files_member_order")
        encoded = file["content_base64"]
        if not isinstance(encoded, str) or len(encoded) > ((MAX_FAMILY_BYTES + 2) // 3) * 4:
            raise ValueError("report_files_byte_limit")
        data = base64.b64decode(encoded, validate=True)
        size += len(data)
        if kind in EXPORT_NAMES:
            text_size += len(data)
        if size > MAX_FAMILY_BYTES or text_size > MAX_TEXT_BYTES:
            raise ValueError("report_files_byte_limit")
        if not data or type(entry["size_bytes"]) is not int or len(data) != entry["size_bytes"] or core._sha(data) != entry["sha256"]:
            raise ValueError("report_files_member_digest")
        members[filename] = data
    _canonical_identity(members["canonical.json"], identity)
    bundle_manifest = _json_object(members["bundle-manifest.json"])
    if core._sha(members["bundle-manifest.json"]) != manifest["bundle_manifest_sha256"]:
        raise ValueError("report_files_bundle_manifest_digest")
    bundle = {"manifest": bundle_manifest, "manifest_sha256": manifest["bundle_manifest_sha256"],
              "files": [{"filename": filename, "pdf_base64": base64.b64encode(members[filename]).decode("ascii")}
                        for filename in names[:volume_count]]}
    core.validate_review_bundle(bundle, expected_identity=identity, expected_manifest_sha256=manifest["bundle_manifest_sha256"])
    expected_metadata = {"artifact_schema": SCHEMA, "identity": identity,
                         "bundle_manifest_sha256": manifest["bundle_manifest_sha256"],
                         "approval_status": "pending_human_approval", "client_delivery_allowed": False}
    if members["artifact-identity.json"] != core._json(expected_metadata):
        raise ValueError("report_files_identity_metadata")
    members[MANIFEST_NAME] = core._json(manifest)
    if sum(map(len, members.values())) > MAX_FAMILY_BYTES:
        raise ValueError("report_files_byte_limit")
    return members


def validate_report_files(family: Mapping[str, Any], *, expected_identity: Mapping[str, str], expected_manifest_sha256: str) -> None:
    try:
        _validated_members(family, expected_identity, expected_manifest_sha256)
    except (KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ValueError("report_files_invalid_structure") from exc


def report_files_zip(family: Mapping[str, Any], *, expected_identity: Mapping[str, str], expected_manifest_sha256: str) -> bytes:
    members = _validated_members(family, expected_identity, expected_manifest_sha256)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, data in sorted(members.items()):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            archive.writestr(info, data)
    data = output.getvalue()
    if len(data) > MAX_FAMILY_BYTES:
        raise ValueError("report_files_byte_limit")
    return data


def read_report_files_zip(data: bytes, *, expected_identity: Mapping[str, str], expected_manifest_sha256: str) -> dict[str, Any]:
    """Verify a frozen archive against an independently retained family digest."""
    if not isinstance(data, bytes) or len(data) > MAX_FAMILY_BYTES:
        raise ValueError("report_files_byte_limit")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or not 11 <= len(names) <= core.MAX_VOLUMES + 10:
            raise ValueError("report_files_zip_population")
        if sum(item.file_size for item in infos) > MAX_FAMILY_BYTES or any(item.flag_bits & 1 for item in infos):
            raise ValueError("report_files_zip_limit")
        if MANIFEST_NAME not in names:
            raise ValueError("report_files_manifest_missing")
        raw = archive.read(MANIFEST_NAME)
        if core._sha(raw) != expected_manifest_sha256:
            raise ValueError("report_files_manifest_digest")
        manifest = _json_object(raw)
        expected_names = [entry["filename"] for entry in manifest["artifacts"]]
        if names != sorted([*expected_names, MANIFEST_NAME]):
            raise ValueError("report_files_zip_members")
        family = {"artifact_schema": SCHEMA, "manifest": manifest, "manifest_sha256": expected_manifest_sha256,
                  "files": [{"filename": filename, "content_base64": base64.b64encode(archive.read(filename)).decode("ascii")}
                            for filename in expected_names]}
    validate_report_files(family, expected_identity=expected_identity, expected_manifest_sha256=expected_manifest_sha256)
    return deepcopy(family)
