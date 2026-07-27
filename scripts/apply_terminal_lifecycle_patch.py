#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "apps/web/app/assessment/useAssessmentRun.ts"
WORKSPACE = ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx"
MOBILE_CSS = ROOT / "apps/web/styles/assessment-mobile-stability.css"
PROOF = ROOT / "scripts/mobile_restart_live_acceptance_v1.py"
TEST = ROOT / "tests/test_terminal_run_lifecycle_and_scroll_v1.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def patch_hook() -> None:
    source = HOOK.read_text(encoding="utf-8")
    if "function startNew(): void" in source:
        return
    source = replace_once(source, "  retry: () => Promise<void>;\n};", "  retry: () => Promise<void>;\n  startNew: () => void;\n};", "controller")
    source = replace_once(source, '''function readPersistedRun(): PersistedRun | null {
  if (typeof window === "undefined") return null;
  let stored: PersistedRun | null = null;
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    stored = raw ? normalizePersistedRun(JSON.parse(raw)) : null;
  } catch {
    stored = null;
  }
  const urlRunId = new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY)?.trim() || "";
  if (!urlRunId) return stored;
  if (stored?.runId === urlRunId) return stored;
  return {
    version: 1,
    runId: urlRunId,
    repository: stored?.repository || "",
    client: stored?.client || "",
    project: stored?.project || "",
    customerId: stored?.customerId || "default_customer",
    projectId: stored?.projectId || "default_project",
    startedAt: stored?.startedAt || Date.now(),
    locale: stored?.locale || "en",
  };
}

function writePersistedRun(value: PersistedRun): void {''', '''function readStoredRun(): PersistedRun | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    return raw ? normalizePersistedRun(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

function readPersistedRun(): PersistedRun | null {
  if (typeof window === "undefined") return null;
  const stored = readStoredRun();
  const urlRunId = new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY)?.trim() || "";
  if (!urlRunId) return stored;
  if (stored?.runId === urlRunId) return stored;
  return {
    version: 1,
    runId: urlRunId,
    repository: stored?.repository || "",
    client: stored?.client || "",
    project: stored?.project || "",
    customerId: stored?.customerId || "default_customer",
    projectId: stored?.projectId || "default_project",
    startedAt: stored?.startedAt || Date.now(),
    locale: stored?.locale || "en",
  };
}

function clearPersistedRun(preserveExplicitUrl = false): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
  } catch {
    // URL cleanup remains the authoritative escape from a stale active job.
  }
  if (preserveExplicitUrl) return;
  const url = new URL(window.location.href);
  url.searchParams.set("tier", "comprehensive");
  url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function writePersistedRun(value: PersistedRun): void {''', "storage lifecycle")
    source = replace_once(source, '''    const restoreAfterPageResume = () => {
      const persisted = readPersistedRun();
      if (!persisted || recoveryInFlight.current) return;
      void resumePersistedRun(persisted);
    };''', '''    const restoreAfterPageResume = () => {
      // Only unfinished work remains active. Explicit terminal URLs can still be
      // reloaded, but Safari resume events must not restart completed reports.
      const persisted = readStoredRun();
      if (!persisted || recoveryInFlight.current) return;
      void resumePersistedRun(persisted);
    };''', "resume source")
    source = replace_once(source, '''      if (stable) {
        setPhase(stable);
        setAttempt(count);''', '''      if (stable) {
        clearPersistedRun(true);
        setPhase(stable);
        setAttempt(count);''', "terminal continuation")
    source = replace_once(source, '''      if (stable) {
        setPhase(stable);
        setStarted(null);''', '''      if (stable) {
        clearPersistedRun(true);
        setPhase(stable);
        setStarted(null);''', "terminal recovery")
    source = replace_once(source, '''  async function run(): Promise<void> {
    if (!authorized) {''', '''  async function run(): Promise<void> {
    clearPersistedRun(false);
    if (!authorized) {''', "new run cleanup")
    source = replace_once(source, '''  async function retry(): Promise<void> {
    const persisted = readPersistedRun();''', '''  function startNew(): void {
    sequence.current += 1;
    recoveryInFlight.current = false;
    clearPersistedRun(false);
    setRepository("");
    setClient("");
    setProject("");
    setAuthorized(false);
    setHumanEvidence({});
    setPhase("idle");
    setResult(null);
    setMessage("");
    setError("");
    setIssue(null);
    setAttempt(0);
    setStarted(null);
    setElapsed(0);
    window.requestAnimationFrame(() => window.scrollTo({top: 0, behavior: "auto"}));
  }

  async function retry(): Promise<void> {
    const persisted = readPersistedRun();''', "start new")
    source = replace_once(source, '''    run,
    retry,
  };''', '''    run,
    retry,
    startNew,
  };''', "return startNew")
    HOOK.write_text(source, encoding="utf-8")


def patch_workspace() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    if 'data-assessment-terminal-actions="true"' in source:
        return
    source = replace_once(source, '''function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);''', '''function restoreArtifactScroll(scrollTop: number): void {
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => window.scrollTo({top: scrollTop, behavior: "auto"}));
  });
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);''', "scroll helper")
    source = replace_once(source, '''    run,
    retry,
  } = controller;''', '''    run,
    retry,
    startNew,
  } = controller;''', "controller destructure")
    source = replace_once(source, '''  const artifactStatus = artifactAction
    ? locale === "es-MX" ? "Preparando el archivo…" : "Preparing file…"
    : "";''', '''  const artifactStatus = artifactAction
    ? locale === "es-MX" ? "Preparando el archivo…" : "Preparing file…"
    : "";
  const terminalView = ["review_required", "complete", "failed", "timed_out"].includes(phase);''', "terminal view")
    source = replace_once(source, '''  async function copyMarkdown(): Promise<void> {
    if (!markdownAvailable || artifactAction) return;
    setArtifactAction("markdown");''', '''  async function copyMarkdown(): Promise<void> {
    if (!markdownAvailable || artifactAction) return;
    const scrollTop = window.scrollY;
    (document.activeElement as HTMLElement | null)?.blur();
    setArtifactAction("markdown");''', "copy capture")
    source = replace_once(source, '''    } finally {
      setArtifactAction(null);
    }
  }

  async function downloadPdf(): Promise<void> {''', '''    } finally {
      setArtifactAction(null);
      restoreArtifactScroll(scrollTop);
    }
  }

  async function downloadPdf(): Promise<void> {''', "copy restore")
    source = replace_once(source, '''  async function downloadPdf(): Promise<void> {
    if (!pdfAvailable || artifactAction) return;
    setArtifactAction("pdf");''', '''  async function downloadPdf(): Promise<void> {
    if (!pdfAvailable || artifactAction) return;
    const scrollTop = window.scrollY;
    (document.activeElement as HTMLElement | null)?.blur();
    setArtifactAction("pdf");''', "pdf capture")
    source = replace_once(source, '''    } finally {
      setArtifactAction(null);
    }
  }

  return <main''', '''    } finally {
      setArtifactAction(null);
      restoreArtifactScroll(scrollTop);
    }
  }

  return <main''', "pdf restore")
    source = replace_once(source, '''        <div className={`report-actions ${workspaceStyles.reportActionBar}`} data-assessment-report-actions="true" data-assessment-report-ready={reportReady ? "true" : "false"}><button type="button" disabled={!markdownAvailable || artifactAction !== null} onClick={copyMarkdown}>{copy.copy}</button><button type="button" disabled={!pdfAvailable || artifactAction !== null} onClick={downloadPdf}>{copy.download}</button>{copied ? <span className="muted">{copy.copied}</span> : artifactStatus ? <span className="muted" role="status">{artifactStatus}</span> : null}</div>
        {phase === "review_required" ?''', '''        <div className={`report-actions ${workspaceStyles.reportActionBar}`} data-assessment-report-actions="true" data-assessment-report-ready={reportReady ? "true" : "false"}><button type="button" disabled={!markdownAvailable || artifactAction !== null} onClick={copyMarkdown}>{copy.copy}</button><button type="button" disabled={!pdfAvailable || artifactAction !== null} onClick={downloadPdf}>{copy.download}</button>{copied ? <span className="muted">{copy.copied}</span> : artifactStatus ? <span className="muted" role="status">{artifactStatus}</span> : null}</div>
        {terminalView ? <div className={workspaceStyles.terminalActions} data-assessment-terminal-actions="true"><button type="button" onClick={startNew}>{locale === "es-MX" ? "Iniciar una nueva evaluación" : "Start new assessment"}</button></div> : null}
        {phase === "review_required" ?''', "terminal action")
    WORKSPACE.write_text(source, encoding="utf-8")


def patch_css() -> None:
    source = MOBILE_CSS.read_text(encoding="utf-8")
    if "Terminal interactions must not become Safari scroll anchors" in source:
        return
    addition = '''

  /* Terminal interactions must not become Safari scroll anchors. */
  main[data-workspace="assessment"] [data-assessment-run-state="true"],
  main[data-workspace="assessment"] [data-assessment-report-actions="true"],
  main[data-workspace="assessment"] [data-assessment-terminal-actions="true"] {
    overflow-anchor: none !important;
  }

  main[data-workspace="assessment"] [data-assessment-terminal-actions="true"] button {
    width: 100%;
    min-height: 48px;
    border: 1px solid rgba(103, 232, 249, 0.52);
    border-radius: 12px;
    background: #082f49;
    color: #cffafe;
    font: inherit;
    font-weight: 700;
  }
'''
    index = source.rfind("\n}")
    if index < 0:
        raise RuntimeError("mobile media block not found")
    MOBILE_CSS.write_text(source[:index] + addition + source[index:], encoding="utf-8")


def patch_proof() -> None:
    source = PROOF.read_text(encoding="utf-8")
    if "terminal_pageshow_recovery_absent" in source:
        return
    source = replace_once(source, '''def _reload_and_restore(page: Page, run_id: str, timeout_ms: int) -> dict[str, Any]:
    page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
    page.locator(WORKSPACE_SELECTOR).first.wait_for(state="visible", timeout=timeout_ms)
    state = _wait_for_same_run_ui(page, run_id, min(120.0, timeout_ms / 1000.0))
    stored = _stored_run(page)
    assert stored.get("run_id") == run_id
    assert stored.get("url_run_id") == run_id
    return {"ui": state, "stored": stored}''', '''def _reload_and_restore(page: Page, run_id: str, timeout_ms: int, *, expect_active_storage: bool) -> dict[str, Any]:
    page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
    page.locator(WORKSPACE_SELECTOR).first.wait_for(state="visible", timeout=timeout_ms)
    state = _wait_for_same_run_ui(page, run_id, min(120.0, timeout_ms / 1000.0))
    stored = _stored_run(page)
    if expect_active_storage:
        assert stored.get("run_id") == run_id
    else:
        assert not stored.get("run_id"), f"Terminal run remained active in localStorage: {stored}"
    assert stored.get("url_run_id") == run_id
    return {"ui": state, "stored": stored}''', "reload contract")
    source = replace_once(source, '''        running_reload = _reload_and_restore(page, run_id, args.navigation_timeout_ms)''', '''        running_reload = _reload_and_restore(page, run_id, args.navigation_timeout_ms, expect_active_storage=True)''', "running reload")
    source = replace_once(source, '''        terminal_reload = _reload_and_restore(page, run_id, args.navigation_timeout_ms)
        terminal_after_reload = _wait_for_terminal(page, run_id, 120.0)''', '''        terminal_storage = _stored_run(page)
        assert not terminal_storage.get("run_id"), terminal_storage
        assert terminal_storage.get("url_run_id") == run_id
        terminal_reload = _reload_and_restore(page, run_id, args.navigation_timeout_ms, expect_active_storage=False)
        terminal_after_reload = _wait_for_terminal(page, run_id, 120.0)''', "terminal reload")
    source = replace_once(source, '''        artifacts = _verify_manifest_and_pdf(page, args.frontend_url.rstrip("/"), run_id)
        screenshot_path = args.output.with_suffix(".png")''', '''        actions = page.locator(REPORT_ACTIONS_SELECTOR).first
        actions.scroll_into_view_if_needed(timeout=args.navigation_timeout_ms)
        page.wait_for_timeout(250)
        scroll_before_resume = float(page.evaluate("() => window.scrollY"))
        status_before = sum(1 for item in requests if item.get("method") == "GET" and item.get("path", "").endswith(run_id))
        page.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
        page.wait_for_timeout(750)
        scroll_after_resume = float(page.evaluate("() => window.scrollY"))
        terminal_after_pageshow = _ui_state(page)
        status_after = sum(1 for item in requests if item.get("method") == "GET" and item.get("path", "").endswith(run_id))
        assert terminal_after_pageshow.get("run_id") == run_id
        assert terminal_after_pageshow.get("phase") in TERMINAL_PHASES
        assert abs(scroll_after_resume - scroll_before_resume) <= 2
        assert status_after == status_before, "Terminal pageshow restarted exact-run recovery"
        artifacts = _verify_manifest_and_pdf(page, args.frontend_url.rstrip("/"), run_id)
        screenshot_path = args.output.with_suffix(".png")''', "pageshow proof")
    source = replace_once(source, '''            "terminal_restart_recovery_verified": True,
            "exact_run_identity_preserved": True,''', '''            "terminal_restart_recovery_verified": True,
            "terminal_run_removed_from_active_storage": True,
            "terminal_pageshow_recovery_absent": True,
            "terminal_scroll_position_preserved": True,
            "terminal_storage": terminal_storage,
            "terminal_after_pageshow": terminal_after_pageshow,
            "exact_run_identity_preserved": True,''', "proof evidence")
    PROOF.write_text(source, encoding="utf-8")


def write_test() -> None:
    TEST.write_text('''from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = (ROOT / "apps/web/app/assessment/useAssessmentRun.ts").read_text(encoding="utf-8")
WORKSPACE = (ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "apps/web/styles/assessment-mobile-stability.css").read_text(encoding="utf-8")
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")


def test_terminal_runs_stop_being_active_jobs():
    assert "function readStoredRun(): PersistedRun | null" in HOOK
    assert HOOK.count("clearPersistedRun(true);") == 2
    assert "const persisted = readStoredRun();" in HOOK


def test_new_assessment_clears_stale_identity():
    assert "function startNew(): void" in HOOK
    assert "url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);" in HOOK
    assert "async function run(): Promise<void> {\n    clearPersistedRun(false);" in HOOK


def test_terminal_actions_preserve_scroll():
    assert WORKSPACE.count("restoreArtifactScroll(scrollTop);") == 2
    assert 'data-assessment-terminal-actions="true"' in WORKSPACE
    assert "Start new assessment" in WORKSPACE
    assert "overflow-anchor: none !important" in CSS


def test_live_browser_proof_rejects_stale_terminal_recovery():
    assert "expect_active_storage=False" in PROOF
    assert "Terminal pageshow restarted exact-run recovery" in PROOF
    assert 'terminal_pageshow_recovery_absent": True' in PROOF
''', encoding="utf-8")


def main() -> int:
    patch_hook(); patch_workspace(); patch_css(); patch_proof(); write_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
