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


def test_only_verified_exact_engagement_metadata_overwrites_restored_literals() -> None:
    assert "function validEngagementMetadata" in HOOK
    assert 'metadata.artifact_schema === "nico.comprehensive_engagement_metadata.v1"' in HOOK
    assert "if (validEngagementMetadata(direct)) return direct;" in HOOK
    assert "return validEngagementMetadata(retained) ? retained : null;" in HOOK


def test_url_bound_run_stays_locked_when_first_recovery_read_fails() -> None:
    assert "protectedRunId: string;" in HOOK
    assert "setProtectedRunId(persisted.runId);" in HOOK
    assert "setProtectedRunId(runId);" in HOOK
    assert "setProtectedRunId(\"\");" in HOOK
    assert "protectedRunId || result?.run_id" in WORKSPACE
    assert "{protectedRunId ? <button" in WORKSPACE


def test_invalid_status_metadata_cannot_erase_exact_local_fallback() -> None:
    assert "exactFallback?: PersistedRun" in HOOK
    assert "const fallback = stored?.runId === runId ? stored : null;" in HOOK
    assert "fallback?.primaryTechnicalContact" in HOOK
    assert "fallback?.accessMethod" in HOOK
    assert "fallback?.authorizedScope" in HOOK
    assert "persistExactRun(recovered, scope, persisted.startedAt, persisted);" in HOOK


def test_new_assessment_clears_stale_identity() -> None:
    assert "function startNew(): void" in HOOK
    assert "url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);" in PERSISTENCE
    run = HOOK.split("async function run(): Promise<void>", 1)[1].split(
        "function startNew(): void", 1
    )[0]
    assert "exactRunId(latestResult.current) || readPersistedRun()?.runId" in run
    assert run.index("readPersistedRun()?.runId") < run.index("clearPersistedRun(false);")
    assert "clearPersistedRun(false);" in HOOK.split("function startNew(): void", 1)[1]
    start_new = HOOK.split("function startNew(): void", 1)[1].split(
        "async function retry()", 1
    )[0]
    assert 'activeContinuationRunId.current = ""' in start_new
    assert "publishResult(null);" in start_new
    assert "latestResult.current = visible;" in HOOK
    assert "setResult(visible);" in HOOK


def test_terminal_actions_preserve_scroll() -> None:
    # Markdown copy, pending-review PDF, and exact accepted-edition PDF each
    # preserve the completed-run viewport after their artifact action.
    assert WORKSPACE.count("restoreArtifactScroll(scrollTop);") == 3
    assert 'data-assessment-terminal-actions="true"' in WORKSPACE
    assert "Start new assessment" in WORKSPACE
    assert "Iniciar una nueva evaluación" in WORKSPACE
    assert "overflow-anchor: none !important" in CSS


def test_live_browser_proof_rejects_stale_terminal_recovery() -> None:
    assert "expect_active_storage=False" in PROOF
    assert "Terminal run remained active in localStorage" in PROOF
    assert 'clean_context_reopen_verified": True' in PROOF
    assert 'terminal_visibility_transitions": ["hidden", "visible"]' in PROOF
    assert 'terminal_observation_at_least_90_seconds": True' in PROOF


def test_live_browser_proof_measures_the_terminal_run_heading_geometry() -> None:
    assert "const runHeader = state?.querySelector(':scope > .section-head')" in PROOF
    assert "const runStatus = runHeader?.querySelector(':scope > .status')" in PROOF
    assert "const runHeading = state?.querySelector(':scope > .section-head h2')" in PROOF
    assert "run_header:" in PROOF
    assert "flex_direction: runHeaderStyle?.flexDirection" in PROOF
    assert "status_right: runStatusRect?.right" in PROOF
    assert "run_heading:" in PROOF
    assert "scroll_width: runHeading?.scrollWidth" in PROOF
    assert "parent_client_width: runHeadingParent?.clientWidth" in PROOF
    assert 'heading.get("right"' in PROOF
    assert 'heading.get("scroll_width"' in PROOF
    assert 'heading.get("parent_client_width"' in PROOF
    assert 'header.get("flex_direction") == "column"' in PROOF
    assert 'header.get("status_right"' in PROOF


def test_live_browser_proof_reports_bounded_global_overflow_offenders() -> None:
    assert "const visibleBodyElements" in PROOF
    assert "viewport_overflowing_elements" in PROOF
    assert "intrinsic_overflow_elements" in PROOF
    assert ".slice(0, 20)" in PROOF
    assert "data_keys" in PROOF
