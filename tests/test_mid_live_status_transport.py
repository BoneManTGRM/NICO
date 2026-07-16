from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "apps" / "web" / "app" / "AssessmentMidLiveStatusTransport.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
PROXY = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
DOCKERFILE = ROOT / "Dockerfile"


def test_mid_status_transport_replaces_repeated_canonical_polling_with_live_get() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")

    assert "MID_STATUS_PATH" in source
    assert "/live-status" in source
    assert 'method: "GET"' in source
    assert "LIVE_RETRY_COUNT = 2" in source
    assert "LIVE_TIMEOUT_MS = 10_000" in source
    assert "stable.continuation_required === true" in source
    assert "const continuation = await previousFetch(input, init)" in source
    assert "duplicate_start_allowed: false" in source


def test_mid_transport_preserves_highest_confirmed_progress_and_stage() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")

    assert "highWaterProgress" in source
    assert "highWaterScannerProgress" in source
    assert "highWaterStageRank" in source
    assert "function stabilizePayload" in source
    assert "state.highWaterProgress = Math.max(state.highWaterProgress, incomingProgress)" in source
    assert "output.progress_percent = state.highWaterProgress" in source
    assert "active && incomingRank < state.highWaterStageRank" in source
    assert "highest_confirmed_progress_percent" in source
    assert "const stable = stabilizePayload(livePayload, state)" in source
    assert "const continued = stabilizePayload(continuationPayload, state)" in source
    assert "const stable = stabilizePayload(fallbackPayload, state)" in source


def test_mid_transport_uses_bounded_retry_without_thirty_second_backoff() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")

    assert "LIVE_RETRY_DELAY_MS = 750" in source
    assert "LIVE_BACKOFF_BASE_MS = 2_000" in source
    assert "LIVE_BACKOFF_MAX_MS = 12_000" in source
    assert "LIVE_BACKOFF_MAX_MS = 30_000" not in source
    assert "Live status is temporarily unavailable" in source
    assert "highest confirmed progress" in source


def test_live_transport_is_outer_than_old_status_guards_but_inside_api_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentMidLiveStatusTransport from "./AssessmentMidLiveStatusTransport"' in layout
    assert "<AssessmentMidLiveStatusTransport />" in layout
    assert layout.index("<AssessmentStatusOutcomeGuard />") < layout.index("<AssessmentMidLiveStatusTransport />")
    assert layout.index("<AssessmentMidLiveStatusTransport />") < layout.index("<AssessmentApiTransportBridge />")


def test_same_origin_proxy_allows_live_status_and_runtime_diagnostics_with_short_timeout() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "(?:status|live-status)" in source
    assert 'apiPath.endsWith("/live-status")' in source
    assert 'ALLOWED_DIAGNOSTIC_PATH.test(apiPath)' in source
    assert "express-runtime" in source
    assert "mid-runtime" in source
    assert "AbortSignal.timeout(15_000)" in source
    assert "AbortSignal.timeout(120_000)" in source
    assert "export const GET = proxyNico" in source
    assert "export const POST = proxyNico" in source


def test_production_defaults_to_one_web_worker_for_in_process_assessments() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "ENV NICO_WEB_WORKERS=1" in source
    assert 'workers=${NICO_WEB_WORKERS:-1}' in source
    assert "workers=2" not in source
    assert "DATABASE_URL" not in source.split("CMD", 1)[1]
    assert "--workers $workers" in source
