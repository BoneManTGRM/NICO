from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.full-assessment-delivery-digest-binding.v1.1"
_MARKER = "__nico_full_assessment_delivery_digest_binding_v1__"


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _draft_identity(report: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = report.get("draft_artifact_identity")
    if isinstance(direct, Mapping):
        return direct
    formats = report.get("formats") if isinstance(report.get("formats"), Mapping) else {}
    canonical = formats.get("json") if isinstance(formats.get("json"), Mapping) else {}
    nested = canonical.get("draft_artifact_identity") if isinstance(canonical, Mapping) else None
    if isinstance(nested, Mapping):
        return nested
    return {}


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

    current = delivery.build_approved_delivery_artifact
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "approved_delivery_bound_to_three_digests": True,
        }

    @wraps(current)
    def build_approved_delivery_artifact(
        report: dict[str, Any],
        approval: dict[str, Any],
        *,
        approved_at: str,
    ) -> dict[str, Any]:
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
    return {
        "status": "installed",
        "version": VERSION,
        "approved_delivery_bound_to_three_digests": True,
        "digest_mismatch_blocks_delivery": True,
        "regeneration_invalidates_approval": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_full_assessment_delivery_digest_binding_v1",
]
