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

VERSION = "nico.comprehensive_approved_delivery.v4"
_RECEIPT_PATH = "12_phase4_approval_receipt.json"
_MANIFEST_PATH = "11_evidence_manifest.json"


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
) -> dict[str, Any]:
    """Revalidate against the accepted edition's frozen history reference.

    Attaching the immutable package recomputes the enclosing record hash. That
    bookkeeping update must not invalidate the exact receipt it just enclosed;
    all material report, evidence, candidate, disposition, identity, and version
    fields are still rebuilt from the current record.
    """

    output = deepcopy(dict(record))
    binding = manifest.get("phase4_approval_binding")
    if not isinstance(binding, Mapping):
        return output
    truth = binding.get("version_truth")
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
    """Retain client/project/authorization/version truth without changing report bytes."""

    output = deepcopy(dict(manifest))
    review = deepcopy(dict(_review_metadata(output)))
    binding = engagement_binding(record)
    decision = _text(review.get("decision")).casefold()
    reviewer = _text(review.get("reviewer"))
    reviewer_role = _text(review.get("reviewer_role"))
    reason = _text(review.get("reason"))
    decided_at = _text(review.get("decided_at"))
    if decision == "approved":
        from nico.comprehensive_client_delivery_contract_v1 import reviewer_binding

        human = reviewer_binding(
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision=decision,
            decided_at=decided_at,
            decision_reason=reason,
        )
    else:
        human = {
            "reviewer_identity": reviewer,
            "reviewer_role": reviewer_role,
            "authorization_basis": "protected_admin_write_and_explicit_review_authorization",
            "review_decision": decision,
            "review_timestamp": decided_at,
            "residual_risk_decision": "not_accepted",
            "reviewer_notes": reason,
            "human_action_required": True,
            "automation_may_not_approve": True,
            "approval_record_id": "approval_" + canonical_sha256(review)[:24],
        }
    phase4_binding = {
        "artifact_schema": CONTRACT_VERSION,
        "product_name": PRODUCT_NAME,
        "package_classification": CLIENT_FINAL_CLASSIFICATION,
        "client_identity": binding["client_identity"],
        "project_identity": binding["project_identity"],
        "customer_id": binding["customer_id"],
        "client_id": binding["client_id"],
        "project_id": binding["project_id"],
        "authorized_scope": binding["authorized_scope"],
        "read_only_access_method": binding["access_method"],
        "review": human,
        "version_truth": version_truth(record),
        "one_product": PRODUCT_NAME,
        "one_client_report": True,
        "human_review_required": True,
        "client_delivery_allowed": decision == "approved" and output.get("accepted_edition") is True,
    }
    phase4_binding["binding_sha256"] = canonical_sha256(phase4_binding)
    output.update(
        {
            "phase4_approval_binding": phase4_binding,
            "client_identity": binding["client_identity"],
            "project_identity": binding["project_identity"],
            "customer_id": binding["customer_id"],
            "client_id": binding["client_id"],
            "project_id": binding["project_id"],
            "package_classification": CLIENT_FINAL_CLASSIFICATION,
            "one_product": PRODUCT_NAME,
            "one_client_report": True,
        }
    )
    review.pop("approval_certificate_sha256", None)
    review["authorization_basis"] = human["authorization_basis"]
    review["residual_risk_decision"] = human["residual_risk_decision"]
    review["approval_record_id"] = human["approval_record_id"]
    review["approval_certificate_sha256"] = canonical_sha256(review)
    output["review"] = review
    output.pop("accepted_edition_manifest_sha256", None)
    output["accepted_edition_manifest_sha256"] = canonical_sha256(output)
    return output


def _enhance_delivery_archive(
    delivery: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any], str]:
    try:
        source = base64.b64decode(_text(delivery.get("zip_base64")), validate=True)
    except Exception as exc:
        raise ValueError("phase4_delivery_zip_invalid") from exc
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(source), "r") as archive:
        for name in archive.namelist():
            if not name.endswith("/"):
                entries[name] = archive.read(name)
    receipt_bytes = _json_bytes(receipt)
    entries[_RECEIPT_PATH] = receipt_bytes

    manifest = deepcopy(dict(delivery.get("manifest") or {}))
    artifacts = [
        deepcopy(dict(item))
        for item in manifest.get("artifacts") or []
        if isinstance(item, Mapping) and _text(item.get("path")) != _RECEIPT_PATH
    ]
    artifacts.append(
        {
            "path": _RECEIPT_PATH,
            "kind": "phase4_immutable_approval_receipt",
            "sha256": _sha256(receipt_bytes),
            "size_bytes": len(receipt_bytes),
        }
    )
    artifacts.sort(key=lambda item: _text(item.get("path")))
    manifest.update(
        {
            "artifact_schema": VERSION,
            "product_name": PRODUCT_NAME,
            "package_classification": CLIENT_FINAL_CLASSIFICATION,
            "phase4_approval_receipt_path": _RECEIPT_PATH,
            "phase4_approval_receipt_sha256": _sha256(receipt_bytes),
            "artifacts": artifacts,
            "artifact_count": len(artifacts),
            "one_client_report": True,
            "client_pdf_count": 1,
            "human_review_required": True,
            "client_delivery_allowed": True,
        }
    )
    manifest_bytes = _json_bytes(manifest)
    entries[_MANIFEST_PATH] = manifest_bytes
    return _zip(entries), manifest, _sha256(manifest_bytes)


def build_approved_delivery_package(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    bound = bind_phase4_approval_manifest(record, manifest)
    record_for_delivery = deepcopy(dict(record))
    record_for_delivery["accepted_edition"] = deepcopy(bound)
    delivery = build_v3(record_for_delivery, bound)
    review = _review_metadata(bound)
    receipt = build_approval_receipt(
        record_for_delivery,
        bound,
        reviewer=_text(review.get("reviewer")),
        reviewer_role=_text(review.get("reviewer_role")),
        decision=_text(review.get("decision")),
        decided_at=_text(review.get("decided_at")),
        decision_reason=_text(review.get("reason")),
        authorization_basis=_text(review.get("authorization_basis"))
        or "protected_admin_write_and_explicit_review_authorization",
    )
    archive, delivery_manifest, evidence_manifest_sha = _enhance_delivery_archive(delivery, receipt)
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
            "residual_risk_decision": receipt["review"]["residual_risk_decision"],
            "pdf_sha256": receipt["pdf_sha256"],
            "canonical_json_sha256": receipt["canonical_json_sha256"],
            "evidence_manifest_sha256": evidence_manifest_sha,
            "phase4_approval_receipt_sha256": receipt["approval_receipt_sha256"],
            "candidate_register_sha256": receipt["candidate_register_sha256"],
            "candidate_disposition_state_sha256": receipt["candidate_disposition_state_sha256"],
            "version_truth": deepcopy(receipt["version_truth"]),
            "package_classification": CLIENT_FINAL_CLASSIFICATION,
            "one_client_report": True,
            "client_pdf_count": 1,
            "human_review_required": True,
            "client_delivery_allowed": True,
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
    if not isinstance(manifest, Mapping):
        errors.add("phase4_accepted_edition_missing")
    if not isinstance(receipt, Mapping):
        errors.add("phase4_approval_receipt_missing")
    if isinstance(manifest, Mapping) and isinstance(receipt, Mapping):
        validation = validate_approval_receipt(
            _receipt_validation_record(record, manifest),
            manifest,
            receipt,
        )
        errors.update(validation.get("validation_errors") or [])
    if _text(package.get("product_name")) != PRODUCT_NAME:
        errors.add("phase4_wrong_product")
    if _text(package.get("package_classification")) != CLIENT_FINAL_CLASSIFICATION:
        errors.add("phase4_internal_or_test_package_blocked")
    if package.get("one_client_report") is not True or int(package.get("client_pdf_count") or 0) != 1:
        errors.add("phase4_one_report_rule_violated")

    try:
        archive_bytes = base64.b64decode(_text(package.get("zip_base64")), validate=True)
        if _sha256(archive_bytes) != _text(package.get("zip_sha256")):
            errors.add("phase4_delivery_archive_hash_mismatch")
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            names = archive.namelist()
            pdfs = [name for name in names if name.casefold().endswith(".pdf")]
            if len(pdfs) != 1:
                errors.add("phase4_one_report_rule_violated")
            if _RECEIPT_PATH not in names:
                errors.add("phase4_receipt_not_in_immutable_package")
            elif isinstance(receipt, Mapping):
                if archive.read(_RECEIPT_PATH) != _json_bytes(receipt):
                    errors.add("phase4_receipt_archive_mismatch")
            if _MANIFEST_PATH not in names:
                errors.add("phase4_evidence_manifest_missing")
            else:
                manifest_sha = _sha256(archive.read(_MANIFEST_PATH))
                certificate = package.get("certificate")
                if not isinstance(certificate, Mapping) or _text(
                    certificate.get("evidence_manifest_sha256")
                ) != manifest_sha:
                    errors.add("phase4_evidence_manifest_hash_mismatch")
    except Exception:
        errors.add("phase4_delivery_archive_invalid")

    certificate = package.get("certificate")
    binding = engagement_binding(record)
    if not isinstance(certificate, Mapping):
        errors.add("phase4_delivery_certificate_missing")
    else:
        for key, expected in (
            ("client_identity", binding["client_identity"]),
            ("project_identity", binding["project_identity"]),
            ("project_id", binding["project_id"]),
        ):
            if _text(certificate.get(key)) != _text(expected):
                errors.add(f"phase4_{key}_mismatch")
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
    updated["accepted_edition"] = deepcopy(bound)
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
