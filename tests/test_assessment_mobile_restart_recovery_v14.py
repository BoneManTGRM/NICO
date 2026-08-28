from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps/web/app/assessment"
HOOK = ASSESSMENT / "useAssessmentRun.ts"
PERSISTENCE = ASSESSMENT / "assessmentRunPersistence.ts"
REQUESTS = ASSESSMENT / "assessmentRunRequests.ts"
WORKSPACE = ASSESSMENT / "AssessmentWorkspace.tsx"
PROXY = ROOT / "apps/web/app/api/nico/[...path]/route.ts"
BACKEND = ROOT / "nico/comprehensive_mobile_recovery_v1.py"
INIT = ROOT / "nico/__init__.py"


def test_exact_run_is_persisted_in_url_and_browser_storage() -> None:
    hook = HOOK.read_text(encoding="utf-8")
    persistence = PERSISTENCE.read_text(encoding="utf-8")

    assert 'ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1"' in persistence
    assert 'EXACT_RUN_STORAGE_PREFIX = "nico.comprehensive.exact-run.v1."' in persistence
    assert 'ACTIVE_RUN_QUERY_KEY = "run_id"' in persistence
    assert "window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, encoded)" in persistence
    assert "window.localStorage.setItem(exactRunStorageKey(value.runId), encoded)" in persistence
    assert "url.searchParams.set(ACTIVE_RUN_QUERY_KEY, value.runId)" in persistence
    assert "persistExactRun(data, scope, startedAt)" in hook
    assert "persistExactRun(current, scope, startedAt)" in hook


def test_mobile_page_resume_recovers_and_continues_the_same_run() -> None:
    source = HOOK.read_text(encoding="utf-8")

    assert "resumePersistedRun(persisted)" in source
    assert 'window.addEventListener("pageshow", restoreAfterPageResume)' in source
    assert 'window.addEventListener("online", restoreAfterPageResume)' in source
    assert "const persisted = readPersistedRun();" in source
    assert "activeContinuationRunId.current === persisted.runId" in source
    assert "visibleRunId && visibleRunId !== persisted.runId" in source
    assert '`/assessment/comprehensive-run/${encodeURIComponent(persisted.runId)}`' in source
    assert "publishResult(recovered);" in source
    assert "await continueRun(recovered, scope, token, persisted.startedAt)" in source
    assert 'setResult({\n      run_id: persisted.runId' not in source
    assert '"/assessment/comprehensive-intake"' in source


def test_browser_requests_select_bounded_terminal_manifest() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert 'BROWSER_PROJECTION_HEADER = "X-NICO-Browser-Projection"' in source
    assert 'BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"' in source
    assert "headers.set(BROWSER_PROJECTION_HEADER, BROWSER_PROJECTION_VALUE)" in source


def test_terminal_report_actions_stream_artifacts_instead_of_requiring_embedded_pdf() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "report?.pdf_available" in source
    assert "report?.markdown_available" in source
    assert '`/assessment/comprehensive-run/${encodeURIComponent(runId)}/localized-report/${encodeURIComponent(requestedReportLanguage)}`' in source
    assert "payload.report?.markdown" in source
    assert "payload.assessment_rerun !== false" in source
    assert 'data-commit-sha={immutableCommit}' in source
    assert '`/assessment/comprehensive-run/${encodeURIComponent(runId)}/report/pdf`' in source
    assert "await response.arrayBuffer()" in source
    assert 'new Blob([bytes], {type: "application/pdf"})' in source
    assert "disabled={!pdfAvailable || artifactAction !== null}" in source
    assert "disabled={!markdownAvailable || artifactAction !== null}" in source


def test_same_origin_proxy_allows_artifacts_and_forwards_bounded_projection() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "COMPREHENSIVE_REPORT_ARTIFACT" in source
    assert "(?:markdown|html|json|pdf)" in source
    assert "COMPREHENSIVE_REPORT_ARTIFACT.test(path)" in source
    assert 'BROWSER_PROJECTION_HEADER = "x-nico-browser-projection"' in source
    assert 'BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"' in source
    assert 'headers.set("X-NICO-Browser-Projection", BROWSER_PROJECTION_VALUE)' in source
    assert '"x-nico-artifact-sha256"' in source
    assert '"x-nico-accepted-pdf-sha256"' in source
    assert '"x-nico-canonical-truth-sha256"' in source


def test_backend_streams_exact_run_artifacts_and_keeps_browser_terminal_response_bounded() -> None:
    source = BACKEND.read_text(encoding="utf-8")
    package_init = INIT.read_text(encoding="utf-8")

    assert 'BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"' in source
    assert '"pdf_available": bool(encoded_pdf)' in source
    assert '"artifact_delivery": "on_demand_exact_run"' in source
    assert '@app.get("/assessment/comprehensive-run/{run_id}/report/pdf")' in source
    assert "base64.b64decode(encoded, validate=True)" in source
    assert 'if not pdf.startswith(b"%PDF")' in source
    assert "expected_hash and expected_hash != observed_hash" in source
    assert "install_comprehensive_mobile_recovery_v1()" in package_init
