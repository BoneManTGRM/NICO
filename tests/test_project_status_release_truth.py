from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "7cd53c94d863b2d441454f59d21c1396e9b1105d"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Keep assessment failure evidence page-scoped (#420)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "page-scoped current-request failure evidence" in release_truth
    assert "cleared before a new canonical assessment request" in release_truth
    assert "bounded exact-run failure details" in release_truth
    assert "same-origin canonical assessment transport" in release_truth
    assert "strict repository-target validation" in release_truth


def test_release_truth_does_not_overclaim_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "authorized production smoke artifact" in release_truth
    assert "matching browser evidence" in release_truth
