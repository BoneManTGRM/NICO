from __future__ import annotations

from copy import deepcopy

from nico.scanner_evidence_pipeline_v1 import REQUIRED_EVIDENCE_TOOLS
from nico.scanner_evidence_qualification_v1 import compare_frozen_runs, qualify_scanner_evidence


def _artifact() -> dict:
    tools = {}
    retained = {}
    for name in REQUIRED_EVIDENCE_TOOLS:
        tools[name] = {
            "tool": name,
            "status": "completed",
            "verified_for_this_report": True,
            "output_capture_complete": True,
            "returncode_valid": True,
            "timed_out": False,
            "scans_git_history": name in {"gitleaks", "trufflehog"},
            "full_history_verified": name in {"gitleaks", "trufflehog"},
            "deterministic_fingerprint": f"fingerprint-{name}",
        }
        retained[name] = {
            "storage_key": f"repo/sha/run/{name}.json.gz",
            "sha256": f"raw-{name}",
            "gzip_sha256": f"gzip-{name}",
            "raw_format": "json",
            "redacted": True,
        }
    return {
        "tools": tools,
        "raw_artifacts": retained,
        "target_commit_sha": "abc123",
        "application_commit_sha": "abc123",
        "checkout": {"commit_sha": "abc123"},
        "provenance_verified": True,
        "worker_execution_state": "completed",
    }


def test_complete_exact_commit_evidence_is_ready() -> None:
    artifact = _artifact()
    qualification = qualify_scanner_evidence(artifact)
    assert qualification["ready"] is True
    assert qualification["blocking_tools"] == []
    assert artifact["scanner_evidence_ready"] is True


def test_missing_retained_artifact_blocks_readiness() -> None:
    artifact = _artifact()
    artifact["raw_artifacts"].pop("bandit")
    qualification = qualify_scanner_evidence(artifact)
    assert qualification["ready"] is False
    assert "bandit" in qualification["blocking_tools"]
    assert "retained_artifact_missing" in qualification["tool_readiness"]["bandit"]["blockers"]
    assert artifact["worker_execution_state"] == "partial"
    assert artifact["human_review_required"] is True


def test_commit_mismatch_blocks_readiness() -> None:
    artifact = _artifact()
    artifact["checkout"]["commit_sha"] = "different"
    qualification = qualify_scanner_evidence(artifact)
    assert qualification["ready"] is False
    assert "checkout_commit_mismatch" in qualification["provenance"]["blockers"]


def test_repeatability_requires_identical_fingerprints() -> None:
    first = _artifact()
    second = deepcopy(first)
    assert compare_frozen_runs(first, second)["equivalent"] is True
    second["tools"]["eslint"]["deterministic_fingerprint"] = "changed"
    comparison = compare_frozen_runs(first, second)
    assert comparison["equivalent"] is False
    assert comparison["fingerprint_mismatches"] == ["eslint"]
