from __future__ import annotations

from pathlib import Path


PROGRESS = Path("apps/web/app/assessment/assessmentProgress.ts")


def test_sparse_recovery_rejects_unknown_stage_sentinels() -> None:
    source = PROGRESS.read_text(encoding="utf-8")

    assert "INVALID_STAGE_SENTINELS" in source
    assert '"unknown_stage"' in source
    assert "normalizeStageId" in source
    assert "INVALID_STAGE_SENTINELS.has(normalized)" in source


def test_sparse_recovery_uses_completed_stage_truth_instead_of_resetting_to_one_percent() -> None:
    source = PROGRESS.read_text(encoding="utf-8")

    assert "const completed = completedStageCount(result);" in source
    assert "if (completed > 0 && completed < COMPREHENSIVE_STAGE_IDS.length)" in source
    assert "return completed;" in source
    assert "fetch(" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source


def test_progress_continuity_does_not_mutate_terminal_or_delivery_truth() -> None:
    source = PROGRESS.read_text(encoding="utf-8")

    assert 'phase === "complete" || phase === "review_required"' in source
    assert "client_delivery_allowed" not in source
    assert "human_review_required" not in source
