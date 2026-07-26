from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_defines_exact_release_and_live_acceptance_requirements() -> None:
    release_truth = _release_truth()

    assert "required repository CI" in release_truth
    assert "security analysis" in release_truth
    assert "frontend build" in release_truth
    assert "configured frontend/backend deployment checks" in release_truth
    assert "Deployment success does not prove assessment correctness." in release_truth
    assert "exact deployment identity" in release_truth
    assert "two consecutive distinct Comprehensive run IDs" in release_truth
    assert "expected immutable repository baseline" in release_truth
    assert "passing cross-format verification" in release_truth
    assert "expert review required" in release_truth
    assert "client delivery blocked before approval" in release_truth


def test_release_truth_records_a_concrete_transformation_baseline_without_claiming_maturity() -> None:
    release_truth = _release_truth()
    matches = re.findall(r"`([0-9a-f]{40})`", release_truth)

    assert matches == ["272f5ddde1e81e9f845eab0393f04a356b01d16f"]
    assert "baseline used by the current transformation branch" in release_truth
    assert "mature" not in release_truth.lower()
    assert "certified" not in release_truth.lower()
