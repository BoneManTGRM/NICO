from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "nico" / "express_repository_stage_watchdog.py"
PERSISTENCE = ROOT / "nico" / "express_progress_persistence_patch.py"


def test_repository_stage_has_heartbeat_without_false_cancellation() -> None:
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "_HEARTBEAT_SECONDS = 15" in source
    assert "_EXPECTED_STAGE_SECONDS = 900" in source
    assert "progress_percent=53" in source
    assert '"backend_task_active": True' in source
    assert '"stage_overdue": elapsed >= _EXPECTED_STAGE_SECONDS' in source
    assert "future.cancel()" not in source
    assert "ThreadPoolExecutor" not in source
    assert "raise TimeoutError" not in source


def test_watchdog_preserves_exact_run_and_prevents_duplicate_start() -> None:
    source = WATCHDOG.read_text(encoding="utf-8")
    assert '"same_run_continuation": True' in source
    assert '"duplicate_start_allowed": False' in source
    assert '"synthetic_progress_allowed": False' in source
    assert '"authoritative_task_runs_inline": True' in source
    assert '"zombie_assessment_possible": False' in source
    assert "_CONTEXT.run_id = run_id" in source


def test_watchdog_wraps_both_repository_execution_paths() -> None:
    source = WATCHDOG.read_text(encoding="utf-8")
    assert '"run_github_assessment"' in source
    assert '"run_github_assessment_with_scanner_artifacts"' in source
    assert "_run_with_watchdog" in source


def test_watchdog_is_installed_with_progress_persistence() -> None:
    source = PERSISTENCE.read_text(encoding="utf-8")
    assert "install_express_repository_stage_watchdog" in source
    assert '"repository_stage_watchdog": watchdog' in source
