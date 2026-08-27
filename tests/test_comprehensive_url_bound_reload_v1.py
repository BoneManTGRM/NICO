from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "apps/web/app/assessment/useAssessmentRun.ts"


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_bootstrap_prefers_exact_url_run_over_local_active_run() -> None:
    source = _source()
    bootstrap = _slice(source, "useEffect(() => {", "const restoreAfterPageResume")

    assert 'const boundRunId = urlBoundRunId(url);' in bootstrap
    assert 'const persisted = readPersistedRun();' in bootstrap
    assert 'if (boundRunId) {' in bootstrap
    assert 'if (persisted?.runId === boundRunId)' in bootstrap
    assert 'void resumeUrlBoundRun(boundRunId);' in bootstrap
    assert bootstrap.index('if (boundRunId) {') < bootstrap.index('} else if (persisted) {')


def test_url_bound_terminal_recovery_is_exact_run_get_before_any_continuation() -> None:
    source = _source()
    recovery = _slice(source, "async function resumeUrlBoundRun", "async function resumePersistedRun")

    exact_get = '`/assessment/comprehensive-run/${encodeURIComponent(boundRunId)}`'
    terminal_check = "const stable = terminal(service, recovered);"
    continuation = "await continueRun(recovered, scope, token, startedAt);"

    assert 'boundRunId.startsWith("comprun_")' in recovery
    assert exact_get in recovery
    assert '{method: "GET"}' in recovery
    assert 'preserveRunIdentity(recoveredResponse, {runId: boundRunId})' in recovery
    assert terminal_check in recovery
    assert 'if (stable) {' in recovery
    assert 'clearPersistedRun(true);' in recovery
    assert continuation in recovery
    assert recovery.index(exact_get) < recovery.index(terminal_check) < recovery.index(continuation)
    assert "/continue" not in recovery


def test_page_resume_keeps_explicit_url_run_authoritative() -> None:
    source = _source()
    resume = _slice(source, "const restoreAfterPageResume", 'window.addEventListener("pageshow"')

    assert "const boundRunId = urlBoundRunId(resumedUrl);" in resume
    assert "if (boundRunId) {" in resume
    assert "visibleRunId === boundRunId" in resume
    assert "void resumeUrlBoundRun(boundRunId);" in resume
    assert resume.index("if (boundRunId) {") < resume.index("const persisted = readPersistedRun();")


def test_start_new_removes_stale_exact_run_query_parameter() -> None:
    source = _source()
    start_new = _slice(source, "function startNew()", "async function retry")

    assert 'url.searchParams.has("run_id")' in start_new
    assert 'url.searchParams.delete("run_id")' in start_new
    assert "window.history.replaceState(" in start_new
    assert start_new.index('url.searchParams.delete("run_id")') < start_new.index("publishResult(null)")


def test_url_recovery_does_not_grant_human_approval_or_delivery_authority() -> None:
    source = _source()
    recovery = _slice(source, "async function resumeUrlBoundRun", "async function resumePersistedRun")

    assert "approved_delivery_package" not in recovery
    assert "client_delivery_allowed" not in recovery
    assert "human_review_completed" not in recovery
    assert "authorization_confirmed" not in recovery
