from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "48010dd066c9c511d11951383bb2fbcdbbdff5d5"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Fix opaque Express backend execution failures (#442)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "bounded named failure stage" in release_truth
    assert "non-secret diagnostic ID" in release_truth
    assert "exception class" in release_truth
    assert "exact `express_run_*` identity" in release_truth
    assert "authorized traceback only in backend logs" in release_truth
    assert "writes the exact final run record once" in release_truth
    assert "never retries the assessment start" in release_truth
    assert "creates a replacement run" in release_truth
    assert "converts failed evidence into a pass" in release_truth
    assert "authenticated Recovery visibility" in release_truth
    assert "human review" in release_truth.lower()
    assert "`client_ready: false`" in release_truth


def test_release_truth_does_not_overclaim_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "production exception observed in `express_run_42393e95d3c84706b1eed8f042d0eacc` is resolved" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "new protected production smoke is authorized, executed once, retained, and reviewed" in release_truth
