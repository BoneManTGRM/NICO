from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nico.candidate_technical_triage_v1 import load_default_technical_triage


TRIAGE_DIR = Path("evidence/candidate-triage")


def test_compact_triage_artifact_matches_retained_manifest() -> None:
    triage = load_default_technical_triage()
    manifest = json.loads(
        (TRIAGE_DIR / "manifest-9c876ba4.json").read_text(encoding="utf-8")
    )

    assert triage["c"] == manifest["assessed_commit_sha"]
    assert triage["n"] == manifest["candidate_count"]
    assert triage["source_schema"] == manifest["source_triage_schema"]
    assert triage["source_sha256"] == manifest["source_triage_sha256"]
    assert triage["h"] == manifest["human_approval_status"]
    assert triage["d"] is manifest["client_delivery_allowed"] is False
    assert triage["runtime_validation_performed"] is False


def test_compact_triage_artifact_parts_are_contiguous_and_bounded() -> None:
    parts = sorted(TRIAGE_DIR.glob("technical-triage-9c876ba4.part-*.b64"))

    assert [part.name for part in parts] == [
        f"technical-triage-9c876ba4.part-{index:02d}.b64"
        for index in range(5)
    ]
    assert all(part.stat().st_size <= 5001 for part in parts)
    assert not (TRIAGE_DIR / "technical-triage-9c876ba4.json.gz.b64").exists()


def test_manifest_source_digest_is_sha256_shaped() -> None:
    manifest = json.loads(
        (TRIAGE_DIR / "manifest-9c876ba4.json").read_text(encoding="utf-8")
    )
    digest = manifest["source_triage_sha256"]

    assert len(digest) == hashlib.sha256().digest_size * 2
    int(digest, 16)
