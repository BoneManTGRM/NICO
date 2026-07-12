from __future__ import annotations

from pathlib import Path


def test_retainer_auto_evidence_runbook_preserves_truth_and_safety_boundaries() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "RETAINER_AUTO_EVIDENCE.md"
    ).read_text(encoding="utf-8").lower()

    for required in [
        "post /retainer/ops",
        "/retainer-ops",
        "all current open issues without a timeframe cutoff",
        "latest observed state of each workflow",
        "verified_clear",
        "verified_blockers",
        "unverified",
        "score_calculated",
        "score unavailable",
        "explicit baseline run id",
        "fails closed",
        "does not silently substitute",
        "client delivery",
        "provider response bodies",
        "human approval",
    ]:
        assert required in text

    assert "an empty input field is not blocker evidence" in text
    assert "historical workflow failure is not kept as a current blocker" in text
    assert "operator-supplied business context alone cannot create an overall retainer score" in text
    assert "does not persist the operator's full business notes" in text
