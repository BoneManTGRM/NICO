from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "apps" / "web" / "app" / "AssessmentApiTransportBridge.tsx"
FAILURE_PANEL = ROOT / "apps" / "web" / "app" / "AssessmentFailureEvidencePanel.tsx"
ROUTE = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_bridge_intercepts_only_configured_canonical_assessment_requests() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    assert 'process.env.NEXT_PUBLIC_NICO_API_URL' in source
    assert 'requested.origin !== configured.origin' in source
    assert 'ASSESSMENT_PATH.test(apiPath)' in source
    assert 'const response = await originalFetch(input, init)' in source
    assert '/api/nico' not in source
    assert 'return originalFetch(input, init)' in source
    assert 'window.fetch = bridgedFetch' in source
    assert 'if (window.fetch === bridgedFetch) window.fetch = originalFetch' in source


def test_bridge_retains_bounded_page_scoped_failure_identity_and_transport_state() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    assert 'ASSESSMENT_FAILURE_EVENT = "nico:assessment-request-failed"' in source
    assert 'response.clone()' in source
    assert 'value.slice(0, 16)' in source
    assert 'boundedText(record.message, 240)' in source
    assert 'run_id: boundedText(detail.run_id || payload.run_id, 120)' in source
    assert 'assessment_transport_interrupted' in source
    assert 'The request was not marked successful.' in source
    assert 'publishTransportFailure(apiPath)' in source
    assert 'sessionStorage' not in source
    assert 'localStorage' not in source
    request_start = source.index('      clearFailure();')
    upstream_fetch = source.index('        const response = await originalFetch(input, init)')
    assert request_start < upstream_fetch
    assert 'evidence:' not in source.split('const evidence: AssessmentFailureEvidence = {', 1)[1].split('};', 1)[0]
    assert 'headers' not in source.split('const evidence: AssessmentFailureEvidence = {', 1)[1].split('};', 1)[0]


def test_server_transport_redirects_legacy_canonical_routes_without_holding_execution_open() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert 'process.env.NICO_API_URL || process.env.NEXT_PUBLIC_NICO_API_URL' in source
    assert 'ALLOWED_ASSESSMENT_PATH.test(apiPath)' in source
    assert 'assessment_proxy_route_not_allowed' in source
    assert 'assessment_backend_not_configured' in source
    assert 'assessment_backend_loop' in source
    assert 'url.username || url.password' in source
    assert 'process.env.NODE_ENV === "production" && url.protocol !== "https:"' in source
    assert 'status: 307' in source
    assert 'Location: upstream.toString()' in source
    assert 'Cache-Control": "no-store"' in source
    assert 'AbortSignal.timeout' not in source
    assert 'await fetch(upstream' not in source
    assert 'request.arrayBuffer()' not in source
    assert 'request.headers.get("authorization")' not in source
    assert 'request.headers.get("cookie")' not in source


def test_failure_panel_displays_only_current_page_failure_without_hydration() -> None:
    source = FAILURE_PANEL.read_text(encoding="utf-8")

    assert 'ASSESSMENT FAILURE EVIDENCE' in source
    assert 'failure.run_id' in source
    assert 'failure.http_status' in source
    assert 'failure.route' in source
    assert 'failure.progress.map' in source
    assert 'href="/operations/recovery"' in source
    assert 'for the current open page' in source
    assert 'does not convert the failed or unavailable stage into a passing result' in source
    assert 'sessionStorage' not in source
    assert 'localStorage' not in source
    assert 'dangerouslySetInnerHTML' not in source


def test_root_layout_installs_transport_and_failure_panel_before_assessment_page() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentApiTransportBridge from "./AssessmentApiTransportBridge"' in source
    assert 'import AssessmentFailureEvidencePanel from "./AssessmentFailureEvidencePanel"' in source
    assert source.index('<AssessmentApiTransportBridge />') < source.index('<AssessmentHomeRedirect />')
    assert source.index('<AssessmentFailureEvidencePanel />') < source.index('          {children}')
