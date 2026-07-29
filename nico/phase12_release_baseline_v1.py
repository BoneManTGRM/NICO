from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

VERSION = "nico.phase12.release-baseline.v1"
REQUIRED_PROOFS = {
    "database", "worker", "frontend", "mobile", "restart", "security", "audit", "bandit",
    "node_scanners", "report", "approval", "delivery", "rollback", "recovery",
}


class Phase12Error(ValueError):
    pass


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Phase12Error(f"{label} must be non-empty text")
    return value.strip()


def _commit_sha(value: Any, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 40 or any(ch not in "0123456789abcdef" for ch in text):
        raise Phase12Error(f"{label} must be a full commit SHA")
    return text


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise Phase12Error(f"{label} must be a SHA-256 digest")
    return text


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_release_baseline(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("schema") != VERSION:
        raise Phase12Error("unsupported Phase 12 schema")
    repository = _text(record.get("repository"), "repository")
    deployed_sha = _commit_sha(record.get("deployed_sha"), "deployed_sha")
    tested_sha = _commit_sha(record.get("tested_sha"), "tested_sha")
    reviewed_sha = _commit_sha(record.get("reviewed_sha"), "reviewed_sha")
    if len({deployed_sha, tested_sha, reviewed_sha}) != 1:
        raise Phase12Error("deployed, tested, and reviewed revisions must be identical")

    acceptance_runs = record.get("acceptance_runs")
    if not isinstance(acceptance_runs, Sequence) or isinstance(acceptance_runs, (str, bytes)) or len(acceptance_runs) < 2:
        raise Phase12Error("at least two consecutive production acceptance runs are required")
    previous_sequence = None
    for index, run in enumerate(acceptance_runs):
        if not isinstance(run, Mapping):
            raise Phase12Error("acceptance run records must be objects")
        if run.get("status") != "passed":
            raise Phase12Error(f"acceptance run {index} did not pass")
        if _commit_sha(run.get("commit_sha"), f"acceptance_runs[{index}].commit_sha") != deployed_sha:
            raise Phase12Error("acceptance run revision drift detected")
        sequence = run.get("sequence")
        if not isinstance(sequence, int):
            raise Phase12Error("acceptance run sequence must be an integer")
        if previous_sequence is not None and sequence != previous_sequence + 1:
            raise Phase12Error("acceptance runs must be consecutive")
        previous_sequence = sequence
        if run.get("manual_repair") is not False or run.get("mutation_between_runs") is not False:
            raise Phase12Error("acceptance runs must succeed without mutation or manual repair")
        _sha256(run.get("evidence_sha256"), f"acceptance_runs[{index}].evidence_sha256")

    proofs = record.get("proofs")
    if not isinstance(proofs, Sequence) or isinstance(proofs, (str, bytes)):
        raise Phase12Error("proofs must be a list")
    proof_by_name = {item.get("name"): item for item in proofs if isinstance(item, Mapping)}
    missing = REQUIRED_PROOFS - set(proof_by_name)
    if missing:
        raise Phase12Error(f"missing production proofs: {sorted(missing)}")
    for name in REQUIRED_PROOFS:
        proof = proof_by_name[name]
        if proof.get("status") != "passed":
            raise Phase12Error(f"production proof did not pass: {name}")
        if _commit_sha(proof.get("commit_sha"), f"proofs.{name}.commit_sha") != deployed_sha:
            raise Phase12Error(f"production proof revision drift: {name}")
        _sha256(proof.get("evidence_sha256"), f"proofs.{name}.evidence_sha256")

    human_review = record.get("human_review")
    if not isinstance(human_review, Mapping):
        raise Phase12Error("human_review is required")
    if human_review.get("approved") is not True:
        raise Phase12Error("a real immutable client package must be approved by a human")
    _text(human_review.get("reviewer_name"), "human_review.reviewer_name")
    _text(human_review.get("reviewer_role"), "human_review.reviewer_role")
    if human_review.get("independent") is not True:
        raise Phase12Error("release reviewer must be independent of package generation")
    if _commit_sha(human_review.get("commit_sha"), "human_review.commit_sha") != deployed_sha:
        raise Phase12Error("human review is bound to the wrong revision")
    _sha256(human_review.get("package_fingerprint"), "human_review.package_fingerprint")

    release_manifest = record.get("release_manifest")
    if not isinstance(release_manifest, Mapping):
        raise Phase12Error("release_manifest is required")
    if _commit_sha(release_manifest.get("commit_sha"), "release_manifest.commit_sha") != deployed_sha:
        raise Phase12Error("release manifest revision drift")
    _sha256(release_manifest.get("manifest_sha256"), "release_manifest.manifest_sha256")
    _text(release_manifest.get("signed_by"), "release_manifest.signed_by")
    _text(release_manifest.get("signed_at"), "release_manifest.signed_at")

    runbook = record.get("runbook")
    if not isinstance(runbook, Mapping):
        raise Phase12Error("runbook is required")
    for key in ("monitoring", "alerting", "rollback", "recovery", "support", "post_release_validation"):
        _text(runbook.get(key), f"runbook.{key}")

    tag = _text(record.get("release_tag"), "release_tag")
    if record.get("unsupported_marketing_claims_prohibited") is not True:
        raise Phase12Error("unsupported marketing claims must remain prohibited")
    if record.get("rollback_rehearsal_completed") is not True or record.get("recovery_rehearsal_completed") is not True:
        raise Phase12Error("rollback and recovery rehearsals must be complete")

    result = {
        "schema": VERSION,
        "valid": True,
        "repository": repository,
        "production_sha": deployed_sha,
        "release_tag": tag,
        "acceptance_run_count": len(acceptance_runs),
        "proof_count": len(REQUIRED_PROOFS),
        "human_review_approved": True,
        "rollback_and_recovery_rehearsed": True,
        "capability_boundary": "Release claims are limited to the tested, reviewed, and retained production baseline.",
    }
    result["baseline_sha256"] = _hash(result)
    return result


__all__ = ["VERSION", "Phase12Error", "validate_release_baseline"]
