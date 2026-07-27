from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = (ROOT / "apps/web/app/assessment/useAssessmentRun.ts").read_text(encoding="utf-8")
WORKSPACE = (ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "apps/web/styles/assessment-mobile-stability.css").read_text(encoding="utf-8")
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")


def test_terminal_runs_stop_being_active_jobs() -> None:
    assert "function readStoredRun(): PersistedRun | null" in HOOK
    assert HOOK.count("clearPersistedRun(true);") == 2
    assert "const persisted = readStoredRun();" in HOOK
    assert "Safari resume events must not restart completed reports" in HOOK


def test_new_assessment_clears_stale_identity() -> None:
    assert "function startNew(): void" in HOOK
    assert "url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);" in HOOK
    assert 'async function run(): Promise<void> {\n    clearPersistedRun(false);' in HOOK
    assert "setResult(null);" in HOOK


def test_terminal_actions_preserve_scroll() -> None:
    assert WORKSPACE.count("restoreArtifactScroll(scrollTop);") == 2
    assert 'data-assessment-terminal-actions="true"' in WORKSPACE
    assert "Start new assessment" in WORKSPACE
    assert "Iniciar una nueva evaluación" in WORKSPACE
    assert "overflow-anchor: none !important" in CSS


def test_live_browser_proof_rejects_stale_terminal_recovery() -> None:
    assert "expect_active_storage=False" in PROOF
    assert "Terminal run remained active in localStorage" in PROOF
    assert "Terminal pageshow restarted exact-run recovery" in PROOF
    assert 'terminal_pageshow_recovery_absent": True' in PROOF
    assert 'terminal_scroll_position_preserved": True' in PROOF
