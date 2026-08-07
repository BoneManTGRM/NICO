from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nico import candidate_lineage_migration_v1 as lineage
from nico.candidate_lineage_runtime_patch_v1 import _load_verified_baseline


EXPECTED_COMMIT = "9c876ba4e3e9bb152de52567232038e52a6bbb3e"
EXPECTED_COUNTS = {"dependency": 59, "secret": 17, "static": 586}


def test_retained_baseline_is_exact_source_bound_and_complete() -> None:
    baseline = lineage.load_default_baseline()

    assert baseline["s"] == "nico.candidate-lineage-baseline.v2"
    assert baseline["r"] == "BoneManTGRM/NICO"
    assert baseline["c"] == EXPECTED_COMMIT
    assert baseline["n"] == 662
    assert baseline["k"] == EXPECTED_COUNTS
    assert baseline["a"] == "none"
    assert len(baseline["x"]) == 662
    assert len({str(item[4]) for item in baseline["x"]}) == 662


def test_retained_baseline_chunks_are_bound_to_triage_manifest() -> None:
    root = Path(lineage.__file__).resolve().parents[1]
    source_manifest = json.loads(
        (root / "evidence" / "triage-662" / "manifest.json").read_text(encoding="utf-8")
    )
    baseline_manifest = json.loads(
        (root / "evidence" / "candidate-lineage" / "baseline-9c876ba4-chunks" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert source_manifest["candidate_count"] == 662
    assert source_manifest["counts"] == EXPECTED_COUNTS
    assert source_manifest["target_commit_sha"] == EXPECTED_COMMIT
    assert source_manifest["human_review_status"] == "pending"
    assert source_manifest["client_delivery_status"] == "blocked"
    assert baseline_manifest["source_candidate_register_sha256"] == source_manifest["artifacts"]["candidate-register.json"]
    assert baseline_manifest["approval_authority"] == "none"
    assert len(baseline_manifest["chunks"]) == 8


def test_retained_baseline_rejects_tampered_chunk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = Path(lineage.__file__).resolve().parents[1] / "evidence" / "candidate-lineage" / "baseline-9c876ba4-chunks"
    target = tmp_path / "baseline"
    shutil.copytree(source, target)
    part = target / "part-00.b64"
    part.write_text(part.read_text(encoding="ascii") + "A", encoding="ascii")

    monkeypatch.setattr(lineage, "_BASELINE_DIR", target)
    monkeypatch.setattr(lineage, "_BASELINE_MANIFEST", target / "manifest.json")

    with pytest.raises(ValueError, match="candidate_lineage_baseline_chunk_digest_invalid"):
        lineage.load_default_baseline()


def test_production_lineage_preflight_requires_verified_baseline() -> None:
    baseline, available, reason = _load_verified_baseline()

    assert available is True
    assert reason == ""
    assert baseline is not None
    assert baseline["c"] == EXPECTED_COMMIT
    assert baseline["n"] == 662
    assert baseline["a"] == "none"
