from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nico.candidate_technical_triage_v1 import load_default_technical_triage


def test_compact_triage_artifact_matches_retained_manifest() -> None:
    triage = load_default_technical_triage()
    manifest = json.loads(
        Path("evidence/candidate-triage/manifest-9c876ba4.json").read_text(
            encoding="utf-8"
        )
    )

    assert triage["c"] == manifest["assessed_commit_sha"]
    assert triage["n"] == manifest["candidate_count"]
    assert triage["source_schema"] == manifest["source_triage_schema"]
    assert triage["source_sha256"] == manifest["source_triage_sha256"]
    assert triage["h"] == manifest["human_approval_status"]
    assert triage["d"] is manifest["client_delivery_allowed"] is False
    assert triage["runtime_validation_performed"] is False


def test_manifest_source_digest_is_sha256_shaped() -> None:
    manifest = json.loads(
        Path("evidence/candidate-triage/manifest-9c876ba4.json").read_text(
            encoding="utf-8"
        )
    )
    digest = manifest["source_triage_sha256"]

    assert len(digest) == hashlib.sha256().digest_size * 2
    int(digest, 16)
