from __future__ import annotations

from pathlib import Path


def test_canonical_workspace_copy_is_not_rewritten_after_hydration() -> None:
    guard = Path("apps/web/app/UnifiedAssessmentPublicGuard.tsx").read_text(encoding="utf-8")
    workspace = Path("apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")
    hydration = Path("apps/web/app/assessment/AssessmentHydrationContract.tsx").read_text(encoding="utf-8")

    canonical_check = 'if (main.dataset.assessmentCopyContract === CANONICAL_COPY_CONTRACT) return;'
    assert 'const CANONICAL_COPY_CONTRACT = "expert-engagement-v2";' in guard
    assert canonical_check in guard
    assert guard.index(canonical_check) < guard.index('Complete technical and strategic diligence')
    assert 'data-assessment-copy-contract="expert-engagement-v2"' in workspace
    assert 'action: "Create engagement and capture repository snapshot"' in hydration
    assert 'heading: "Create assessment engagement"' in hydration
