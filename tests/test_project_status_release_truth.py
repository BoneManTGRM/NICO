from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "46651c337fd84025af07f8ea017a2fd8c64057ab"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Fix interrupted Express assessments with exact-run polling (#436)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "one quick authorized lifecycle start" in release_truth
    assert "tenant-bound `express_run_*` identity" in release_truth
    assert "short same-origin status polling" in release_truth
    assert "duplicate-active-start prevention" in release_truth
    assert "authenticated Recovery visibility" in release_truth
    assert "without issuing duplicate starts" in release_truth
    assert "human review" in release_truth
    assert "`client_ready: false`" in release_truth


def test_release_truth_does_not_overclaim_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "protected production smoke is authorized, executed, retained, and reviewed" in release_truth
