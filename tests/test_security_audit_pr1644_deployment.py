"""Bind a Railway-confirmed nonsecret ID; never exempt UUIDs as a class."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.security_audit_gate import _trufflehog

# Authenticated Railway metadata identifies this exact value as the 31269344
# deployment. Artifact 10864619748 retains the original scanner observation.
DEPLOYMENT_ID = "e045965c-ca52-42dc-858f-ef18bf563266"
VALUE_SHA256 = "1980b2f6dab7776d10baa4343cca6b20d8af6aaec1a99137932989a3a81fff37"


def _finding():
    return {
        "SourceMetadata": {"Data": {"Git": {"file": "NICO-Ship-Checkpoint.md"}}},
        "DetectorName": "RailwayApp", "Verified": False, "Raw": DEPLOYMENT_ID,
    }


def _evaluate(root: Path, rows: list[dict], status: str = "completed"):
    raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
    (root / "trufflehog.json").write_bytes(raw)
    (root / "trufflehog-summary.json").write_text(
        json.dumps({"status": status, "finding_count": len(rows)}), encoding="utf-8"
    )
    result = _trufflehog(root)
    assert (root / "trufflehog.json").read_bytes() == raw
    assert result["artifact_hash"] == hashlib.sha256(raw).hexdigest()
    assert DEPLOYMENT_ID not in json.dumps(result)
    assert _trufflehog(root) == result
    return result


def test_exact_deployment_observation_is_retained_not_deleted(tmp_path):
    assert hashlib.sha256(DEPLOYMENT_ID.encode()).hexdigest() == VALUE_SHA256
    result = _evaluate(tmp_path, [_finding()])
    assert result["status"] == "completed"
    assert result["finding_count"] == 1
    assert result["blocking"] == 0
    assert result["approved_nonsecret_identifiers"] == 1
    assert result["triage"][0]["disposition"] == "approved_nonsecret_deployment_identifier"


@pytest.mark.parametrize("field,value", [
    ("Verified", True), ("Verified", None), ("Verified", 0), ("Verified", 1),
    ("Verified", "false"), ("Verified", "true"), ("Verified", []), ("Verified", {}),
    ("DetectorName", "Other"), ("DetectorName", None),
    ("Raw", DEPLOYMENT_ID.upper()), ("Raw", DEPLOYMENT_ID + " "),
    ("Raw", "unreviewed-value"), ("Raw", None),
    ("SourceMetadata", {"Data": {"Git": {"file": "README.md"}}}),
    ("SourceMetadata", {"Data": {"Git": {"file": "./NICO-Ship-Checkpoint.md"}}}),
    ("SourceMetadata", {"Data": {"Git": {"file": "docs/NICO-Ship-Checkpoint.md"}}}),
])
def test_changed_identity_or_verification_still_blocks(tmp_path, field, value):
    row = _finding()
    row[field] = value
    result = _evaluate(tmp_path, [row])
    assert result["blocking"] == 1
    assert result["approved_nonsecret_identifiers"] == 0


@pytest.mark.parametrize("field", ["Verified", "DetectorName", "Raw", "SourceMetadata"])
def test_missing_evidence_still_blocks(tmp_path, field):
    row = _finding()
    del row[field]
    assert _evaluate(tmp_path, [row])["blocking"] == 1


def test_known_identifier_does_not_hide_verified_or_unknown_findings(tmp_path):
    known, verified, unknown = _finding(), _finding(), _finding()
    verified["Verified"] = True
    unknown["Raw"] = "unreviewed-value"
    result = _evaluate(tmp_path, [known, verified, unknown])
    assert result["finding_count"] == 3
    assert result["blocking"] == 2
    assert [row["disposition"] for row in result["triage"]] == [
        "approved_nonsecret_deployment_identifier", "blocking_verified_secret",
        "blocking_unverified_non_fixture",
    ]


@pytest.mark.parametrize("status", ["failed", "unavailable"])
def test_identifier_cannot_turn_failed_scanner_into_success(tmp_path, status):
    assert _evaluate(tmp_path, [_finding()], status)["status"] == "unavailable"
