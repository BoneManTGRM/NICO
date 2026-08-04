from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.full-assessment-delivery-digest-binding.v1.2"
_MARKER = "__nico_full_assessment_delivery_digest_binding_v1__"


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _canonical(report: Mapping[str, Any]) -> Mapping[str, Any]:
    formats = report.get("formats") if isinstance(report.get("formats"), Mapping) else {}
    value = formats.get("json") if isinstance(formats.get("json"), Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _draft_identity(report: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = report.get("draft_artifact_identity")
    if isinstance(direct, Mapping):
        return direct
    nested = _canonical(report).get("draft_artifact_identity")
    if isinstance(nested, Mapping):
        return nested
    return {}


def _requires_exact_artifact_binding(
    report: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> bool:
    """Enforce the new digest contract only after a report enters that lifecycle.

    Historical approved-delivery records predate detached manifests. They continue
    through the existing delivery validator. Any report or approval that advertises
    a manifest, exact identity, digest, or exact-artifact requirement remains fully
    fail-closed under the new contract.
    """

    canonical = _canonical(report)
    report_markers = (
        report.get("draft_artifact_identity"),
        report.get("artifact_manifest"),
        canonical.get("draft_artifact_identity"),
        canonical.get("artifact_manifest"),
    )
    if any(isinstance(value, Mapping) for value in report_markers):
        return True
    if report.get("exact_artifact_approval_required") is True:
        return True
    if canonical.get("exact_artifact_approval_required") is True:
        return True
    if approval.get("exact_artifact_approval_required") is True:
        return True
    if isinstance(approval.get("draft_artifact_identity"), Mapping):
        return True
    return any(
        _text(approval.get(key))
        for key in (
            "approved_pdf_sha256",
            "approved_json_sha256",
            "evidence_manifest_sha256",
            "artifact_manifest_id",
        )
    )


def _approval_digest(
    approval: Mapping[str, Any],
    explicit_key: str,
    identity_key: str,
) -> str:
    explicit = _text(approval.get(explicit_key))
    if explicit:
        return explicit
    identity = approval.get("draft_artifact_identity")
    if isinstance(identity, Mapping):
        return _text(identity.get(identity_key))
    return ""


def install_full_assessment_delivery_digest_binding_v1() -> dict[str, Any]:
    from nico import final_review_workflow as workflow
    from nico import full_assessment_delivery as delivery
    from nico.exact_artifact_review_compat_v1 import (
        install_exact_artifact_review_compat_v1,
    )

    current = delivery.build_approved_delivery_artifact
    if getattr(current, _MARKER, False):
        review_compat = install_exact_artifact_review_compat_v1()
        return {
            "status": "already_installed",
            "version": VERSION,
            "approved_delivery_bound_to_three_digests": True,
            "legacy_non_manifest_delivery_compatibility_preserved": True,
            "exact_artifact_review_compat": review_compat,
        }

    @wraps(current)
    def build_approved_delivery_artifact(
        report: dict[str, Any],
        approval: dict[str, Any],
        *,
        approved_at: str,
    ) -> dict[str, Any]:
        if not _requires_exact_artifact_binding(report, approval):
            return deepcopy(current(report, approval, approved_at=approved_at))

        identity = _draft_identity(report)
        required = {
            "pdf_sha256": _text(identity.get("pdf_sha256")),
            "canonical_json_sha256": _text(identity.get("canonical_json_sha256")),
            "evidence_manifest_sha256": _text(identity.get("evidence_manifest_sha256")),
            "manifest_id": _text(identity.get("manifest_id")),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            return {
                "status": "blocked",
                "error": (
                    "Approved delivery requires the exact draft PDF, canonical JSON, "
                    "and evidence-manifest digests. Missing: " + ", ".join(missing)
                ),
                "client_delivery_allowed": False,
            }

        supplied = {
            "pdf_sha256": _approval_digest(
                approval,
                "approved_pdf_sha256",
                "pdf_sha256",
            ),
            "canonical_json_sha256": _approval_digest(
                approval,
                "approved_json_sha256",
                "canonical_json_sha256",
            ),
            "evidence_manifest_sha256": _approval_digest(
                approval,
                "evidence_manifest_sha256",
                "evidence_manifest_sha256",
            ),
        }
        mismatches = [
            key
            for key, value in supplied.items()
            if value and value != required[key]
        ]
        if mismatches:
            return {
                "status": "blocked",
                "error": (
                    "Approved delivery digest mismatch for: " + ", ".join(mismatches)
                ),
                "client_delivery_allowed": False,
            }

        enriched_approval = deepcopy(approval)
        enriched_approval.update(
            {
                "approved_pdf_sha256": required["pdf_sha256"],
                "approved_json_sha256": required["canonical_json_sha256"],
                "evidence_manifest_sha256": required["evidence_manifest_sha256"],
                "artifact_manifest_id": required["manifest_id"],
                "draft_artifact_identity": deepcopy(dict(identity)),
                "exact_artifact_identity_verified": True,
            }
        )
        result = deepcopy(current(report, enriched_approval, approved_at=approved_at))
        if result.get("status") != "complete":
            return result
        if result.get("source_draft_pdf_sha256") != required["pdf_sha256"]:
            return {
                "status": "blocked",
                "error": "Approved delivery source PDF digest changed during rendering.",
                "client_delivery_allowed": False,
            }
        result.update(
            {
                "source_draft_pdf_sha256": required["pdf_sha256"],
                "source_draft_json_sha256": required["canonical_json_sha256"],
                "source_evidence_manifest_sha256": required[
                    "evidence_manifest_sha256"
                ],
                "source_artifact_manifest_id": required["manifest_id"],
                "approved_digests": {
                    "pdf_sha256": required["pdf_sha256"],
                    "canonical_json_sha256": required["canonical_json_sha256"],
                    "evidence_manifest_sha256": required[
                        "evidence_manifest_sha256"
                    ],
                },
                "exact_artifact_identity_verified": True,
                "regeneration_invalidates_approval": True,
                "disclosure": (
                    "Approval authorizes delivery only of the artifact derived from "
                    "the exact reviewed PDF, canonical JSON, and detached evidence-manifest digests."
                ),
            }
        )
        return result

    setattr(build_approved_delivery_artifact, _MARKER, True)
    setattr(build_approved_delivery_artifact, "_nico_previous", current)
    delivery.build_approved_delivery_artifact = build_approved_delivery_artifact
    workflow.build_approved_delivery_artifact = build_approved_delivery_artifact
    review_compat = install_exact_artifact_review_compat_v1()
    return {
        "status": "installed",
        "version": VERSION,
        "approved_delivery_bound_to_three_digests": True,
        "digest_mismatch_blocks_delivery": True,
        "regeneration_invalidates_approval": True,
        "legacy_non_manifest_delivery_compatibility_preserved": True,
        "manifest_aware_missing_identity_fails_closed": True,
        "exact_artifact_review_compat": review_compat,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_requires_exact_artifact_binding",
    "install_full_assessment_delivery_digest_binding_v1",
]
