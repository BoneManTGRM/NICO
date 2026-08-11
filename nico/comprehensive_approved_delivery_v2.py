from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_approved_delivery_v1 import (
    require_new_report_after_evidence_request,
    validate_approved_delivery_package,
)
from nico.comprehensive_delivery_package_v2 import build_comprehensive_delivery_package
from nico.comprehensive_review_decision_v1 import report_package_from_record

VERSION = "nico.comprehensive_approved_delivery.v2"


def _review_decision(manifest: Mapping[str, Any]) -> str:
    review = manifest.get("review")
    return (
        str(review.get("decision") or "").strip().casefold()
        if isinstance(review, Mapping)
        else ""
    )


def _canonical_hash(payload: Any) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


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
    review = manifest.get("review") if isinstance(manifest.get("review"), Mapping) else {}
    certificate = {
        "artifact_schema": VERSION,
        "run_id": str(identity.get("run_id") or ""),
        "repository": str(identity.get("repository") or ""),
        "commit_sha": str(identity.get("commit_sha") or ""),
        "report_artifact_digest": str(manifest.get("report_artifact_digest") or ""),
        "accepted_edition_manifest_sha256": str(
            manifest.get("accepted_edition_manifest_sha256") or ""
        ),
        "approval_certificate_sha256": str(review.get("approval_certificate_sha256") or ""),
        "review_work_ledger_sha256": str(manifest.get("review_work_ledger_sha256") or ""),
        "review_work_source_sha256": str(manifest.get("review_work_source_sha256") or ""),
        "delivery_package_sha256": archive_sha,
        "delivery_package_size_bytes": len(archive),
        "delivery_package_filename": str(delivery.get("filename") or ""),
        "approved_at": str(review.get("decided_at") or ""),
        "report_regenerated_during_delivery_packaging": False,
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
    missing = [field for field in required if not str(certificate.get(field) or "").strip()]
    if missing:
        raise ValueError("approved_delivery_certificate_missing:" + ",".join(missing))
    if isinstance(record.get("review_work_ledger"), Mapping) and not certificate["review_work_ledger_sha256"]:
        raise ValueError("approved_delivery_certificate_missing:review_work_ledger_sha256")
    certificate["delivery_authorization_certificate_sha256"] = _canonical_hash(certificate)

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
        "one_client_report": True,
        "client_pdf_count": 1,
        "human_review_required": True,
        "client_delivery_allowed": True,
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
            "one_client_report": True,
            "client_pdf_count": 1,
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
    from nico.comprehensive_run_record import _record_hash

    updated["integrity_sha256"] = _record_hash(updated)
    return updated


__all__ = [
    "VERSION",
    "attach_approved_delivery_package",
    "build_approved_delivery_package",
]
