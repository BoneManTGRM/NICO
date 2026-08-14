from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps/web/app/ComprehensiveStuckRunRecovery.tsx"
LAYOUT = ROOT / "apps/web/app/layout.tsx"


def test_guard_bounds_comprehensive_lifecycle_requests() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const DIAGNOSTIC_REQUEST_TIMEOUT_MS = 60_000" in source
    assert "const RUN_STATUS_REQUEST_TIMEOUT_MS = 90_000" in source
    assert "const LONG_REQUEST_TIMEOUT_MS = 300_000" in source
    assert "const RUN_STATUS_PATH =" in source
    assert 'if (method === "GET" && RUN_STATUS_PATH.test(path))' in source
    assert "const controller = new AbortController()" in source
    assert "controller.abort" in source
    assert "nico:comprehensive-request-timeout" in source
    assert "/diagnostics/comprehensive-runtime" in source
    assert "assessment\\/comprehensive-(?:intake|run" in source
    assert "(?:\\/continue)?" in source


def test_saved_run_age_never_overrides_durable_backend_authority() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "ACTIVE_RUN_MAX_AGE_MS" not in source
    assert "STALE_CHECK_INTERVAL_MS" not in source
    assert "Date.now() - stored.startedAt" not in source
    assert "The saved assessment is older than the recovery limit." not in source
    assert "Browser age is not evidence that a durable run is invalid" in source
    assert "Recovery controls appear only after a bounded lifecycle request" in source


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
    assert "const stale = Boolean(" not in source
    assert "setInterval(" not in source
    assert 'window.addEventListener("nico:comprehensive-request-timeout"' in source


def test_keep_waiting_dismisses_the_current_timeout_notice() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const keepWaiting = () =>" in source
    assert 'timedOutRunId.current = ""' in source
    assert "setVisible(false)" in source
    assert "onClick={keepWaiting}" in source


def test_timeout_recovers_run_identity_from_the_exact_request_path() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "function runIdFromLifecyclePath(path: string)" in source
    assert "const timeoutRunId = currentRunId() || runIdFromLifecyclePath(path)" in source
    assert "retainExactRunIdentity(timeoutRunId)" in source
    assert 'url.searchParams.set(ACTIVE_RUN_QUERY_KEY, exactRunId)' in source
    assert "window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY" in source
    assert "setRecoveryRunId(timeoutRunId)" in source


def test_readiness_timeout_without_an_accepted_run_does_not_show_recovery() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "if (!timeoutRunId)" in source
    assert 'setRecoveryRunId("")' in source
    assert "setVisible(false)" in source
    assert "Recovery controls appear only after a bounded lifecycle request" in source


def test_retry_action_restores_exact_identity_and_cache_busts_navigation() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const retryExactRun = () =>" in source
    assert "retainExactRunIdentity(runId)" in source
    assert 'url.searchParams.set(ACTIVE_RUN_QUERY_KEY, runId)' in source
    assert 'url.searchParams.set("recovery_attempt", Date.now().toString())' in source
    assert "window.location.replace" in source
    assert "window.location.reload()" not in source
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