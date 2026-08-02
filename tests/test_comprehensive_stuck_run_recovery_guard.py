from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps/web/app/ComprehensiveStuckRunRecovery.tsx"
LAYOUT = ROOT / "apps/web/app/layout.tsx"


def test_guard_bounds_comprehensive_lifecycle_requests() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const SHORT_REQUEST_TIMEOUT_MS = 45_000" in source
    assert "const LONG_REQUEST_TIMEOUT_MS = 300_000" in source
    assert "const controller = new AbortController()" in source
    assert "controller.abort" in source
    assert "nico:comprehensive-request-timeout" in source
    assert "/diagnostics/comprehensive-runtime" in source
    assert "assessment\\/comprehensive-(?:intake|run" in source
    assert "(?:\\/continue)?" in source


def test_guard_expires_stale_browser_run_identity() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const ACTIVE_RUN_MAX_AGE_MS = 2 * 60 * 60_000" in source
    assert "Date.now() - stored.startedAt > ACTIVE_RUN_MAX_AGE_MS" in source
    assert 'window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY)' in source
    assert 'url.searchParams.delete(ACTIVE_RUN_QUERY_KEY)' in source


def test_guard_exposes_mobile_safe_recovery_controls() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'data-comprehensive-stuck-run-recovery="true"' in source
    assert 'data-clear-stuck-comprehensive-run="true"' in source
    assert "Retry exact run" in source
    assert "Clear stuck run and start new" in source
    assert "Keep waiting" in source
    assert "env(safe-area-inset-bottom)" in source


def test_guard_does_not_treat_every_active_run_as_stuck() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "RECOVERY_CONTROL_DELAY_MS" not in source
    assert "RUNNING_COPY" not in source
    assert "document.body?.innerText" not in source
    assert "const stale = Boolean(" in source
    assert "const timedOut = Boolean(" in source
    assert "if (dismissed || (!stale && !timedOut))" in source


def test_keep_waiting_dismisses_the_current_run_until_identity_changes() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'const dismissedRunId = useRef("")' in source
    assert "dismissedRunId.current = runId" in source
    assert 'timedOutRunId.current = ""' in source
    assert "onClick={keepWaiting}" in source
    assert "dismissedRunId.current !== runId" in source


def test_timeout_recovers_run_identity_from_the_exact_request_path() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "function runIdFromLifecyclePath(path: string)" in source
    assert "const timeoutRunId = currentRunId() || runIdFromLifecyclePath(path)" in source
    assert "retainExactRunIdentity(timeoutRunId)" in source
    assert 'url.searchParams.set(ACTIVE_RUN_QUERY_KEY, exactRunId)' in source
    assert 'window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY' in source
    assert "setRecoveryRunId(timeoutRunId)" in source


def test_readiness_timeout_without_an_accepted_run_does_not_show_recovery() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "if (!timeoutRunId)" in source
    assert 'setRecoveryRunId("")' in source
    assert "setVisible(false)" in source
    assert "Recovery controls are shown only when NICO can retain" in source


def test_retry_action_restores_exact_identity_before_reload() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const retryExactRun = () =>" in source
    assert "retainExactRunIdentity(runId)" in source
    assert "window.location.reload()" in source
    assert "onClick={retryExactRun}" in source


def test_guard_is_mounted_before_assessment_transport_bridges() -> None:
    source = LAYOUT.read_text(encoding="utf-8")
    assert 'import ComprehensiveStuckRunRecovery from "./ComprehensiveStuckRunRecovery"' in source
    assert "<ComprehensiveStuckRunRecovery />" in source
    assert source.index("<ComprehensiveStuckRunRecovery />") < source.index("<AssessmentApiTransportBridge />")


def test_request_input_is_dispatched_once_for_webkit_body_safety() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const boundedRequest = new Request(input, boundedInit)" in source
    assert "requestPromise = originalFetch(boundedRequest)" in source
    assert "originalFetch(boundedRequest, boundedInit)" not in source
    assert "Passing the same" in source and "WebKit" in source
