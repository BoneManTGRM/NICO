from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "cbaa988b638f90f16663ff3b58423fa6f3bd855c"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Render unloaded operator evidence neutrally (#425)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "long-running Express requests use the configured Railway API directly" in release_truth
    assert "one canonical assessment intake" in release_truth
    assert "legacy Start Job route redirects" in release_truth
    assert "unloaded Operations and Recovery evidence is neutral" in release_truth
    assert "loaded unavailable or failed evidence remains fail-closed" in release_truth


def test_release_truth_does_not_overclaim_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "authorized production smoke artifact" in release_truth
    assert "matching browser evidence" in release_truth
