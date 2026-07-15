from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "7101df90e04f02780ef34763ae9c98d1e40ecc8e"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Remove contradicted test-absence evidence from final report (#468)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "express_run_fae863e57088494d8c4000e1e5521257" in release_truth
    assert "Senior 92/100" in release_truth
    assert "aligned visible and detailed section scores" in release_truth
    assert "no missing release-readiness signals" in release_truth
    assert "bounded-sample metric preserved" in release_truth
    assert "human review required" in release_truth
    assert "`client_ready: false`" in release_truth


def test_release_truth_records_corrected_verification_without_rewriting_history() -> None:
    release_truth = _release_truth()

    assert "workflow run `29413945233`" in release_truth
    assert "express_run_a1a93d3a93ef49b7a81129eed86ca6a5" in release_truth
    assert "temporary assertion expected a positive cleanup count" in release_truth
    assert "fresh report was already clean" in release_truth
    assert "Historical workflow failures remain historical evidence and are not rewritten" in release_truth
