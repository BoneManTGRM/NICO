from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Mapping

from nico.decision_grade_accepted_edition_v2 import VERSION as ACCEPTED_EDITION_VERSION

VERSION = "nico.decision_grade_accepted_edition_guard.v1"


def _bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def current_report_artifact_digests(
    package: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
    except Exception:
        pdf = b""
    values = {
        "markdown": package.get("markdown"),
        "html": package.get("html"),
        "pdf": pdf,
        "json": package.get("json"),
    }
    output: dict[str, dict[str, Any]] = {}
    for name, value in values.items():
        if value in (None, "", b""):
            continue
        encoded = _bytes(value)
        output[name] = {
            "sha256": _sha256(encoded),
            "size_bytes": len(encoded),
        }
    return output


def current_report_artifact_digest(package: Mapping[str, Any]) -> str:
    return _sha256(_bytes(current_report_artifact_digests(package)))


def validate_accepted_edition(
    package: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if candidate.get("artifact_schema") != ACCEPTED_EDITION_VERSION:
        errors.append("accepted_edition_schema_mismatch")
    if candidate.get("accepted_edition") is not True:
        errors.append("accepted_edition_not_approved")
    if candidate.get("client_delivery_allowed") is not True:
        errors.append("accepted_edition_delivery_not_authorized")
    if str(candidate.get("delivery_status") or "") != "approved_for_delivery":
        errors.append("accepted_edition_delivery_status_invalid")
    if list(candidate.get("validation_errors") or []):
        errors.append("accepted_edition_contains_validation_errors")
    review = (
        candidate.get("review")
        if isinstance(candidate.get("review"), Mapping)
        else {}
    )
    if str(review.get("decision") or "").casefold() != "approved":
        errors.append("accepted_edition_review_decision_invalid")
    if not str(review.get("reviewer") or "").strip():
        errors.append("accepted_edition_reviewer_required")
    if not str(review.get("reviewer_role") or "").strip():
        errors.append("accepted_edition_reviewer_role_required")

    expected_digests = current_report_artifact_digests(package)
    expected_digest = current_report_artifact_digest(package)
    if set(expected_digests) != {"markdown", "html", "pdf", "json"}:
        errors.append("current_report_required_artifacts_missing")
    if candidate.get("artifact_digests") != expected_digests:
        errors.append("accepted_edition_artifact_digests_mismatch")
    if str(candidate.get("report_artifact_digest") or "") != expected_digest:
        errors.append("accepted_edition_report_digest_mismatch")
    if str(review.get("report_artifact_digest") or "") != expected_digest:
        errors.append("accepted_edition_certificate_report_digest_mismatch")

    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    for field in (
        "repository",
        "commit_sha",
        "run_id",
        "report_language",
        "assessment_depth",
    ):
        expected = str(identity.get(field) or "").strip()
        actual = str(candidate.get(field) or "").strip()
        if not expected:
            errors.append(f"current_report_identity_missing:{field}")
        elif actual != expected:
            errors.append(f"accepted_edition_identity_mismatch:{field}")
    for field in ("tree_sha", "scanner_run_id", "evidence_bundle_hash"):
        if not str(candidate.get(field) or "").strip():
            errors.append(f"accepted_edition_identity_missing:{field}")

    return {
        "artifact_schema": VERSION,
        "status": "valid" if not errors else "invalid",
        "validation_errors": errors,
        "current_report_artifact_digest": expected_digest,
        "current_report_artifact_digests": expected_digests,
        "client_delivery_allowed": not errors,
    }


def guard_report_package_accepted_edition(
    package: dict[str, Any],
) -> dict[str, Any]:
    candidate = package.get("accepted_edition")
    if not isinstance(candidate, Mapping):
        package["accepted_edition_validation"] = {
            "artifact_schema": VERSION,
            "status": "not_present",
            "validation_errors": ["accepted_edition_not_present"],
            "client_delivery_allowed": False,
        }
        return package
    validation = validate_accepted_edition(package, candidate)
    package["accepted_edition_validation"] = validation
    if validation["status"] != "valid":
        blocked = dict(candidate)
        blocked["accepted_edition"] = False
        blocked["client_delivery_allowed"] = False
        blocked["delivery_status"] = "blocked"
        blocked["validation_errors"] = sorted(
            {
                *[str(item) for item in candidate.get("validation_errors") or []],
                *validation["validation_errors"],
            }
        )
        package["accepted_edition"] = blocked
    return package


__all__ = [
    "VERSION",
    "current_report_artifact_digest",
    "current_report_artifact_digests",
    "guard_report_package_accepted_edition",
    "validate_accepted_edition",
]
