from __future__ import annotations

from pathlib import Path


def test_completed_progress_stage_does_not_fall_back_to_not_verified() -> None:
    source = Path("apps/web/app/assessment/assessmentEvidence.ts").read_text(encoding="utf-8")

    for terminal in (
        '"complete"',
        '"completed"',
        '"success"',
        '"passed"',
        '"verified"',
    ):
        assert terminal in source
    assert ".includes(normalizedStatus)" in source
    assert 'message: value.message || value.summary || (completed ? "✓" : undefined)' in source
