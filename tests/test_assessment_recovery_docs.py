from __future__ import annotations

from pathlib import Path


def test_assessment_recovery_runbook_preserves_identity_and_human_control() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "ASSESSMENT_RECOVERY.md"
    ).read_text(encoding="utf-8").lower()

    for required in [
        "nico_assessment_recovery_stale_seconds",
        "get /operations/recovery/assessments",
        "post /operations/recovery/assessment/{run_id}/resume",
        "x-nico-admin-token",
        "atomic compare-and-set",
        "same run id",
        "deterministic report and approval identities",
        "assessment_recovery_queue_clear",
        "does not resume any run",
        "memory fallback is never represented as restart-safe",
        "client delivery",
    ]:
        assert required in text

    assert "raw exception text is not returned" in text
    assert "it does not yet prove" in text
    assert "scheduled backup creation" in text
    assert "restore execution" in text
