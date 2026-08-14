from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps/web/app/assessment"
HOOK = (ASSESSMENT / "useAssessmentRun.ts").read_text(encoding="utf-8")
PERSISTENCE = (ASSESSMENT / "assessmentRunPersistence.ts").read_text(encoding="utf-8")
WORKSPACE = (ASSESSMENT / "AssessmentWorkspace.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "apps/web/styles/assessment-mobile-stability.css").read_text(encoding="utf-8")
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")


def test_terminal_runs_stop_being_active_jobs() -> None:
    assert "export function readStoredRun" in PERSISTENCE
    assert "export function readPersistedRun" in PERSISTENCE
    assert HOOK.count("clearPersistedRun(true);") == 2
    assert "const persisted = readPersistedRun();" in HOOK
    assert "activeContinuationRunId.current === persisted.runId" in HOOK
    assert "const stable = terminal(service, recovered)" in HOOK
    assert 'setResult({\n      run_id: persisted.runId' not in HOOK


def test_new_assessment_clears_stale_identity() -> None:
    assert "function startNew(): void" in HOOK
    assert "url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);" in PERSISTENCE
    assert 'async function run(): Promise<void> {\n    clearPersistedRun(false);' in HOOK
    start_new = HOOK.split("function startNew(): void", 1)[1].split(
        "async function retry()", 1
    )[0]
    assert 'activeContinuationRunId.current = ""' in start_new
    assert "publishResult(null);" in start_new
    assert "latestResult.current = visible;" in HOOK
    assert "setResult(visible);" in HOOK


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
