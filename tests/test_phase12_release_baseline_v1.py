from __future__ import annotations

import pytest

from nico.phase12_release_baseline_v1 import VERSION, Phase12Error, validate_release_baseline

SHA = "a" * 40
DIGEST = "b" * 64
PROOFS = (
    "database", "worker", "frontend", "mobile", "restart", "security", "audit", "bandit",
    "node_scanners", "report", "approval", "delivery", "rollback", "recovery"
)


def _record() -> dict:
    return {
        "schema": VERSION,
        "repository": "BoneManTGRM/NICO",
        "deployed_sha": SHA,
        "tested_sha": SHA,
        "reviewed_sha": SHA,
        "acceptance_runs": [
            {
                "sequence": index,
                "status": "passed",
                "commit_sha": SHA,
                "manual_repair": False,
                "mutation_between_runs": False,
                "evidence_sha256": DIGEST,
            }
            for index in (1, 2)
        ],
        "proofs": [
            {"name": name, "status": "passed", "commit_sha": SHA, "evidence_sha256": DIGEST}
            for name in PROOFS
        ],
        "human_review": {
            "approved": True,
            "reviewer_name": "Independent Reviewer",
            "reviewer_role": "Release Approver",
            "independent": True,
            "commit_sha": SHA,
            "package_fingerprint": DIGEST,
        },
        "release_manifest": {
            "commit_sha": SHA,
            "manifest_sha256": DIGEST,
            "signed_by": "Release Approver",
            "signed_at": "2026-07-28T00:00:00Z",
        },
        "runbook": {
            "monitoring": "Production metrics",
            "alerting": "Alert routes",
            "rollback": "Rollback procedure",
            "recovery": "Recovery procedure",
            "support": "Support procedure",
            "post_release_validation": "Post-release checks",
        },
        "release_tag": "nico-production-v1",
        "unsupported_marketing_claims_prohibited": True,
        "rollback_rehearsal_completed": True,
        "recovery_rehearsal_completed": True,
    }


def test_complete_release_baseline_passes() -> None:
    result = validate_release_baseline(_record())
    assert result["valid"] is True
    assert result["acceptance_run_count"] == 2
    assert len(result["baseline_sha256"]) == 64


def test_revision_drift_fails() -> None:
    record = _record()
    record["reviewed_sha"] = "c" * 40
    with pytest.raises(Phase12Error, match="identical"):
        validate_release_baseline(record)


def test_nonconsecutive_acceptance_runs_fail() -> None:
    record = _record()
    record["acceptance_runs"][1]["sequence"] = 3
    with pytest.raises(Phase12Error, match="consecutive"):
        validate_release_baseline(record)


def test_manual_repair_between_acceptance_runs_fails() -> None:
    record = _record()
    record["acceptance_runs"][1]["manual_repair"] = True
    with pytest.raises(Phase12Error, match="manual repair"):
        validate_release_baseline(record)


def test_missing_bandit_proof_fails() -> None:
    record = _record()
    record["proofs"] = [proof for proof in record["proofs"] if proof["name"] != "bandit"]
    with pytest.raises(Phase12Error, match="missing production proofs"):
        validate_release_baseline(record)


def test_unapproved_human_package_fails() -> None:
    record = _record()
    record["human_review"]["approved"] = False
    with pytest.raises(Phase12Error, match="approved by a human"):
        validate_release_baseline(record)


def test_missing_rehearsal_fails() -> None:
    record = _record()
    record["rollback_rehearsal_completed"] = False
    with pytest.raises(Phase12Error, match="rehearsals"):
        validate_release_baseline(record)
