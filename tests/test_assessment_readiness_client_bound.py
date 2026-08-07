from __future__ import annotations

from pathlib import Path


REQUESTS = Path("apps/web/app/assessment/assessmentRunRequests.ts")
HOOK = Path("apps/web/app/assessment/useAssessmentRun.ts")


def test_readiness_preflight_uses_one_browser_attempt_with_absolute_timeout() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert 'const READINESS_PATH = "/diagnostics/comprehensive-runtime"' in source
    assert "const READINESS_CLIENT_TIMEOUT_MS = 48_000" in source
    assert "const readinessPreflight = path === READINESS_PATH" in source
    assert "const boundedRequest = readinessPreflight || runStatusRequest" in source
    assert "const retryDelays = boundedRequest ? [0] : CLIENT_RETRY_DELAYS_MS" in source
    assert "new AbortController()" in source
    assert "new Promise<never>" in source
    assert "Promise.race([requestPromise, timeoutPromise])" in source
    assert "controller?.abort()" in source
    assert "window.clearTimeout(timeoutId)" in source
    assert '"assessment_readiness_timeout"' in source
    assert "status: 504" in source
    assert "retryable: true" in source


def test_persisted_run_status_recovery_has_its_own_absolute_timeout() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "const RUN_STATUS_CLIENT_TIMEOUT_MS = 20_000" in source
    assert "const RUN_STATUS_PATH = /^\\/assessment\\/comprehensive-run\\/[^/]+$/" in source
    assert 'const runStatusRequest = method === "GET" && RUN_STATUS_PATH.test(path)' in source
    assert "runStatusRequest\n      ? RUN_STATUS_CLIENT_TIMEOUT_MS" in source
    assert '"assessment_run_status_timeout"' in source
    assert '"assessment_run_status_timeout",' in source


def test_normal_assessment_requests_retain_existing_retry_policy() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "const CLIENT_RETRY_DELAYS_MS = [0, 2_000, 5_000]" in source
    assert "TRANSIENT_STATUS.has(response.status)" in source
    assert "attempt < retryDelays.length - 1" in source
    assert "return {retry: true}" in source
    assert 'if (!("result" in attemptResult))' in source
    assert "continue;" in source


def test_readiness_and_run_status_timeouts_route_to_recoverable_service_unavailable_state() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert '"assessment_readiness_timeout"' in source
    assert '"assessment_run_status_timeout"' in source
    assert 'kind: "service_unavailable"' in source
    assert "retryable," in source


def test_run_creation_still_requires_authoritative_durable_readiness() -> None:
    source = HOOK.read_text(encoding="utf-8")
    start = source.index("async function verifyRuntimePersistence")
    end = source.index("async function recoverRun")
    readiness = source[start:end]

    assert '"/diagnostics/comprehensive-runtime"' in readiness
    assert "survives_container_replacement_verified === true" in readiness
    assert 'String(diagnostics.status || "").toLowerCase() !== "ready"' in readiness
    assert 'code: reason' in readiness
    assert 'retryable: true' in readiness


def test_persisted_run_recovery_uses_the_bounded_status_request() -> None:
    source = HOOK.read_text(encoding="utf-8")
    start = source.index("async function resumePersistedRun")
    recovery = source[start:]

    assert '`/assessment/comprehensive-run/${encodeURIComponent(persisted.runId)}`' in recovery
    assert '{method: "GET"}' in recovery
    assert "applyIssue(caught, true)" in recovery


def test_failed_readiness_exits_checking_phase_through_existing_issue_boundary() -> None:
    source = HOOK.read_text(encoding="utf-8")
    run_start = source.index("async function run(): Promise<void>")
    run_source = source[run_start:]

    assert "await verifyRuntimePersistence()" in run_source
    assert "applyIssue(caught, runCreated)" in run_source
    assert 'setPhase(normalized.kind === "run_failed" ? "failed" : "unavailable")' in source
