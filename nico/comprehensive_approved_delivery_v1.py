from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_review_decision_v1 import report_package_from_record
from nico.decision_grade_premium_delivery_v1 import build_premium_delivery_package

VERSION = "nico.comprehensive_approved_delivery.v1"


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _review_decision(manifest: Mapping[str, Any]) -> str:
    review = manifest.get("review")
    return (
        str(review.get("decision") or "").strip().casefold()
        if isinstance(review, Mapping)
        else ""
    )


def require_new_report_after_evidence_request(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    """Prevent an unchanged report from being approved after more evidence was requested."""

    current_digest = str(manifest.get("report_artifact_digest") or "").strip()
    for candidate in reversed(list(record.get("review_history") or [])):
        if not isinstance(candidate, Mapping):
            continue
        if _review_decision(candidate) != "request_more_evidence":
            continue
        requested_digest = str(candidate.get("report_artifact_digest") or "").strip()
        if requested_digest and requested_digest == current_digest:
            raise ValueError(
                "approval_requires_new_evidence_bound_report_after_request_more_evidence"
            )
        return


def build_approved_delivery_package(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic delivery ZIP bound to an already-approved report edition."""

    if _review_decision(manifest) != "approved":
        raise ValueError("approved_delivery_requires_approved_review_decision")
    if manifest.get("accepted_edition") is not True:
        raise ValueError("approved_delivery_requires_valid_accepted_edition")
    if manifest.get("client_delivery_allowed") is not True:
        raise ValueError("approved_delivery_requires_delivery_authorization")
    if list(manifest.get("validation_errors") or []):
        raise ValueError("approved_delivery_manifest_contains_validation_errors")

    report_package = report_package_from_record(record)
    if not report_package:
        raise ValueError("approved_delivery_report_package_required")
    package_input = deepcopy(report_package)
    package_input["accepted_edition"] = deepcopy(dict(manifest))
    delivery = build_premium_delivery_package(package_input)
    if delivery.get("status") != "approved_for_delivery":
        raise ValueError("approved_delivery_package_incomplete")
    if delivery.get("client_delivery_allowed") is not True:
        raise ValueError("approved_delivery_package_not_authorized")
    if list(delivery.get("missing_required_artifacts") or []):
        raise ValueError("approved_delivery_package_missing_required_artifacts")

    encoded = str(delivery.get("zip_base64") or "").strip()
    try:
        archive = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("approved_delivery_package_base64_invalid") from exc
    if not archive.startswith(b"PK"):
        raise ValueError("approved_delivery_package_zip_invalid")
    archive_sha = hashlib.sha256(archive).hexdigest()
    if archive_sha != str(delivery.get("zip_sha256") or ""):
        raise ValueError("approved_delivery_package_hash_mismatch")

    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    certificate = {
        "artifact_schema": VERSION,
        "run_id": str(identity.get("run_id") or ""),
        "repository": str(identity.get("repository") or ""),
        "commit_sha": str(identity.get("commit_sha") or ""),
        "report_artifact_digest": str(manifest.get("report_artifact_digest") or ""),
        "accepted_edition_manifest_sha256": str(
            manifest.get("accepted_edition_manifest_sha256") or ""
        ),
        "approval_certificate_sha256": str(
            (manifest.get("review") or {}).get("approval_certificate_sha256")
            if isinstance(manifest.get("review"), Mapping)
            else ""
        ),
        "delivery_package_sha256": archive_sha,
        "delivery_package_size_bytes": len(archive),
        "delivery_package_filename": str(delivery.get("filename") or ""),
        "approved_at": str(
            (manifest.get("review") or {}).get("decided_at")
            if isinstance(manifest.get("review"), Mapping)
            else ""
        ),
        "report_regenerated_during_delivery_packaging": False,
        "human_review_required": True,
        "client_delivery_allowed": True,
    }
    missing = [
        field
        for field in (
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
        if not str(certificate.get(field) or "").strip()
    ]
    if missing:
        raise ValueError("approved_delivery_certificate_missing:" + ",".join(missing))
    certificate["delivery_authorization_certificate_sha256"] = _canonical_hash(
        certificate
    )

    return {
        "artifact_schema": VERSION,
        "status": "approved_for_delivery",
        "filename": str(delivery.get("filename") or ""),
        "zip_base64": encoded,
        "zip_sha256": archive_sha,
        "zip_size_bytes": len(archive),
        "artifact_count": int(delivery.get("artifact_count") or 0),
        "manifest": deepcopy(delivery.get("manifest") or {}),
        "certificate": certificate,
        "human_review_required": True,
        "client_delivery_allowed": True,
    }


def validate_approved_delivery_package(
    record: Mapping[str, Any],
    package: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(package, Mapping):
        return {"status": "invalid", "validation_errors": ["package_required"]}
    if package.get("status") != "approved_for_delivery":
        errors.append("status_not_approved_for_delivery")
    if package.get("client_delivery_allowed") is not True:
        errors.append("delivery_not_authorized")
    try:
        archive = base64.b64decode(str(package.get("zip_base64") or ""), validate=True)
    except Exception:
        archive = b""
        errors.append("zip_base64_invalid")
    if not archive.startswith(b"PK"):
        errors.append("zip_signature_invalid")
    archive_sha = hashlib.sha256(archive).hexdigest() if archive else ""
    if archive_sha != str(package.get("zip_sha256") or ""):
        errors.append("zip_hash_mismatch")
    if len(archive) != int(package.get("zip_size_bytes") or 0):
        errors.append("zip_size_mismatch")

    certificate = (
        package.get("certificate")
        if isinstance(package.get("certificate"), Mapping)
        else {}
    )
    certificate_payload = deepcopy(dict(certificate))
    claimed_certificate_hash = str(
        certificate_payload.pop("delivery_authorization_certificate_sha256", "") or ""
    )
    if not claimed_certificate_hash or claimed_certificate_hash != _canonical_hash(
        certificate_payload
    ):
        errors.append("delivery_authorization_certificate_hash_mismatch")

    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    for field in ("run_id", "repository", "commit_sha"):
        if str(certificate.get(field) or "") != str(identity.get(field) or ""):
            errors.append(f"delivery_identity_mismatch:{field}")
    accepted = (
        record.get("accepted_edition")
        if isinstance(record.get("accepted_edition"), Mapping)
        else {}
    )
    for field in (
        "report_artifact_digest",
        "accepted_edition_manifest_sha256",
    ):
        if str(certificate.get(field) or "") != str(accepted.get(field) or ""):
            errors.append(f"delivery_accepted_edition_mismatch:{field}")
    if str(certificate.get("delivery_package_sha256") or "") != archive_sha:
        errors.append("delivery_certificate_zip_hash_mismatch")
    if str(certificate.get("delivery_package_filename") or "") != str(
        package.get("filename") or ""
    ):
        errors.append("delivery_certificate_filename_mismatch")

    return {
        "status": "valid" if not errors else "invalid",
        "validation_errors": sorted(set(errors)),
        "zip_sha256": archive_sha,
        "zip_size_bytes": len(archive),
    }


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
    context = (
        deepcopy(updated.get("review_context"))
        if isinstance(updated.get("review_context"), Mapping)
        else {}
    )
    context.update(
        {
            "approved_delivery_package_filename": delivery["filename"],
            "approved_delivery_package_sha256": delivery["zip_sha256"],
            "delivery_authorization_certificate_sha256": delivery["certificate"][
                "delivery_authorization_certificate_sha256"
            ],
            "report_regenerated_during_delivery_packaging": False,
        }
    )
    updated["review_context"] = context

    validation = validate_approved_delivery_package(updated, delivery)
    if validation["status"] != "valid":
        raise ValueError(
            "invalid_approved_delivery_package:"
            + ",".join(validation["validation_errors"])
        )
    # Imported lazily to avoid a module-import cycle with the run-record validator.
    from nico.comprehensive_run_record import _record_hash

    updated["integrity_sha256"] = _record_hash(updated)
    return updated


__all__ = [
    "VERSION",
    "attach_approved_delivery_package",
    "build_approved_delivery_package",
    "require_new_report_after_evidence_request",
    "validate_approved_delivery_package",
]
