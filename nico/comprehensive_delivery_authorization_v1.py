from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256, reviewer_binding
from nico.comprehensive_review_decision_v1 import (
    assert_expected_review_artifact_identity,
    report_package_from_record,
    review_artifact_identity,
)
from nico.decision_grade_accepted_edition_guard_v1 import validate_accepted_edition

VERSION = "nico.comprehensive_delivery_authorization.v1"
AUTHORIZATION_BASIS = "protected_admin_write_and_explicit_delivery_authorization"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _review(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    value = manifest.get("review")
    return value if isinstance(value, Mapping) else {}


def _authorization_hash(payload: Mapping[str, Any]) -> str:
    candidate = deepcopy(dict(payload))
    candidate.pop("delivery_authorization_sha256", None)
    return canonical_sha256(candidate)


def _accepted_manifest_hash(manifest: Mapping[str, Any]) -> str:
    candidate = deepcopy(dict(manifest))
    claimed = _text(candidate.pop("accepted_edition_manifest_sha256", ""))
    if not claimed or claimed != canonical_sha256(candidate):
        raise ValueError("accepted_edition_manifest_hash_mismatch")
    return claimed


def _assert_current_accepted_edition(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    validation = validate_accepted_edition(report_package_from_record(record), manifest)
    if validation["status"] != "valid":
        raise ValueError(
            "invalid_accepted_edition:" + ",".join(validation["validation_errors"])
        )


def validate_delivery_authorization(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
    authorization: Any,
) -> dict[str, Any]:
    """Validate a separate delivery receipt without changing human approval."""

    errors: list[str] = []
    if not isinstance(authorization, Mapping):
        return {
            "artifact_schema": VERSION,
            "status": "invalid",
            "validation_errors": ["delivery_authorization_required"],
            "client_delivery_allowed": False,
        }
    try:
        accepted_manifest_sha = _accepted_manifest_hash(manifest)
    except ValueError as exc:
        accepted_manifest_sha = ""
        errors.append(_text(exc))
    try:
        _assert_current_accepted_edition(record, manifest)
    except ValueError as exc:
        errors.append(_text(exc))

    if _text(record.get("status")).casefold() != "approved":
        errors.append("delivery_authorization_requires_approved_run")
    if record.get("human_review_completed") is not True:
        errors.append("delivery_authorization_requires_completed_human_review")
    if authorization.get("artifact_schema") != VERSION:
        errors.append("delivery_authorization_schema_mismatch")
    if authorization.get("human_action_required") is not True:
        errors.append("delivery_authorization_human_action_missing")
    if authorization.get("automation_may_not_authorize") is not True:
        errors.append("delivery_authorization_automation_boundary_missing")
    if manifest.get("accepted_edition") is not True:
        errors.append("delivery_authorization_accepted_edition_required")
    if _text(_review(manifest).get("decision")).casefold() != "approved":
        errors.append("delivery_authorization_human_approval_required")

    required = (
        "delivery_authorization_id",
        "authorizer_identity",
        "authorizer_role",
        "authorization_basis",
        "authorization_reason",
        "authorized_at",
        "run_id",
        "report_artifact_digest",
        "accepted_edition_manifest_sha256",
        "review_artifact_identity_sha256",
        "delivery_authorization_sha256",
    )
    for field in required:
        if not _text(authorization.get(field)):
            errors.append(f"delivery_authorization_{field}_required")
    if _text(authorization.get("authorization_basis")) != AUTHORIZATION_BASIS:
        errors.append("delivery_authorization_basis_invalid")
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    if _text(authorization.get("run_id")) != _text(identity.get("run_id")):
        errors.append("delivery_authorization_run_mismatch")
    if _text(authorization.get("report_artifact_digest")) != _text(
        manifest.get("report_artifact_digest")
    ):
        errors.append("delivery_authorization_report_digest_mismatch")
    if _text(authorization.get("accepted_edition_manifest_sha256")) != accepted_manifest_sha:
        errors.append("delivery_authorization_accepted_manifest_mismatch")
    supplied_identity = authorization.get("review_artifact_identity")
    if not isinstance(supplied_identity, Mapping):
        errors.append("delivery_authorization_review_artifact_identity_required")
    else:
        if _text(authorization.get("review_artifact_identity_sha256")) != canonical_sha256(
            supplied_identity
        ):
            errors.append("delivery_authorization_review_artifact_identity_hash_mismatch")
        current_identity = review_artifact_identity(record)
        for field in ("artifact_schema", "run_id", "report_artifact_digest", "artifact_digests"):
            if supplied_identity.get(field) != current_identity.get(field):
                errors.append(f"delivery_authorization_current_artifact_mismatch:{field}")
    if _text(authorization.get("delivery_authorization_sha256")) != _authorization_hash(
        authorization
    ):
        errors.append("delivery_authorization_hash_mismatch")
    try:
        reviewer_binding(
            reviewer=_text(authorization.get("authorizer_identity")),
            reviewer_role=_text(authorization.get("authorizer_role")),
            decision="approved",
            decided_at=_text(authorization.get("authorized_at")),
            decision_reason=_text(authorization.get("authorization_reason")),
            authorization_basis=AUTHORIZATION_BASIS,
        )
    except ValueError as exc:
        errors.append(_text(exc).split(":", 1)[0] or "delivery_authorizer_invalid")
    return {
        "artifact_schema": VERSION,
        "status": "valid" if not errors else "invalid",
        "validation_errors": sorted(set(errors)),
        "client_delivery_allowed": not errors,
    }


def authorize_accepted_edition(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    authorizer: str,
    authorizer_role: str,
    authorization_reason: str,
    authorized_at: str,
    expected_artifact_identity: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Create a delivery receipt bound to, but outside, immutable approval."""

    if _text(record.get("status")).casefold() != "approved":
        raise ValueError("delivery_authorization_requires_approved_run")
    if record.get("human_review_completed") is not True:
        raise ValueError("delivery_authorization_requires_completed_human_review")
    if record.get("client_delivery_allowed") is True or isinstance(
        record.get("delivery_authorization"), Mapping
    ):
        raise ValueError("client_delivery_already_authorized")
    if manifest.get("accepted_edition") is not True or _text(
        _review(manifest).get("decision")
    ).casefold() != "approved":
        raise ValueError("delivery_authorization_requires_accepted_edition")

    accepted_manifest_sha = _accepted_manifest_hash(manifest)
    _assert_current_accepted_edition(record, manifest)
    exact_identity = assert_expected_review_artifact_identity(record, expected_artifact_identity)
    human = reviewer_binding(
        reviewer=authorizer,
        reviewer_role=authorizer_role,
        decision="approved",
        decided_at=authorized_at,
        decision_reason=authorization_reason,
        authorization_basis=AUTHORIZATION_BASIS,
    )
    authorization: dict[str, Any] = {
        "artifact_schema": VERSION,
        "authorizer_identity": human["reviewer_identity"],
        "authorizer_role": human["reviewer_role"],
        "authorization_basis": AUTHORIZATION_BASIS,
        "authorization_reason": human["reviewer_notes"],
        "authorized_at": human["review_timestamp"],
        "run_id": _text(manifest.get("run_id")),
        "report_artifact_digest": _text(manifest.get("report_artifact_digest")),
        "accepted_edition_manifest_sha256": accepted_manifest_sha,
        "review_artifact_identity": deepcopy(dict(exact_identity)),
        "review_artifact_identity_sha256": canonical_sha256(exact_identity),
        "human_action_required": True,
        "automation_may_not_authorize": True,
    }
    authorization["delivery_authorization_id"] = (
        "delivery_authorization_" + canonical_sha256(authorization)[:24]
    )
    authorization["delivery_authorization_sha256"] = _authorization_hash(authorization)
    validation = validate_delivery_authorization(record, manifest, authorization)
    if validation["status"] != "valid":
        raise ValueError(
            "invalid_delivery_authorization:"
            + ",".join(validation["validation_errors"])
        )
    return authorization


__all__ = [
    "AUTHORIZATION_BASIS",
    "VERSION",
    "authorize_accepted_edition",
    "validate_delivery_authorization",
]
