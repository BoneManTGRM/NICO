from __future__ import annotations

from pathlib import Path


REQUESTS = Path("apps/web/app/assessment/assessmentRunRequests.ts")
HOOK = Path("apps/web/app/assessment/useAssessmentRun.ts")
PROXY = Path("apps/web/app/api/nico/[...path]/route.ts")

# Readiness recovery retries are semantic-only: transport failure alone never
# authorizes an additional probe of the canonical durable store.


def test_readiness_preflight_uses_bounded_same_store_recovery_probes_with_absolute_timeout() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert 'const READINESS_PATH = "/diagnostics/comprehensive-runtime"' in source
    assert "const READINESS_CLIENT_TIMEOUT_MS = 48_000" in source
    assert "const READINESS_RETRY_DELAYS_MS = [0, 2_500, 5_000]" in source
    assert 'const RECOVERABLE_READINESS_REASONS = new Set([' in source
    assert '"comprehensive_database_unavailable"' in source
    assert "function readinessCanRecoverOnSameStore(result: Result): boolean" in source
    assert "result.runtime_recovery_supported === true" in source
    assert "result.automatic_cross_store_fallback === false" in source
    assert "const readinessPreflight = path === READINESS_PATH" in source
    assert "readinessPreflight || runStatusRequest || mutatingRequest" in source
    assert "const retryDelays = readinessPreflight" in source
    assert "? READINESS_RETRY_DELAYS_MS" in source
    assert "readinessCanRecoverOnSameStore(result)" in source
    assert "attempt < retryDelays.length - 1" in source
    assert "new AbortController()" in source
    assert "new Promise<never>" in source
    assert "Promise.race([requestPromise, timeoutPromise])" in source
    assert "controller?.abort()" in source
    assert "window.clearTimeout(timeoutId)" in source
    assert '"assessment_readiness_timeout"' in source
    assert "status: 504" in source
    assert "retryable: true" in source


def test_readiness_retries_only_after_parsed_same_store_recovery_proof() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    # Generic transport-status retrying must never authorize a readiness re-probe.
    assert (
        "!readinessPreflight &&\n          TRANSIENT_STATUS.has(response.status)" in source
    )

    # The sole readiness retry authorization is the parsed semantic contract.
    retry_guard = (
        "readinessPreflight\n"
        "        && readinessCanRecoverOnSameStore(result)\n"
        "        && attempt < retryDelays.length - 1"
    )
    assert retry_guard in source

    # Exceptions/timeouts/network failures during readiness fail closed rather than
    # silently consuming the remaining recovery probes.
    assert (
        "readinessPreflight ||\n        !retryable ||\n"
        "        attempt >= retryDelays.length - 1"
    ) in source

    # Preserve the exact three semantic gates required by the recovery contract.
    assert '"comprehensive_database_unavailable"' in source
    assert "result.runtime_recovery_supported === true" in source
    assert "result.automatic_cross_store_fallback === false" in source


def test_persisted_run_status_recovery_has_bounded_retry_and_larger_absolute_timeout() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "const RUN_STATUS_CLIENT_TIMEOUT_MS = 75_000" in source
    assert "const RUN_STATUS_PATH = /^\\/assessment\\/comprehensive-run\\/[^/]+$/" in source
    assert 'const runStatusRequest = method === "GET" && RUN_STATUS_PATH.test(path)' in source
    assert "runStatusRequest\n      ? RUN_STATUS_CLIENT_TIMEOUT_MS" in source
    assert "runStatusRequest\n      ? CLIENT_RETRY_DELAYS_MS" in source
    assert '"assessment_run_status_timeout"' in source
    assert '"assessment_run_status_timeout",' in source
    assert "status is idempotent durable recovery truth" in source


def test_exact_run_status_proxy_has_one_long_attempt_per_browser_retry() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "const EXACT_RUN_STATUS_TIMEOUT_MS = 60_000" in source
    assert 'const exactRunStatus = method === "GET" && COMPREHENSIVE_STATUS.test(path)' in source
    assert "if (exactRunStatus)" in source
    assert "timeoutMs: EXACT_RUN_STATUS_TIMEOUT_MS" in source
    assert "retryDelaysMs: SINGLE_ATTEMPT_DELAYS_MS" in source
    assert 'readClass: "exact-run-status"' in source
    assert "browser owns bounded retries" in source


def test_comprehensive_continue_is_single_attempt_and_has_absolute_timeout() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "const RUN_CONTINUE_CLIENT_TIMEOUT_MS = 260_000" in source
    assert (
        "const RUN_CONTINUE_PATH = "
        "/^\\/assessment\\/comprehensive-run\\/[^/]+\\/continue$/" in source
    )
    assert (
        'const runContinueRequest = method === "POST" && '
        "RUN_CONTINUE_PATH.test(path)" in source
    )
    assert "readinessPreflight || runStatusRequest || mutatingRequest" in source
    assert "runContinueRequest\n        ? RUN_CONTINUE_CLIENT_TIMEOUT_MS" in source
    assert '"assessment_run_continue_timeout"' in source
    assert "const retryDelays = readinessPreflight" in source
    assert ': mutatingRequest\n        ? [0]\n        : CLIENT_RETRY_DELAYS_MS' in source
    assert "No mutation is safely replayable" in source
    assert "server proxy gives a single non-replayable continuation up to 240s" in source


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
    assert '"assessment_run_continue_timeout"' in source
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
