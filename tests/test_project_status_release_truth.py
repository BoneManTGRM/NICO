from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "b8aaba855a68fd33fae0260db23b81ff01b062c6"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Combine deployed browser and API production proof (#432)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "collision-resistant Express run/report identity and exact-run persistence repair from PR #430" in release_truth
    assert "protected browser-driven Express/Mid/Full production-proof workflow from PR #432" in release_truth
    assert "without duplicate API starts" in release_truth
    assert "human review" in release_truth
    assert "`client_ready: false`" in release_truth


def test_release_truth_does_not_overclaim_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "protected production smoke is authorized, executed, retained, and reviewed" in release_truth
