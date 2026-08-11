from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_approved_delivery_v1 import (
    require_new_report_after_evidence_request,
    validate_approved_delivery_package as validate_v1,
)
from nico.comprehensive_delivery_package_v3 import build_comprehensive_delivery_package
from nico.comprehensive_review_decision_v1 import report_package_from_record
from nico.comprehensive_review_work_v2 import ledger_for_record

VERSION = "nico.comprehensive_approved_delivery.v3"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _review_decision(manifest: Mapping[str, Any]) -> str:
    review = manifest.get("review")
    return _text(review.get("decision")).casefold() if isinstance(review, Mapping) else ""


def _review_binding(record: Mapping[str, Any]) -> tuple[str, str]:
    if not isinstance(record.get("review_work_ledger"), Mapping):
        return "", ""
    ledger = ledger_for_record(record)
    return _canonical_hash(ledger), _text(ledger.get("review_source_sha256"))


def build_approved_delivery_package(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if _review_decision(manifest) != "approved":
        raise ValueError("approved_delivery_requires_approved_review_decision")
    if manifest.get("accepted_edition") is not True:
        raise ValueError("approved_delivery_requires_valid_accepted_edition")
    if manifest.get("client_delivery_allowed") is not True:
        raise ValueError("approved_delivery_requires_delivery_authorization")
    if list(manifest.get("validation_errors") or []):
        raise ValueError("approved_delivery_manifest_contains_validation_errors")

    ledger_hash, source_hash = _review_binding(record)
    if ledger_hash:
        if _text(manifest.get("review_work_ledger_sha256")) != ledger_hash:
            raise ValueError("approved_delivery_review_ledger_binding_mismatch")
        if _text(manifest.get("review_work_source_sha256")) != source_hash:
            raise ValueError("approved_delivery_review_source_binding_mismatch")

    report_package = report_package_from_record(record)
    if not report_package:
        raise ValueError("approved_delivery_report_package_required")
    package_input = deepcopy(report_package)
    package_input["accepted_edition"] = deepcopy(dict(manifest))
    delivery = build_comprehensive_delivery_package(package_input)
    if delivery.get("status") != "approved_for_delivery":
        raise ValueError("approved_delivery_package_incomplete")
    if delivery.get("client_delivery_allowed") is not True:
        raise ValueError("approved_delivery_package_not_authorized")
    if delivery.get("one_client_report") is not True or int(delivery.get("client_pdf_count") or 0) != 1:
        raise ValueError("approved_delivery_requires_one_comprehensive_client_report")
    if delivery.get("approval_certificate_page_appended") is not True:
        raise ValueError("approved_delivery_requires_client_pdf_approval_certificate")
    if list(delivery.get("missing_required_artifacts") or []):
        raise ValueError("approved_delivery_package_missing_required_artifacts")

    encoded = _text(delivery.get("zip_base64"))
    try:
        archive = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("approved_delivery_package_base64_invalid") from exc
    if not archive.startswith(b"PK"):
        raise ValueError("approved_delivery_package_zip_invalid")
    archive_sha = hashlib.sha256(archive).hexdigest()
    if archive_sha != _text(delivery.get("zip_sha256")):
        raise ValueError("approved_delivery_package_hash_mismatch")

    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    review = manifest.get("review") if isinstance(manifest.get("review"), Mapping) else {}
    certificate = {
        "artifact_schema": VERSION,
        "run_id": _text(identity.get("run_id")),
        "repository": _text(identity.get("repository")),
        "commit_sha": _text(identity.get("commit_sha")),
        "report_artifact_digest": _text(manifest.get("report_artifact_digest")),
        "accepted_edition_manifest_sha256": _text(manifest.get("accepted_edition_manifest_sha256")),
        "approval_certificate_sha256": _text(review.get("approval_certificate_sha256")),
        "review_work_ledger_sha256": _text(manifest.get("review_work_ledger_sha256")),
        "review_work_source_sha256": _text(manifest.get("review_work_source_sha256")),
        "delivery_package_sha256": archive_sha,
        "delivery_package_size_bytes": len(archive),
        "delivery_package_filename": _text(delivery.get("filename")),
        "approved_at": _text(review.get("decided_at")),
        "final_human_approval_status": "approved",
        "client_delivery_authorization_status": "authorized",
        "approval_certificate_page_appended": True,
        "report_analysis_regenerated_during_delivery_packaging": False,
        "one_client_report": True,
        "client_pdf_count": 1,
        "human_review_required": True,
        "client_delivery_allowed": True,
    }
    required = (
        "run_id",
        "repository",
        "commit_sha",
        "report_artifact_digest",
        "accepted_edition_manifest_sha256",
        "approval_certificate_sha256",
        "delivery_package_sha256",
        "delivery_package_filename",
        "approved_at",
    )
    missing = [field for field in required if not _text(certificate.get(field))]
    if ledger_hash and not certificate["review_work_ledger_sha256"]:
        missing.append("review_work_ledger_sha256")
    if missing:
        raise ValueError("approved_delivery_certificate_missing:" + ",".join(sorted(set(missing))))
    certificate["delivery_authorization_certificate_sha256"] = _canonical_hash(certificate)

    return {
        "artifact_schema": VERSION,
        "status": "approved_for_delivery",
        "filename": _text(delivery.get("filename")),
        "zip_base64": encoded,
        "zip_sha256": archive_sha,
        "zip_size_bytes": len(archive),
        "artifact_count": int(delivery.get("artifact_count") or 0),
        "manifest": deepcopy(delivery.get("manifest") or {}),
        "certificate": certificate,
        "one_client_report": True,
        "client_pdf_count": 1,
        "approval_certificate_page_appended": True,
        "final_human_approval_status": "approved",
        "client_delivery_authorization_status": "authorized",
        "human_review_required": True,
        "client_delivery_allowed": True,
    }


def validate_approved_delivery_package(
    record: Mapping[str, Any],
    package: Any,
) -> dict[str, Any]:
    result = dict(validate_v1(record, package))
    errors = set(str(value) for value in result.get("validation_errors") or [])
    if not isinstance(package, Mapping):
        return result
    certificate = package.get("certificate") if isinstance(package.get("certificate"), Mapping) else {}
    ledger_hash, source_hash = _review_binding(record)
    if ledger_hash and _text(certificate.get("review_work_ledger_sha256")) != ledger_hash:
        errors.add("delivery_review_ledger_hash_mismatch")
    if source_hash and _text(certificate.get("review_work_source_sha256")) != source_hash:
        errors.add("delivery_review_source_hash_mismatch")
    if package.get("one_client_report") is not True or int(package.get("client_pdf_count") or 0) != 1:
        errors.add("delivery_not_single_comprehensive_report")
    if package.get("approval_certificate_page_appended") is not True:
        errors.add("delivery_pdf_approval_certificate_missing")
    if _text(certificate.get("final_human_approval_status")) != "approved":
        errors.add("delivery_final_approval_status_invalid")
    if _text(certificate.get("client_delivery_authorization_status")) != "authorized":
        errors.add("delivery_authorization_status_invalid")
    result["validation_errors"] = sorted(errors)
    result["status"] = "valid" if not errors else "invalid"
    return result


def attach_approved_delivery_package(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    updated = deepcopy(dict(record))
    if _review_decision(manifest) != "approved":
        updated.pop("approved_delivery_package", None)
        return updated
    require_new_report_after_evidence_request(updated, manifest)
    delivery = build_approved_delivery_package(updated, manifest)
    updated["approved_delivery_package"] = delivery
    context = deepcopy(updated.get("review_context")) if isinstance(updated.get("review_context"), Mapping) else {}
    context.update(
        {
            "approved_delivery_package_filename": delivery["filename"],
            "approved_delivery_package_sha256": delivery["zip_sha256"],
            "delivery_authorization_certificate_sha256": delivery["certificate"]["delivery_authorization_certificate_sha256"],
            "one_client_report": True,
            "client_pdf_count": 1,
            "approval_certificate_page_appended": True,
            "final_human_approval_status": "approved",
            "client_delivery_authorization_status": "authorized",
            "report_analysis_regenerated_during_delivery_packaging": False,
        }
    )
    updated["review_context"] = context
    validation = validate_approved_delivery_package(updated, delivery)
    if validation["status"] != "valid":
        raise ValueError(
            "invalid_approved_delivery_package:"
            + ",".join(validation["validation_errors"])
        )
    from nico.comprehensive_run_record import _record_hash

    updated["integrity_sha256"] = _record_hash(updated)
    return updated


__all__ = [
    "VERSION",
    "attach_approved_delivery_package",
    "build_approved_delivery_package",
    "validate_approved_delivery_package",
]
