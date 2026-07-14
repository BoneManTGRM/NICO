from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "721f45b154025bb037f1ddda4e1a8ddca11a0762"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Localize the shared Spanish navigation menu (#405)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "shared `/es-mx` navigation localization" in release_truth


def test_release_truth_does_not_overclaim_localization_or_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that every operator surface is localized" in release_truth
    assert "any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "authorized production smoke artifact" in release_truth
    assert "matching browser evidence" in release_truth
