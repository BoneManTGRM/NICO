from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

VERSION = "nico.decision_grade_accepted_edition.v1"
_REQUIRED_ARTIFACTS = ("markdown", "html", "pdf", "json")
_ALLOWED_DECISIONS = {"approved", "rejected"}


def _bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


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
    decision: str,
    decision_reason: str,
    accepted_at: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic, fail-closed manifest for a reviewed report edition."""

    normalized_decision = str(decision or "").strip().casefold()
    errors: list[str] = []
    identity = {
        "repository": str(repository or "").strip(),
        "commit_sha": str(commit_sha or "").strip(),
        "tree_sha": str(tree_sha or "").strip(),
        "run_id": str(run_id or "").strip(),
        "scanner_run_id": str(scanner_run_id or "").strip(),
        "evidence_bundle_hash": str(evidence_bundle_hash or "").strip(),
        "report_language": str(report_language or "").strip(),
        "assessment_depth": str(assessment_depth or "").strip(),
    }
    for key, value in identity.items():
        if not value:
            errors.append(f"missing_identity:{key}")

    reviewer_value = str(reviewer or "").strip()
    reason_value = str(decision_reason or "").strip()
    if not reviewer_value:
        errors.append("missing_reviewer")
    if normalized_decision not in _ALLOWED_DECISIONS:
        errors.append("invalid_decision")
    if not reason_value:
        errors.append("missing_decision_reason")

    artifact_digests: dict[str, dict[str, Any]] = {}
    missing_artifacts: list[str] = []
    for name in _REQUIRED_ARTIFACTS:
        if name not in artifacts or artifacts[name] in (None, "", b""):
            missing_artifacts.append(name)
            continue
        payload = artifacts[name]
        artifact_digests[name] = {
            "sha256": _sha256(payload),
            "size_bytes": len(_bytes(payload)),
        }
    if missing_artifacts:
        errors.append("missing_required_artifacts:" + ",".join(missing_artifacts))

    canonical_artifacts = json.dumps(artifact_digests, sort_keys=True, separators=(",", ":"))
    report_artifact_digest = _sha256(canonical_artifacts)
    timestamp = accepted_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    approved = normalized_decision == "approved" and not errors

    manifest = {
        "artifact_schema": VERSION,
        **identity,
        "report_artifact_digest": report_artifact_digest,
        "artifact_digests": artifact_digests,
        "review": {
            "reviewer": reviewer_value,
            "decision": normalized_decision or "invalid",
            "reason": reason_value,
            "accepted_at": timestamp,
        },
        "validation_errors": errors,
        "accepted_edition": approved,
        "delivery_status": "approved_for_delivery" if approved else "blocked",
        "human_review_required": True,
        "client_delivery_allowed": approved,
    }
    canonical_manifest = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    manifest["accepted_edition_manifest_sha256"] = _sha256(canonical_manifest)
    return manifest


__all__ = ["VERSION", "build_accepted_report_edition"]
