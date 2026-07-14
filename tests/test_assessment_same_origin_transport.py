from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "apps" / "web" / "app" / "AssessmentApiTransportBridge.tsx"
ROUTE = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_bridge_rewrites_only_configured_canonical_assessment_requests() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    assert 'process.env.NEXT_PUBLIC_NICO_API_URL' in source
    assert 'requested.origin !== configured.origin' in source
    assert 'ASSESSMENT_PATH.test(apiPath)' in source
    assert 'new URL(`/api/nico${apiPath}${requested.search}`, window.location.origin)' in source
    assert 'return originalFetch(input, init)' in source
    assert 'window.fetch = bridgedFetch' in source
    assert 'if (window.fetch === bridgedFetch) window.fetch = originalFetch' in source


def test_server_proxy_is_fixed_origin_bounded_and_fail_closed() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert 'process.env.NICO_API_URL || process.env.NEXT_PUBLIC_NICO_API_URL' in source
    assert 'ALLOWED_ASSESSMENT_PATH.test(apiPath)' in source
    assert 'assessment_proxy_route_not_allowed' in source
    assert 'assessment_backend_not_configured' in source
    assert 'assessment_backend_unreachable' in source
    assert 'url.username || url.password' in source
    assert 'process.env.NODE_ENV === "production" && url.protocol !== "https:"' in source
    assert 'request.headers.get("content-type")' in source
    assert 'request.headers.get("authorization")' not in source
    assert 'request.headers.get("cookie")' not in source
    assert 'Cache-Control": "no-store"' in source
    assert 'AbortSignal.timeout(285_000)' in source


def test_root_layout_installs_transport_before_assessment_helpers() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentApiTransportBridge from "./AssessmentApiTransportBridge"' in source
    assert source.index('<AssessmentApiTransportBridge />') < source.index('<AssessmentHomeRedirect />')
