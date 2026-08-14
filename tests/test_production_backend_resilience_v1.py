from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "apps/web/app/api/nico/[...path]/route.ts"
ASSESSMENT = ROOT / "apps/web/app/assessment"
HOOK = ASSESSMENT / "useAssessmentRun.ts"
REQUESTS = ASSESSMENT / "assessmentRunRequests.ts"
IDENTITY = ASSESSMENT / "assessmentRunIdentity.ts"


def test_proxy_retries_transient_backend_failures_and_cold_starts() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "const TRANSIENT_STATUS = new Set([408, 425, 429, 500, 502, 503, 504])" in source
    assert "const RETRY_DELAYS_MS = [0, 1_500, 4_000]" in source
    assert "const ARTIFACT_RETRY_DELAYS_MS = [0]" in source
    assert "const SHORT_READ_TIMEOUT_MS = 20_000" in source
    assert "const ARTIFACT_READ_TIMEOUT_MS = 240_000" in source
    assert "for (let attempt = 0; attempt < policy.retryDelaysMs.length; attempt += 1)" in source
    assert "signal: AbortSignal.timeout(policy.timeoutMs)" in source
    assert 'readClass: "exact-run-artifact"' in source
    assert 'readClass: shortRead ? "short-status" : "bounded-write"' in source
    assert '"X-NICO-Proxy-Attempts"' in source
    assert '"X-NICO-Proxy-Read-Class": policy.readClass' in source
    assert '"Retry-After": "5"' in source


def test_proxy_supports_bounded_backend_configuration_fallbacks() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "process.env.NICO_API_URL" in source
    assert "process.env.NICO_BACKEND_URL" in source
    assert "process.env.NEXT_PUBLIC_NICO_API_URL" in source
    assert "url.username || url.password" in source
    assert 'process.env.NODE_ENV === "production" && url.protocol !== "https:"' in source
    assert "backend_candidate_count" in source
    assert "request_id" in source


def test_frontend_retries_and_recovers_existing_run_state() -> None:
    hook = HOOK.read_text(encoding="utf-8")
    requests = REQUESTS.read_text(encoding="utf-8")
    identity = IDENTITY.read_text(encoding="utf-8")

    assert "export async function requestWithRetry" in requests
    assert "const CLIENT_RETRY_DELAYS_MS = [0, 2_000, 5_000]" in requests
    assert "async function recoverRun" in hook
    assert '`/assessment/comprehensive-run/${encodeURIComponent(runId)}`' in hook
    assert "const recovered = await recoverRun(runId, {" in hook
    assert "return preserveRunIdentity(recovered" in hook
    assert "export function preserveRunIdentity" in identity
    assert "async function resumePersistedRun" in hook
    assert "const recovered = preserveRunIdentity(recoveredResponse" in hook
    assert "publishResult(recovered);" in hook
    assert "preferMonotonicVisibleResult" in hook
    assert "incomingProgress < previousProgress" in hook
    assert "await continueRun(recovered, scope, token, persisted.startedAt)" in hook
    assert 'window.addEventListener("pageshow", restoreAfterPageResume)' in hook
    assert 'window.addEventListener("online", restoreAfterPageResume)' in hook
    assert "runStatusUnavailableMessage" in requests


def test_retry_logic_does_not_bypass_authorization_or_proxy_allowlist() -> None:
    proxy = PROXY.read_text(encoding="utf-8")
    hook = HOOK.read_text(encoding="utf-8")

    assert "assessmentRouteAllowed(request.method, apiPath)" in proxy
    assert "if (!assessmentAllowed && !diagnosticAllowed)" in proxy
    assert "if (!authorized)" in hook
    assert "authorization_confirmed: true" in hook
    assert "authorized: true" in hook
