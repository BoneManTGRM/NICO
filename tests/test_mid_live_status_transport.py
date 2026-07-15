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
    assert "LIVE_TIMEOUT_MS = 12_000" in source
    assert "livePayload.continuation_required === true" in source
    assert "const continuation = await previousFetch(input, init)" in source
    assert "duplicate_start_allowed: false" in source


def test_live_transport_is_outer_than_old_status_guards_but_inside_api_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentMidLiveStatusTransport from "./AssessmentMidLiveStatusTransport"' in layout
    assert "<AssessmentMidLiveStatusTransport />" in layout
    assert layout.index("<AssessmentStatusOutcomeGuard />") < layout.index("<AssessmentMidLiveStatusTransport />")
    assert layout.index("<AssessmentMidLiveStatusTransport />") < layout.index("<AssessmentApiTransportBridge />")


def test_same_origin_proxy_allows_live_status_with_short_timeout() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "(?:status|live-status)" in source
    assert 'apiPath.endsWith("/live-status") ? 15_000 : 120_000' in source
    assert "export const GET = proxyAssessment" in source


def test_production_uses_two_web_workers_only_when_durable_database_exists() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "NICO_WEB_WORKERS" in source
    assert 'if [ -n "${DATABASE_URL:-}" ]; then workers=2; else workers=1; fi' in source
    assert "--workers $workers" in source
