from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "apps" / "web" / "app" / "AssessmentApiTransportBridge.tsx"
FAILURE_PANEL = ROOT / "apps" / "web" / "app" / "AssessmentFailureEvidencePanel.tsx"
ROUTE = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_bridge_replaces_one_long_express_connection_with_exact_run_polling() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    assert 'process.env.NEXT_PUBLIC_NICO_API_URL' in source
    assert 'LEGACY_EXPRESS_PATH = "/assessment/github"' in source
    assert 'EXPRESS_START_PATH = "/assessment/express-run"' in source
    assert 'EXPRESS_POLL_INTERVAL_MS = 3000' in source
    assert 'EXPRESS_MAX_POLL_ATTEMPTS = 240' in source
    assert 'requested.origin !== configured.origin' in source
    assert 'ASSESSMENT_PATH.test(apiPath)' in source
    assert 'if (apiPath === LEGACY_EXPRESS_PATH) return startExpressLifecycle' in source
    assert 'proxyUrl(EXPRESS_START_PATH)' in source
    assert '`/assessment/express-run/${encodeURIComponent(runId)}/status`' in source
    assert 'runId.startsWith("express_run_")' in source
    assert 'The exact run ID is preserved' in source
    assert 'Express transport was interrupted before the Railway backend returned a response' not in source
    assert 'window.fetch = bridgedFetch' in source
    assert 'if (window.fetch === bridgedFetch) window.fetch = originalFetch' in source


def test_bridge_retains_only_bounded_page_scoped_failure_identity_and_progress() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    assert 'ASSESSMENT_FAILURE_EVENT = "nico:assessment-request-failed"' in source
    assert 'response.clone()' in source
    assert 'value.slice(0, 16)' in source
    assert 'boundedText(record.message, 240)' in source
    assert 'run_id: boundedText(detail.run_id || payload.run_id, 120)' in source
    assert 'window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT' in source
    assert 'sessionStorage' not in source
    assert 'localStorage' not in source
    request_start = source.index('      clearFailure();')
    express_branch = source.index('      if (apiPath === LEGACY_EXPRESS_PATH)')
    assert request_start < express_branch
    assert 'evidence:' not in source.split('const evidence: AssessmentFailureEvidence = {', 1)[1].split('};', 1)[0]
    assert 'headers' not in source.split('const evidence: AssessmentFailureEvidence = {', 1)[1].split('};', 1)[0]


def test_server_proxy_allows_only_quick_lifecycle_routes() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert 'process.env.NICO_API_URL || process.env.NEXT_PUBLIC_NICO_API_URL' in source
    assert 'ALLOWED_ASSESSMENT_PATH.test(apiPath)' in source
    assert '(?:express|mid|full)-run' in source
    assert '/assessment/github' not in source
    assert 'Only canonical Express, Mid, and Full lifecycle routes are available through this proxy.' in source
    assert 'assessment_proxy_route_not_allowed' in source
    assert 'assessment_backend_not_configured' in source
    assert 'assessment_backend_unreachable' in source
    assert 'url.username || url.password' in source
    assert 'process.env.NODE_ENV === "production" && url.protocol !== "https:"' in source
    assert 'request.headers.get("content-type")' in source
    assert 'request.headers.get("authorization")' not in source
    assert 'request.headers.get("cookie")' not in source
    assert 'Cache-Control": "no-store"' in source
    assert 'AbortSignal.timeout(120_000)' in source


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
