"""Exact nonsecret deployment-ID disposition; no blanket secret exemptions."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.security_audit_gate import _trufflehog

# Railway deployment metadata identifies this as the replaced d5b3de33 deployment.
# The matching observation is in Actions artifact 10717384136, not a credential.
DEPLOYMENT_ID = "ce6af1c6-c767-425a-b442-26c8e83aa29b"
VALUE_SHA256 = "ef9eb96c9686e4314a4a0dfed94e8c026ca73e7e350895ac129ce57164da3d10"


def _finding() -> dict:
    return {
        "SourceMetadata": {"Data": {"Git": {"file": "NICO-Ship-Checkpoint.md"}}},
        "DetectorName": "RailwayApp",
        "Verified": False,
        "Raw": DEPLOYMENT_ID,
    }


def _write(root: Path, findings: list[dict], *, status: str = "completed") -> bytes:
    raw = "".join(json.dumps(row) + "\n" for row in findings).encode()
    (root / "trufflehog.json").write_bytes(raw)
    (root / "trufflehog-summary.json").write_text(
        json.dumps({"status": status, "finding_count": len(findings)}), encoding="utf-8"
    )
    return raw


def test_exact_retired_deployment_is_retained_without_exposing_value(tmp_path: Path) -> None:
    finding = _finding()
    before = deepcopy(finding)
    raw = _write(tmp_path, [finding])
    result = _trufflehog(tmp_path)
    assert hashlib.sha256(DEPLOYMENT_ID.encode()).hexdigest() == VALUE_SHA256
    assert result["status"] == "completed"
    assert result["finding_count"] == 1
    assert result["blocking"] == 0
    assert result["approved_nonsecret_identifiers"] == 1
    assert result["triage"][0]["disposition"] == "approved_nonsecret_deployment_identifier"
    assert result["artifact_hash"] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / "trufflehog.json").read_bytes() == raw
    assert finding == before
    assert DEPLOYMENT_ID not in json.dumps(result)


@pytest.mark.parametrize("verified", [True, None, 0, 1, "false", "true", "", [], {}])
def test_other_verification_states_still_block(tmp_path: Path, verified: object) -> None:
    finding = _finding()
    finding["Verified"] = verified
    _write(tmp_path, [finding])
    result = _trufflehog(tmp_path)
    assert result["blocking"] == 1
    assert result["approved_nonsecret_identifiers"] == 0


@pytest.mark.parametrize("missing", ["Verified", "Raw", "DetectorName", "SourceMetadata"])
def test_missing_identity_evidence_still_blocks(tmp_path: Path, missing: str) -> None:
    finding = _finding()
    del finding[missing]
    _write(tmp_path, [finding])
    assert _trufflehog(tmp_path)["blocking"] == 1


@pytest.mark.parametrize("path", [
    "nico/settings.py", "docs/operator-report-approval.md",
    "docs/human-report-repair-acceptance.md", "./NICO-Ship-Checkpoint.md",
    "nico-ship-checkpoint.md", "another-checkpoint.md",
])
def test_same_value_in_other_nonfixture_paths_still_blocks(tmp_path: Path, path: str) -> None:
    finding = _finding()
    finding["SourceMetadata"] = {"Data": {"Git": {"file": path}}}
    _write(tmp_path, [finding])
    assert _trufflehog(tmp_path)["blocking"] == 1


@pytest.mark.parametrize("detector", ["Other", "Postgres", "", None])
def test_other_detectors_still_block(tmp_path: Path, detector: object) -> None:
    finding = _finding()
    finding["DetectorName"] = detector
    _write(tmp_path, [finding])
    assert _trufflehog(tmp_path)["blocking"] == 1


@pytest.mark.parametrize("value", [
    "unreviewed-value", DEPLOYMENT_ID.upper(), DEPLOYMENT_ID[:-1] + "c",
])
def test_other_values_still_block(tmp_path: Path, value: str) -> None:
    finding = _finding()
    finding["Raw"] = value
    _write(tmp_path, [finding])
    assert _trufflehog(tmp_path)["blocking"] == 1


def test_mixed_population_retains_verified_and_unknown_blockers(tmp_path: Path) -> None:
    known, verified, unknown = _finding(), _finding(), _finding()
    verified["Verified"] = True
    unknown["Raw"] = "unreviewed-value"
    raw = _write(tmp_path, [known, verified, unknown])
    result = _trufflehog(tmp_path)
    assert result["finding_count"] == 3
    assert result["blocking"] == 2
    assert result["approved_nonsecret_identifiers"] == 1
    assert [row["disposition"] for row in result["triage"]] == [
        "approved_nonsecret_deployment_identifier", "blocking_verified_secret",
        "blocking_unverified_non_fixture",
    ]
    assert result["artifact_hash"] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / "trufflehog.json").read_bytes() == raw


@pytest.mark.parametrize("status", ["failed", "unavailable"])
def test_known_identifier_cannot_make_incomplete_scanner_pass(tmp_path: Path, status: str) -> None:
    _write(tmp_path, [_finding()], status=status)
    assert _trufflehog(tmp_path)["status"] == "unavailable"
