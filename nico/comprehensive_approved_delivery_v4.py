from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_approved_delivery_v1 import require_new_report_after_evidence_request
from nico.comprehensive_approved_delivery_v3 import (
    build_approved_delivery_package as build_v3,
    validate_approved_delivery_package as validate_v3,
)
from nico.comprehensive_client_delivery_contract_v1 import (
    CLIENT_FINAL_CLASSIFICATION,
    PRODUCT_NAME,
    VERSION as CONTRACT_VERSION,
    build_approval_receipt,
    canonical_sha256,
    engagement_binding,
    validate_approval_receipt,
    version_truth,
)
from nico.comprehensive_delivery_authorization_v1 import (
    validate_delivery_authorization,
)
from nico.comprehensive_authorized_report_v1 import (
    VERSION as AUTHORIZED_REPORT_VERSION,
    authorized_text,
    build_authorized_report_pdf,
)

VERSION = "nico.comprehensive_approved_delivery.v4"
_RECEIPT_PATH = "12_phase4_approval_receipt.json"
_MANIFEST_PATH = "11_evidence_manifest.json"
_REPORT_PATH = "01_nico_comprehensive_report.pdf"
_APPROVAL_RECORD_PATH = "15_approval_record.json"
_DELIVERY_AUTHORIZATION_PATH = "16_delivery_authorization.json"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _zip(entries: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            archive.writestr(info, entries[name])
    return buffer.getvalue()


def _review_metadata(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    value = manifest.get("review")
    return value if isinstance(value, Mapping) else {}


def _bounded_validation_error_code(exc: ValueError) -> str:
    raw = _text(exc).split(":", 1)[0]
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_"
        for char in raw
    )[:120]
    return normalized or "value_error"


def _receipt_validation_record(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Revalidate against the accepted edition's frozen history reference.

    Attaching the immutable package recomputes the enclosing record hash. That
    bookkeeping update must not invalidate the exact receipt it just enclosed;
    all material report, evidence, candidate, disposition, identity, and version
    fields are still rebuilt from the current record.
    """

    output = deepcopy(dict(record))
    binding = manifest.get("phase4_approval_binding")
    truth = (
        receipt.get("version_truth")
        if isinstance(receipt, Mapping)
        and isinstance(receipt.get("version_truth"), Mapping)
        else binding.get("version_truth")
        if isinstance(binding, Mapping)
        else None
    )
    if not isinstance(truth, Mapping):
        return output
    frozen = _text(truth.get("mutable_operational_history_reference"))
    if not frozen:
        return output
    output.pop("audit_chain_sha256", None)
    output["integrity_sha256"] = frozen
    return output


def bind_phase4_approval_manifest(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and preserve the exact immutable human-approved manifest."""

    output = deepcopy(dict(manifest))
    authorization_validation = validate_delivery_authorization(
        record,
        output,
        record.get("delivery_authorization"),
    )
    if authorization_validation["status"] != "valid":
        raise ValueError(
            "invalid_delivery_authorization:"
            + ",".join(authorization_validation["validation_errors"])
        )
    return output


def _enhance_delivery_archive(
    delivery: Mapping[str, Any],
    receipt: Mapping[str, Any],
    accepted_edition: Mapping[str, Any],
    delivery_authorization: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any], str, str, str]:
    try:
        source = base64.b64decode(_text(delivery.get("zip_base64")), validate=True)
    except Exception as exc:
        raise ValueError("phase4_delivery_zip_invalid") from exc
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(source), "r") as archive:
        for name in archive.namelist():
            if not name.endswith("/"):
                entries[name] = archive.read(name)
    approved_source_pdf = entries.get(_REPORT_PATH, b"")
    approved_source_sha = _sha256(approved_source_pdf)
    if approved_source_sha != _text(receipt.get("pdf_sha256")):
        raise ValueError("approved_source_pdf_receipt_mismatch")
    identity = {
        "run_id": receipt.get("assessment_run_id"),
        "repository": receipt.get("repository"),
        "commit_sha": receipt.get("assessed_repository_commit"),
    }
    authorized_pdf = build_authorized_report_pdf(
        approved_source_pdf,
        identity=identity,
        delivery_authorization=delivery_authorization,
        source_pdf_sha256=approved_source_sha,
    )
    authorized_pdf_sha = _sha256(authorized_pdf)
    entries[_REPORT_PATH] = authorized_pdf
    for name, content in list(entries.items()):
        if name == _REPORT_PATH:
            continue
        if name.casefold().endswith((".md", ".html", ".txt")):
            try:
                entries[name] = authorized_text(content.decode("utf-8")).encode("utf-8")
            except UnicodeDecodeError:
                pass
    receipt_bytes = _json_bytes(receipt)
    authorization_bytes = _json_bytes(delivery_authorization)
    entries[_APPROVAL_RECORD_PATH] = _json_bytes(accepted_edition)
    entries[_RECEIPT_PATH] = receipt_bytes
    entries[_DELIVERY_AUTHORIZATION_PATH] = authorization_bytes

    manifest = deepcopy(dict(delivery.get("manifest") or {}))
    artifacts = [
        deepcopy(dict(item))
        for item in manifest.get("artifacts") or []
        if isinstance(item, Mapping)
        and _text(item.get("path"))
        not in {_RECEIPT_PATH, _DELIVERY_AUTHORIZATION_PATH, _APPROVAL_RECORD_PATH}
    ]
    artifacts.append(
        {
            "path": _APPROVAL_RECORD_PATH,
            "kind": "immutable_human_approved_edition",
            "sha256": _sha256(entries[_APPROVAL_RECORD_PATH]),
            "size_bytes": len(entries[_APPROVAL_RECORD_PATH]),
        }
    )
    artifacts.append(
        {
            "path": _RECEIPT_PATH,
            "kind": "phase4_immutable_approval_receipt",
            "sha256": _sha256(receipt_bytes),
            "size_bytes": len(receipt_bytes),
        }
    )
    artifacts.append(
        {
            "path": _DELIVERY_AUTHORIZATION_PATH,
            "kind": "explicit_human_delivery_authorization_receipt",
            "sha256": _sha256(authorization_bytes),
            "size_bytes": len(authorization_bytes),
        }
    )
    artifacts.sort(key=lambda item: _text(item.get("path")))
    for item in artifacts:
        path = _text(item.get("path"))
        if path in entries:
            item["sha256"] = _sha256(entries[path])
            item["size_bytes"] = len(entries[path])
    manifest.update(
        {
            "artifact_schema": VERSION,
            "product_name": PRODUCT_NAME,
            "package_classification": CLIENT_FINAL_CLASSIFICATION,
            "repository": receipt.get("repository"),
            "run_id": receipt.get("assessment_run_id"),
            "assessed_repository_commit": receipt.get(
                "assessed_repository_commit"
            ),
            "evidence_ledger_id": receipt.get("evidence_ledger_id"),
            "client_identity": receipt.get("client_identity"),
            "project_identity": receipt.get("project_identity"),
            "customer_id": receipt.get("customer_id"),
            "client_id": receipt.get("client_id"),
            "project_id": receipt.get("project_id"),
            "accepted_edition_manifest_sha256": receipt.get(
                "accepted_edition_manifest_sha256"
            ),
            "phase4_approval_receipt_path": _RECEIPT_PATH,
            "phase4_approval_receipt_sha256": _sha256(receipt_bytes),
            "delivery_authorization_path": _DELIVERY_AUTHORIZATION_PATH,
            "delivery_authorization_sha256": delivery_authorization.get(
                "delivery_authorization_sha256"
            ),
            "artifacts": artifacts,
            "artifact_count": len(artifacts),
            "one_client_report": True,
            "client_pdf_count": 1,
            "human_review_required": True,
            "client_delivery_allowed": True,
            "client_facing_status": "authorized",
            "authorized_report_version": AUTHORIZED_REPORT_VERSION,
            "approved_source_pdf_sha256": approved_source_sha,
            "authorized_edition_pdf_sha256": authorized_pdf_sha,
        }
    )
    manifest_bytes = _json_bytes(manifest)
    entries[_MANIFEST_PATH] = manifest_bytes
    return (
        _zip(entries),
        manifest,
        _sha256(manifest_bytes),
        approved_source_sha,
        authorized_pdf_sha,
    )


def build_approved_delivery_package(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    bound = bind_phase4_approval_manifest(record, manifest)
    delivery_authorization = record.get("delivery_authorization")
    if not isinstance(delivery_authorization, Mapping):
        raise ValueError("delivery_authorization_required")
    delivery_projection = deepcopy(bound)
    delivery_projection["delivery_status"] = "approved_for_delivery"
    delivery_projection["client_delivery_allowed"] = True
    delivery_projection.pop("accepted_edition_manifest_sha256", None)
    delivery_projection["accepted_edition_manifest_sha256"] = canonical_sha256(
        delivery_projection
    )
    record_for_delivery = deepcopy(dict(record))
    record_for_delivery["accepted_edition"] = deepcopy(delivery_projection)
    delivery = build_v3(record_for_delivery, delivery_projection)
    review = _review_metadata(bound)
    receipt = build_approval_receipt(
        record,
        bound,
        reviewer=_text(review.get("reviewer")),
        reviewer_role=_text(review.get("reviewer_role")),
        decision=_text(review.get("decision")),
        decided_at=_text(review.get("decided_at")),
        decision_reason=_text(review.get("reason")),
        authorization_basis=_text(review.get("authorization_basis"))
        or "protected_admin_write_and_explicit_review_authorization",
    )
    (
        archive,
        delivery_manifest,
        evidence_manifest_sha,
        approved_source_pdf_sha,
        authorized_edition_pdf_sha,
    ) = _enhance_delivery_archive(
        delivery,
        receipt,
        bound,
        delivery_authorization,
    )
    certificate = deepcopy(dict(delivery.get("certificate") or {}))
    certificate.update(
        {
            "artifact_schema": VERSION,
            "client_identity": receipt["client_identity"],
            "project_identity": receipt["project_identity"],
            "customer_id": receipt["customer_id"],
            "client_id": receipt["client_id"],
            "project_id": receipt["project_id"],
            "assessment_run_id": receipt["assessment_run_id"],
            "repository": receipt["repository"],
            "assessed_repository_commit": receipt["assessed_repository_commit"],
            "approval_record_id": receipt["review"]["approval_record_id"],
            "reviewer_identity": receipt["review"]["reviewer_identity"],
            "reviewer_role": receipt["review"]["reviewer_role"],
            "authorization_basis": receipt["review"]["authorization_basis"],
            "delivery_authorization_id": delivery_authorization.get(
                "delivery_authorization_id"
            ),
            "delivery_authorizer_identity": delivery_authorization.get(
                "authorizer_identity"
            ),
            "delivery_authorizer_role": delivery_authorization.get(
                "authorizer_role"
            ),
            "delivery_authorized_at": delivery_authorization.get("authorized_at"),
            "delivery_authorization_reason": delivery_authorization.get(
                "authorization_reason"
            ),
            "delivery_authorization_sha256": delivery_authorization.get(
                "delivery_authorization_sha256"
            ),
            "residual_risk_decision": receipt["review"]["residual_risk_decision"],
            "pdf_sha256": receipt["pdf_sha256"],
            "canonical_json_sha256": receipt["canonical_json_sha256"],
            "evidence_manifest_sha256": evidence_manifest_sha,
            "phase4_approval_receipt_sha256": receipt["approval_receipt_sha256"],
            "candidate_register_sha256": receipt["candidate_register_sha256"],
            "candidate_disposition_state_sha256": receipt["candidate_disposition_state_sha256"],
            "accepted_edition_manifest_sha256": receipt[
                "accepted_edition_manifest_sha256"
            ],
            "version_truth": deepcopy(receipt["version_truth"]),
            "package_classification": CLIENT_FINAL_CLASSIFICATION,
            "one_client_report": True,
            "client_pdf_count": 1,
            "human_review_required": True,
            "client_delivery_allowed": True,
            "client_facing_status": "authorized",
            "authorized_report_version": AUTHORIZED_REPORT_VERSION,
            "approved_source_pdf_sha256": approved_source_pdf_sha,
            "authorized_edition_pdf_sha256": authorized_edition_pdf_sha,
            "authorized_edition_created": True,
            "approved_report_pdf_preserved_exactly": False,
            "delivery_authorization_certificate_page_prepended": True,
        }
    )
    certificate["delivery_package_sha256"] = _sha256(archive)
    certificate["delivery_package_size_bytes"] = len(archive)
    certificate.pop("delivery_authorization_certificate_sha256", None)
    certificate["delivery_authorization_certificate_sha256"] = canonical_sha256(certificate)
    return {
        **dict(delivery),
        "artifact_schema": VERSION,
        "zip_base64": base64.b64encode(archive).decode("ascii"),
        "zip_sha256": _sha256(archive),
        "zip_size_bytes": len(archive),
        "artifact_count": len(delivery_manifest.get("artifacts") or []),
        "manifest": delivery_manifest,
        "certificate": certificate,
        "phase4_approval_receipt": receipt,
        "phase4_approval_receipt_sha256": receipt["approval_receipt_sha256"],
        "product_name": PRODUCT_NAME,
        "package_classification": CLIENT_FINAL_CLASSIFICATION,
        "one_client_report": True,
        "client_pdf_count": 1,
        "human_review_required": True,
        "client_delivery_allowed": True,
        "client_facing_status": "authorized",
        "authorized_report_version": AUTHORIZED_REPORT_VERSION,
        "approved_source_pdf_sha256": approved_source_pdf_sha,
        "authorized_edition_pdf_sha256": authorized_edition_pdf_sha,
        "authorized_edition_created": True,
        "approved_report_pdf_preserved_exactly": False,
        "delivery_authorization_certificate_page_prepended": True,
    }


def validate_approved_delivery_package(
    record: Mapping[str, Any],
    package: Any,
) -> dict[str, Any]:
    try:
        result = dict(validate_v3(record, package))
    except ValueError as exc:
        result = {
            "status": "invalid",
            "validation_errors": [
                "phase4_inherited_validation_failed:"
                + _bounded_validation_error_code(exc)
            ],
            "client_delivery_allowed": False,
        }
    errors = set(str(item) for item in result.get("validation_errors") or [])
    if not isinstance(package, Mapping):
        errors.add("phase4_delivery_package_must_be_mapping")
        return {
            **result,
            "status": "invalid",
            "validation_errors": sorted(errors),
            "client_delivery_allowed": False,
        }
    manifest = record.get("accepted_edition")
    receipt = package.get("phase4_approval_receipt")
    delivery_authorization = record.get("delivery_authorization")
    if not isinstance(manifest, Mapping):
        errors.add("phase4_accepted_edition_missing")
    if not isinstance(receipt, Mapping):
        errors.add("phase4_approval_receipt_missing")
    if isinstance(manifest, Mapping) and isinstance(receipt, Mapping):
        authorization_validation = validate_delivery_authorization(
            record,
            manifest,
            delivery_authorization,
        )
        errors.update(authorization_validation.get("validation_errors") or [])
        validation = validate_approval_receipt(
            _receipt_validation_record(record, manifest, receipt),
            manifest,
            receipt,
        )
        errors.update(validation.get("validation_errors") or [])
        receipt_hash = _text(receipt.get("approval_receipt_sha256"))
        if receipt_hash != _text(package.get("phase4_approval_receipt_sha256")):
            errors.add("phase4_receipt_package_hash_mismatch")
    if _text(package.get("product_name")) != PRODUCT_NAME:
        errors.add("phase4_wrong_product")
    if _text(package.get("package_classification")) != CLIENT_FINAL_CLASSIFICATION:
        errors.add("phase4_internal_or_test_package_blocked")
    if package.get("one_client_report") is not True or int(package.get("client_pdf_count") or 0) != 1:
        errors.add("phase4_one_report_rule_violated")
    if package.get("human_review_required") is not True:
        errors.add("phase4_human_review_boundary_missing")
    if package.get("client_delivery_allowed") is not True:
        errors.add("phase4_delivery_authorization_missing")
    if _text(package.get("final_human_approval_status")) != "approved":
        errors.add("phase4_final_approval_status_invalid")
    if _text(package.get("client_delivery_authorization_status")) != "authorized":
        errors.add("phase4_delivery_status_invalid")
    if package.get("authorized_edition_created") is not True:
        errors.add("phase4_authorized_edition_missing")
    if not _text(package.get("approved_source_pdf_sha256")):
        errors.add("phase4_approved_source_pdf_hash_missing")
    if package.get("delivery_authorization_certificate_page_prepended") is not True:
        errors.add("phase4_delivery_authorization_certificate_missing")
    if _text(package.get("client_facing_status")) != "authorized":
        errors.add("phase4_client_facing_status_invalid")
    if package.get("approval_certificate_separate_json") is not True:
        errors.add("phase4_separate_approval_certificate_missing")

    archive_manifest: Mapping[str, Any] | None = None
    archive_manifest_sha = ""
    archive_sha = ""
    try:
        archive_bytes = base64.b64decode(_text(package.get("zip_base64")), validate=True)
        archive_sha = _sha256(archive_bytes)
        if archive_sha != _text(package.get("zip_sha256")):
            errors.add("phase4_delivery_archive_hash_mismatch")
        if len(archive_bytes) != int(package.get("zip_size_bytes") or -1):
            errors.add("phase4_delivery_archive_size_mismatch")
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                errors.add("phase4_delivery_archive_duplicate_path")
            pdfs = [name for name in names if name.casefold().endswith(".pdf")]
            if len(pdfs) != 1:
                errors.add("phase4_one_report_rule_violated")
            elif isinstance(manifest, Mapping) and isinstance(receipt, Mapping):
                delivered_pdf_sha = _sha256(archive.read(pdfs[0]))
                if delivered_pdf_sha != _text(package.get("authorized_edition_pdf_sha256")):
                    errors.add("phase4_authorized_edition_pdf_mismatch")
                if pdfs[0] != _REPORT_PATH:
                    errors.add("phase4_client_report_path_mismatch")
                if _text(package.get("approved_source_pdf_sha256")) != _text(
                    receipt.get("pdf_sha256")
                ):
                    errors.add("phase4_approved_source_pdf_receipt_mismatch")
            if _APPROVAL_RECORD_PATH not in names:
                errors.add("phase4_approval_record_missing")
            elif isinstance(manifest, Mapping) and archive.read(
                _APPROVAL_RECORD_PATH
            ) != _json_bytes(manifest):
                errors.add("phase4_approval_record_accepted_edition_mismatch")
            if _DELIVERY_AUTHORIZATION_PATH not in names:
                errors.add("phase4_delivery_authorization_receipt_missing")
            elif isinstance(delivery_authorization, Mapping) and archive.read(
                _DELIVERY_AUTHORIZATION_PATH
            ) != _json_bytes(delivery_authorization):
                errors.add("phase4_delivery_authorization_receipt_mismatch")
            if _RECEIPT_PATH not in names:
                errors.add("phase4_receipt_not_in_immutable_package")
            elif isinstance(receipt, Mapping):
                if archive.read(_RECEIPT_PATH) != _json_bytes(receipt):
                    errors.add("phase4_receipt_archive_mismatch")
            if _MANIFEST_PATH not in names:
                errors.add("phase4_evidence_manifest_missing")
            else:
                manifest_bytes = archive.read(_MANIFEST_PATH)
                archive_manifest_sha = _sha256(manifest_bytes)
                try:
                    parsed_manifest = json.loads(manifest_bytes.decode("utf-8"))
                    if isinstance(parsed_manifest, Mapping):
                        archive_manifest = parsed_manifest
                    else:
                        errors.add("phase4_evidence_manifest_invalid")
                except (UnicodeDecodeError, ValueError):
                    errors.add("phase4_evidence_manifest_invalid")
                in_memory_manifest = package.get("manifest")
                if not isinstance(in_memory_manifest, Mapping) or _json_bytes(
                    in_memory_manifest
                ) != manifest_bytes:
                    errors.add("phase4_evidence_manifest_archive_mismatch")
                certificate = package.get("certificate")
                if not isinstance(certificate, Mapping) or _text(
                    certificate.get("evidence_manifest_sha256")
                ) != archive_manifest_sha:
                    errors.add("phase4_evidence_manifest_hash_mismatch")
            if isinstance(archive_manifest, Mapping):
                identity = (
                    record.get("identity")
                    if isinstance(record.get("identity"), Mapping)
                    else {}
                )
                expected_manifest_values = {
                    "product_name": PRODUCT_NAME,
                    "package_classification": CLIENT_FINAL_CLASSIFICATION,
                    "repository": receipt.get("repository")
                    if isinstance(receipt, Mapping)
                    else "",
                    "run_id": receipt.get("assessment_run_id")
                    if isinstance(receipt, Mapping)
                    else "",
                    "assessed_repository_commit": receipt.get(
                        "assessed_repository_commit"
                    )
                    if isinstance(receipt, Mapping)
                    else "",
                    "evidence_ledger_id": receipt.get("evidence_ledger_id")
                    if isinstance(receipt, Mapping)
                    else "",
                    "client_identity": receipt.get("client_identity")
                    if isinstance(receipt, Mapping)
                    else "",
                    "project_identity": receipt.get("project_identity")
                    if isinstance(receipt, Mapping)
                    else "",
                    "customer_id": receipt.get("customer_id")
                    if isinstance(receipt, Mapping)
                    else "",
                    "client_id": receipt.get("client_id")
                    if isinstance(receipt, Mapping)
                    else "",
                    "project_id": receipt.get("project_id")
                    if isinstance(receipt, Mapping)
                    else "",
                    "accepted_edition_manifest_sha256": receipt.get(
                        "accepted_edition_manifest_sha256"
                    )
                    if isinstance(receipt, Mapping)
                    else "",
                    "report_language": identity.get("report_language"),
                }
                for key, expected in expected_manifest_values.items():
                    if _text(archive_manifest.get(key)) != _text(expected):
                        errors.add(f"phase4_evidence_manifest_{key}_mismatch")
                if _text(archive_manifest.get("delivery_status")) != "approved_for_delivery":
                    errors.add("phase4_evidence_manifest_delivery_status_invalid")
                if _text(archive_manifest.get("client_facing_status")) != "authorized":
                    errors.add("phase4_evidence_manifest_client_status_invalid")
                if _text(archive_manifest.get("approved_source_pdf_sha256")) != _text(
                    package.get("approved_source_pdf_sha256")
                ):
                    errors.add("phase4_evidence_manifest_source_pdf_hash_mismatch")
                if _text(archive_manifest.get("authorized_edition_pdf_sha256")) != _text(
                    package.get("authorized_edition_pdf_sha256")
                ):
                    errors.add("phase4_evidence_manifest_authorized_pdf_hash_mismatch")
                if archive_manifest.get("human_review_required") is not True:
                    errors.add("phase4_evidence_manifest_human_review_boundary_missing")
                if archive_manifest.get("client_delivery_allowed") is not True:
                    errors.add("phase4_evidence_manifest_delivery_authorization_missing")
                if archive_manifest.get("one_client_report") is not True or int(
                    archive_manifest.get("client_pdf_count") or 0
                ) != 1:
                    errors.add("phase4_evidence_manifest_one_report_rule_violated")
                artifact_rows = [
                    item
                    for item in archive_manifest.get("artifacts") or []
                    if isinstance(item, Mapping)
                ]
                declared_paths = [_text(item.get("path")) for item in artifact_rows]
                archived_paths = sorted(name for name in names if name != _MANIFEST_PATH)
                if sorted(declared_paths) != archived_paths:
                    errors.add("phase4_evidence_manifest_artifact_set_mismatch")
                if len(declared_paths) != len(set(declared_paths)):
                    errors.add("phase4_evidence_manifest_duplicate_path")
                for item in artifact_rows:
                    path = _text(item.get("path"))
                    if path not in names:
                        continue
                    content = archive.read(path)
                    if _text(item.get("sha256")) != _sha256(content):
                        errors.add("phase4_evidence_manifest_artifact_hash_mismatch")
                    if item.get("size_bytes") != len(content):
                        errors.add("phase4_evidence_manifest_artifact_size_mismatch")
                declared_count = int(archive_manifest.get("artifact_count") or -1)
                if declared_count != len(artifact_rows) or int(
                    package.get("artifact_count") or -1
                ) != len(artifact_rows):
                    errors.add("phase4_evidence_manifest_artifact_count_mismatch")
                if _text(archive_manifest.get("phase4_approval_receipt_path")) != _RECEIPT_PATH:
                    errors.add("phase4_evidence_manifest_receipt_path_mismatch")
                receipt_bytes = archive.read(_RECEIPT_PATH) if _RECEIPT_PATH in names else b""
                if _text(archive_manifest.get("phase4_approval_receipt_sha256")) != _sha256(
                    receipt_bytes
                ):
                    errors.add("phase4_evidence_manifest_receipt_hash_mismatch")
                if _text(archive_manifest.get("delivery_authorization_path")) != (
                    _DELIVERY_AUTHORIZATION_PATH
                ):
                    errors.add(
                        "phase4_evidence_manifest_delivery_authorization_path_mismatch"
                    )
                expected_authorization_sha = (
                    _text(delivery_authorization.get("delivery_authorization_sha256"))
                    if isinstance(delivery_authorization, Mapping)
                    else ""
                )
                if _text(
                    archive_manifest.get("delivery_authorization_sha256")
                ) != expected_authorization_sha:
                    errors.add(
                        "phase4_evidence_manifest_delivery_authorization_hash_mismatch"
                    )
    except Exception:
        errors.add("phase4_delivery_archive_invalid")

    certificate = package.get("certificate")
    binding = engagement_binding(record)
    if not isinstance(certificate, Mapping):
        errors.add("phase4_delivery_certificate_missing")
    else:
        expected_certificate: dict[str, Any] = {
            "client_identity": binding["client_identity"],
            "project_identity": binding["project_identity"],
            "customer_id": binding["customer_id"],
            "client_id": binding["client_id"],
            "project_id": binding["project_id"],
            "package_classification": CLIENT_FINAL_CLASSIFICATION,
            "client_facing_status": "authorized",
            "authorized_report_version": AUTHORIZED_REPORT_VERSION,
            "approved_source_pdf_sha256": package.get(
                "approved_source_pdf_sha256"
            ),
            "authorized_edition_pdf_sha256": package.get(
                "authorized_edition_pdf_sha256"
            ),
        }
        delivery_authorization = (
            record.get("delivery_authorization")
            if isinstance(record.get("delivery_authorization"), Mapping)
            else {}
        )
        expected_certificate.update(
            {
                "delivery_authorization_id": delivery_authorization.get(
                    "delivery_authorization_id"
                ),
                "delivery_authorizer_identity": delivery_authorization.get(
                    "authorizer_identity"
                ),
                "delivery_authorizer_role": delivery_authorization.get(
                    "authorizer_role"
                ),
                "delivery_authorized_at": delivery_authorization.get(
                    "authorized_at"
                ),
                "delivery_authorization_reason": delivery_authorization.get(
                    "authorization_reason"
                ),
                "delivery_authorization_sha256": delivery_authorization.get(
                    "delivery_authorization_sha256"
                ),
            }
        )
        if isinstance(receipt, Mapping):
            receipt_review = receipt.get("review")
            receipt_review = receipt_review if isinstance(receipt_review, Mapping) else {}
            expected_certificate.update(
                {
                    "assessment_run_id": receipt.get("assessment_run_id"),
                    "run_id": receipt.get("assessment_run_id"),
                    "repository": receipt.get("repository"),
                    "assessed_repository_commit": receipt.get("assessed_repository_commit"),
                    "commit_sha": receipt.get("assessed_repository_commit"),
                    "approval_record_id": receipt_review.get("approval_record_id"),
                    "reviewer_identity": receipt_review.get("reviewer_identity"),
                    "reviewer_role": receipt_review.get("reviewer_role"),
                    "authorization_basis": receipt_review.get("authorization_basis"),
                    "residual_risk_decision": receipt_review.get("residual_risk_decision"),
                    "pdf_sha256": receipt.get("pdf_sha256"),
                    "canonical_json_sha256": receipt.get("canonical_json_sha256"),
                    "phase4_approval_receipt_sha256": receipt.get("approval_receipt_sha256"),
                    "candidate_register_sha256": receipt.get("candidate_register_sha256"),
                    "candidate_disposition_state_sha256": receipt.get(
                        "candidate_disposition_state_sha256"
                    ),
                    "accepted_edition_manifest_sha256": receipt.get(
                        "accepted_edition_manifest_sha256"
                    ),
                    "approval_certificate_sha256": (
                        manifest.get("review", {}).get(
                            "approval_certificate_sha256"
                        )
                        if isinstance(manifest, Mapping)
                        and isinstance(manifest.get("review"), Mapping)
                        else ""
                    ),
                    "approved_at": receipt_review.get("review_timestamp"),
                    "version_truth": receipt.get("version_truth"),
                }
            )
        for key, expected in expected_certificate.items():
            if isinstance(expected, (Mapping, list)):
                matches = certificate.get(key) == expected
            else:
                matches = _text(certificate.get(key)) == _text(expected)
            if not matches:
                errors.add(f"phase4_{key}_mismatch")
        for key, expected in (
            ("evidence_manifest_sha256", archive_manifest_sha),
            ("delivery_package_sha256", archive_sha),
            ("delivery_package_size_bytes", package.get("zip_size_bytes")),
        ):
            if _text(certificate.get(key)) != _text(expected):
                errors.add(f"phase4_{key}_mismatch")
        if certificate.get("one_client_report") is not True or int(
            certificate.get("client_pdf_count") or 0
        ) != 1:
            errors.add("phase4_certificate_one_report_rule_violated")
        if certificate.get("human_review_required") is not True:
            errors.add("phase4_certificate_human_review_boundary_missing")
        if certificate.get("client_delivery_allowed") is not True:
            errors.add("phase4_certificate_delivery_authorization_missing")
        if certificate.get("authorized_edition_created") is not True:
            errors.add("phase4_certificate_authorized_edition_missing")
        if _text(certificate.get("approved_source_pdf_sha256")) != _text(
            package.get("approved_source_pdf_sha256")
        ):
            errors.add("phase4_certificate_approved_source_hash_mismatch")
        if certificate.get("delivery_authorization_certificate_page_prepended") is not True:
            errors.add("phase4_certificate_authorization_page_missing")
        if certificate.get("approval_certificate_page_appended") is not False:
            errors.add("phase4_certificate_approved_pdf_was_mutated")
        if certificate.get("approved_report_pdf_preserved_exactly") is not False:
            errors.add("phase4_certificate_authorized_pdf_truth_invalid")
        if certificate.get("approval_certificate_separate_json") is not True:
            errors.add("phase4_certificate_separate_approval_missing")
        if certificate.get("report_analysis_regenerated_during_delivery_packaging") is not False:
            errors.add("phase4_certificate_report_regeneration_invalid")
        candidate = deepcopy(dict(certificate))
        supplied_hash = _text(candidate.pop("delivery_authorization_certificate_sha256", ""))
        if supplied_hash != canonical_sha256(candidate):
            errors.add("phase4_delivery_certificate_hash_mismatch")
        if _text(certificate.get("delivery_package_sha256")) != _text(package.get("zip_sha256")):
            errors.add("phase4_certificate_archive_binding_mismatch")

    return {
        **result,
        "artifact_schema": VERSION,
        "status": "valid" if not errors else "invalid",
        "validation_errors": sorted(errors),
        "one_client_report": True,
        "client_delivery_allowed": not errors,
    }


def attach_approved_delivery_package(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    updated = deepcopy(dict(record))
    if _text(_review_metadata(manifest).get("decision")).casefold() != "approved":
        updated.pop("approved_delivery_package", None)
        updated["client_delivery_allowed"] = False
        return updated
    require_new_report_after_evidence_request(updated, manifest)
    bound = bind_phase4_approval_manifest(updated, manifest)
    delivery = build_approved_delivery_package(updated, bound)
    updated["approved_delivery_package"] = delivery
    updated["client_delivery_allowed"] = True
    context = deepcopy(dict(updated.get("review_context") or {}))
    context.update(
        {
            "phase4_approval_receipt_sha256": delivery["phase4_approval_receipt_sha256"],
            "delivery_authorization_certificate_sha256": delivery["certificate"][
                "delivery_authorization_certificate_sha256"
            ],
            "client_identity": delivery["certificate"]["client_identity"],
            "project_identity": delivery["certificate"]["project_identity"],
            "package_classification": CLIENT_FINAL_CLASSIFICATION,
            "one_client_report": True,
            "client_pdf_count": 1,
            "delivery_authorization_id": updated["delivery_authorization"][
                "delivery_authorization_id"
            ],
            "delivery_authorization_sha256": updated["delivery_authorization"][
                "delivery_authorization_sha256"
            ],
            "human_review_required": True,
            "client_delivery_allowed": True,
        }
    )
    updated["review_context"] = context
    validation = validate_approved_delivery_package(updated, delivery)
    if validation["status"] != "valid":
        raise ValueError(
            "invalid_phase4_approved_delivery_package:"
            + ",".join(validation["validation_errors"])
        )
    from nico.comprehensive_run_record import _record_hash

    updated["integrity_sha256"] = _record_hash(updated)
    return updated


__all__ = [
    "VERSION",
    "attach_approved_delivery_package",
    "bind_phase4_approval_manifest",
    "build_approved_delivery_package",
    "validate_approved_delivery_package",
]
