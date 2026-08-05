from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from nico.client_readiness_exact_artifact_approval import validate_exact_artifact_approval
from nico.comprehensive_approved_delivery_v1 import (
    attach_approved_delivery_package as _attach_v1,
    validate_approved_delivery_package,
)

VERSION = "nico.client-readiness-approved-delivery.v1"


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attach_approved_delivery_package(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach delivery only after the exact client-readiness approval validates."""

    approval = manifest.get("client_readiness_approval")
    validation = validate_exact_artifact_approval(approval)
    if validation.get("status") != "approved":
        raise ValueError(
            "approved_delivery_requires_exact_client_readiness_approval:"
            + ",".join(str(item) for item in validation.get("validation_errors") or [])
        )
    updated = _attach_v1(record, manifest)
    package = (
        deepcopy(updated.get("approved_delivery_package"))
        if isinstance(updated.get("approved_delivery_package"), Mapping)
        else {}
    )
    certificate = (
        deepcopy(package.get("certificate"))
        if isinstance(package.get("certificate"), Mapping)
        else {}
    )
    certificate["client_readiness_approval_subject_sha256"] = str(
        validation.get("approval_subject_sha256") or ""
    )
    certificate["client_readiness_approval_receipt_sha256"] = str(
        validation.get("approval_receipt_sha256") or ""
    )
    if not certificate["client_readiness_approval_subject_sha256"]:
        raise ValueError("approved_delivery_client_readiness_subject_digest_required")
    if not certificate["client_readiness_approval_receipt_sha256"]:
        raise ValueError("approved_delivery_client_readiness_receipt_digest_required")
    certificate.pop("delivery_authorization_certificate_sha256", None)
    certificate["delivery_authorization_certificate_sha256"] = _canonical_hash(certificate)
    package["certificate"] = certificate
    updated["approved_delivery_package"] = package

    package_validation = validate_approved_delivery_package(updated, package)
    if package_validation.get("status") != "valid":
        raise ValueError(
            "invalid_client_readiness_approved_delivery_package:"
            + ",".join(str(item) for item in package_validation.get("validation_errors") or [])
        )

    from nico.comprehensive_run_record import _record_hash

    updated["integrity_sha256"] = _record_hash(updated)
    return updated


__all__ = ["VERSION", "attach_approved_delivery_package"]
