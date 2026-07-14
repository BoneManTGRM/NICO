from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "22c68f83fdaaf666f2a3056f5ed0f81192b35c61"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Record PR 425 deployment verification (#426)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "deployment of the release-truth update through PR #426" in release_truth
    assert "direct Railway transport for long synchronous Express requests from PR #423" in release_truth
    assert "single unified assessment intake and retired duplicate Start Job wizard from PR #424" in release_truth
    assert "neutral unauthenticated Operations/Recovery presentation from PR #425" in release_truth
    assert "Loaded unavailable or failed evidence remains fail-closed and red" in release_truth


def test_release_truth_does_not_overclaim_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "authorized production smoke artifact" in release_truth
    assert "matching browser evidence" in release_truth
