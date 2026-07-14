from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"
LATEST_DEPLOYED_MAIN = "c9dab99a47d6d4b0dc924b695ef8d0880277950c"


def _release_truth() -> str:
    text = STATUS_PATH.read_text(encoding="utf-8")
    return text.split("## Current release truth", 1)[1].split("## Claims NICO does not make", 1)[0]


def test_release_truth_records_latest_verified_main_deployment() -> None:
    release_truth = _release_truth()

    assert LATEST_DEPLOYED_MAIN in release_truth
    assert "Restore exact Express run and report identity (#430)" in release_truth
    assert "Vercel and Railway deployment checks passed" in release_truth
    assert "bounded long-running Express smoke timeout from PR #428" in release_truth
    assert "collision-resistant Express run identity" in release_truth
    assert "deterministic report identity" in release_truth
    assert "exact-run final-review target" in release_truth
    assert "final returned-payload persistence contract from PR #430" in release_truth
    assert "Explicit existing identities remain authoritative" in release_truth
    assert "request-local payload state is consumed once" in release_truth
    assert "human review and non-client-ready boundaries remain unchanged" in release_truth


def test_release_truth_does_not_overclaim_production_assessment_proof() -> None:
    release_truth = _release_truth()

    assert "does not prove that any Express, Mid, or Full production assessment completed correctly" in release_truth
    assert "Deployed browser/API E2E proof remains incomplete" in release_truth
    assert "authorized production smoke artifact" in release_truth
    assert "matching browser evidence" in release_truth
