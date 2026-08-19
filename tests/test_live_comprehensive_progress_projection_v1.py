from __future__ import annotations

import re
from pathlib import Path

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES


ROOT = Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "apps/web/app/assessment/assessmentProgress.ts"
MODEL = ROOT / "apps/web/app/assessment/assessmentModel.ts"


def _client_stage_ids(source: str) -> list[str]:
    match = re.search(
        r"export const COMPREHENSIVE_STAGE_IDS = \[(.*?)\] as const;",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    return re.findall(r'^\s+"([a-z0-9_]+)",\s*$', match.group(1), flags=re.MULTILINE)


def test_live_progress_projection_matches_canonical_stage_order() -> None:
    source = PROGRESS.read_text(encoding="utf-8")
    assert _client_stage_ids(source) == list(COMPREHENSIVE_STAGES)


def test_live_progress_uses_all_same_run_progress_truth_before_showing_zero() -> None:
    source = PROGRESS.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")

    assert 'export {progressPercent} from "./assessmentProgress";' in model
    assert "boundedPercent(result?.progress_percent)" in source
    assert "boundedPercent(result?.record?.progress_percent)" in source
    assert "boundedPercent(top?.canonical_progress_percent)" in source
    assert "completed_stages" in source
    assert "contiguousCompleted" in source
    assert "stageIndex / totalStages" in source
    assert "active_stage_progress_percent" in source
    assert "if (running && stageIndex === 0 && display === 0) display = 1;" in source
    assert "if (running && stageIndex < 0 && display === 0) display = 1;" in source


def test_live_progress_is_presentation_only_and_bounded() -> None:
    source = PROGRESS.read_text(encoding="utf-8")

    assert "Math.max(" in source
    assert "Math.min(100, display)" in source
    assert "return 100" in source
    assert "fetch(" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
