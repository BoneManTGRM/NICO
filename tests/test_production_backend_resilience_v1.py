from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "apps/web/app/api/nico/[...path]/route.ts"
HOOK = ROOT / "apps/web/app/assessment/useAssessmentRun.ts"


def test_proxy_retries_transient_backend_failures_and_cold_starts() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "const TRANSIENT_STATUS = new Set([408, 425, 429, 500, 502, 503, 504])" in source
    assert "const RETRY_DELAYS_MS = [0, 1_500, 4_000]" in source
    assert "for (let attempt = 0; attempt < RETRY_DELAYS_MS.length; attempt += 1)" in source
    assert "AbortSignal.timeout(shortRead ? 20_000 : 240_000)" in source
    assert '"X-NICO-Proxy-Attempts"' in source
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
    source = HOOK.read_text(encoding="utf-8")

    assert "async function requestWithRetry" in source
    assert "const CLIENT_RETRY_DELAYS_MS = [0, 2_000, 5_000]" in source
    assert "async function recoverRun" in source
    assert '`/assessment/comprehensive-run/${encodeURIComponent(runId)}`' in source
    assert "const recovered = await recoverRun(runId)" in source
    assert "completed stages remain bound to the displayed run ID" in source


def test_retry_logic_does_not_bypass_authorization_or_proxy_allowlist() -> None:
    proxy = PROXY.read_text(encoding="utf-8")
    hook = HOOK.read_text(encoding="utf-8")

    assert "assessmentRouteAllowed(request.method, apiPath)" in proxy
    assert "if (!assessmentAllowed && !diagnosticAllowed)" in proxy
    assert "if (!authorized)" in hook
    assert "authorization_confirmed: true" in hook
    assert "authorized: true" in hook
