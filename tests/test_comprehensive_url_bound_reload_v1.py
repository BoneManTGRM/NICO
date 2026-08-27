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
    assert 'const exactRun = urlBoundPersistedRun(boundRunId, persisted);' in bootstrap
    assert 'void resumePersistedRun(exactRun);' in bootstrap
    assert bootstrap.index('if (boundRunId) {') < bootstrap.index('} else if (persisted) {')


def test_url_bound_fallback_preserves_exact_run_without_inventing_metadata() -> None:
    source = _source()
    fallback = _slice(source, "function urlBoundPersistedRun", "function persistExactRun")

    assert 'if (persisted?.runId === runId)' in fallback
    assert "return persisted;" in fallback
    assert "runId," in fallback
    assert 'repository: ""' in fallback
    assert 'client: ""' in fallback
    assert 'project: ""' in fallback
    assert 'customerId: "default_customer"' in fallback
    assert 'projectId: "default_project"' in fallback


def test_shared_recovery_gets_exact_run_before_terminal_or_continuation() -> None:
    source = _source()
    recovery = _slice(source, "async function resumePersistedRun", "async function run()")

    exact_get = '`/assessment/comprehensive-run/${encodeURIComponent(persisted.runId)}`'
    terminal_check = "const stable = terminal(service, recovered);"
    continuation = "await continueRun(recovered, scope, token, persisted.startedAt);"

    assert exact_get in recovery
    assert '{method: "GET"}' in recovery
    assert "runId: persisted.runId" in recovery
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
    assert "publishResult(null);" in resume
    assert "urlBoundPersistedRun(boundRunId, readPersistedRun())" in resume
    assert resume.index("if (boundRunId) {") < resume.index("const persisted = readPersistedRun();")


def test_start_new_removes_stale_exact_run_query_parameter() -> None:
    source = _source()
    start_new = _slice(source, "function startNew()", "async function retry")

    assert 'url.searchParams.has("run_id")' in start_new
    assert 'url.searchParams.delete("run_id")' in start_new
    assert "window.history.replaceState(" in start_new
    assert start_new.index('url.searchParams.delete("run_id")') < start_new.index("publishResult(null)")


def test_url_reload_change_does_not_grant_human_approval_or_delivery_authority() -> None:
    source = _source()
    bootstrap = _slice(source, "useEffect(() => {", "useEffect(() => {\n    if (!started")
    fallback = _slice(source, "function urlBoundPersistedRun", "function persistExactRun")

    for forbidden in (
        "approved_delivery_package",
        "client_delivery_allowed",
        "human_review_completed",
        "authorization_confirmed",
    ):
        assert forbidden not in bootstrap
        assert forbidden not in fallback
