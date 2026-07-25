from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

VERSION = "nico.decision_grade_accepted_edition.v2"
_REQUIRED_ARTIFACTS = ("markdown", "html", "pdf", "json")
_ALLOWED_DECISIONS = {"approved", "rejected", "request_more_evidence"}


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
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _required_text(value: Any, field: str, errors: list[str]) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        errors.append(f"missing_{field}")
    return normalized


def build_accepted_report_edition(
    *,
    repository: str,
    commit_sha: str,
    tree_sha: str,
    run_id: str,
    scanner_run_id: str,
    evidence_bundle_hash: str,
    report_language: str,
    assessment_depth: str,
    artifacts: Mapping[str, Any],
    reviewer: str,
    reviewer_role: str,
    decision: str,
    decision_reason: str,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic, fail-closed accepted-edition manifest.

    The approved edition is the exact immutable artifact set supplied to this
    function. Review metadata is added as a certificate; report contents are
    never rewritten or regenerated during approval.
    """

    errors: list[str] = []
    normalized_decision = str(decision or "").strip().casefold()
    identity = {
        "repository": _required_text(repository, "identity:repository", errors),
        "commit_sha": _required_text(commit_sha, "identity:commit_sha", errors),
        "tree_sha": _required_text(tree_sha, "identity:tree_sha", errors),
        "run_id": _required_text(run_id, "identity:run_id", errors),
        "scanner_run_id": _required_text(
            scanner_run_id,
            "identity:scanner_run_id",
            errors,
        ),
        "evidence_bundle_hash": _required_text(
            evidence_bundle_hash,
            "identity:evidence_bundle_hash",
            errors,
        ),
        "report_language": _required_text(
            report_language,
            "identity:report_language",
            errors,
        ),
        "assessment_depth": _required_text(
            assessment_depth,
            "identity:assessment_depth",
            errors,
        ),
    }

    reviewer_value = _required_text(reviewer, "reviewer", errors)
    reviewer_role_value = _required_text(reviewer_role, "reviewer_role", errors)
    reason_value = _required_text(decision_reason, "decision_reason", errors)
    if normalized_decision not in _ALLOWED_DECISIONS:
        errors.append("invalid_decision")

    if not isinstance(artifacts, Mapping):
        errors.append("artifacts_must_be_mapping")
        artifacts = {}

    artifact_digests: dict[str, dict[str, Any]] = {}
    missing_artifacts: list[str] = []
    for name in _REQUIRED_ARTIFACTS:
        if name not in artifacts or artifacts[name] in (None, "", b""):
            missing_artifacts.append(name)
            continue
        payload = artifacts[name]
        encoded = _bytes(payload)
        artifact_digests[name] = {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "size_bytes": len(encoded),
        }
    if missing_artifacts:
        errors.append("missing_required_artifacts:" + ",".join(missing_artifacts))

    report_artifact_digest = _sha256(artifact_digests)
    timestamp = str(
        decided_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    ).strip()
    if not timestamp:
        errors.append("missing_decided_at")

    approved = normalized_decision == "approved" and not errors
    review_certificate = {
        "reviewer": reviewer_value,
        "reviewer_role": reviewer_role_value,
        "decision": normalized_decision or "invalid",
        "reason": reason_value,
        "decided_at": timestamp,
        "report_artifact_digest": report_artifact_digest,
        "evidence_bundle_hash": identity["evidence_bundle_hash"],
    }
    review_certificate["approval_certificate_sha256"] = _sha256(
        review_certificate
    )

    manifest = {
        "artifact_schema": VERSION,
        **identity,
        "report_artifact_digest": report_artifact_digest,
        "artifact_digests": artifact_digests,
        "review": review_certificate,
        "validation_errors": errors,
        "accepted_edition": approved,
        "delivery_status": "approved_for_delivery" if approved else "blocked",
        "human_review_required": True,
        "client_delivery_allowed": approved,
    }
    manifest["accepted_edition_manifest_sha256"] = _sha256(manifest)
    return manifest


__all__ = ["VERSION", "build_accepted_report_edition"]
