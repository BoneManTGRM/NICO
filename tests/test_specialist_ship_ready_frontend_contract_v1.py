from pathlib import Path


def test_specialist_frontend_and_runtime_contracts_are_fail_closed():
    session_route = Path("apps/web/app/api/nico/operator-session/route.ts").read_text()
    assessment_proxy = Path("apps/web/app/api/nico/assessment/[...path]/route.ts").read_text()
    readiness_proxy = Path("apps/web/app/api/nico/diagnostics/specialist-readiness/route.ts").read_text()
    login_page = Path("apps/web/app/specialist-login/page.tsx").read_text()
    middleware = Path("apps/web/middleware.ts").read_text()
    specialist_access = Path("nico/specialist_access_v1.py").read_text()
    specialist_bootstrap = Path("nico/api/specialist_ship_ready_bootstrap.py").read_text()
    dockerfile = Path("Dockerfile").read_text()

    assert 'httpOnly: true' in session_route
    assert 'sameSite: "strict"' in session_route
    assert 'secure: process.env.NODE_ENV === "production"' in session_route
    assert 'X-NICO-Operator-Session' in assessment_proxy
    assert 'specialist_authentication_required' in assessment_proxy
    assert 'new URL("/diagnostics/specialist-readiness", backend)' in readiness_proxy
    assert '"Cache-Control": "no-store, private, max-age=0"' in readiness_proxy
    assert "X-NICO-Admin-Token" not in readiness_proxy
    assert 'SPECIALIST_READINESS_ROUTE = "/diagnostics/specialist-readiness"' in specialist_bootstrap
    assert '"secrets_exposed": False' in specialist_bootstrap
    assert 'nico-specialist-session' in middleware
    assert 'type="password"' in login_page
    assert 'const ENGLISH_DESTINATION = "/assessment?tier=comprehensive#assessment"' in login_page
    assert 'const SPANISH_DESTINATION = "/es/assessment?tier=comprehensive#assessment"' in login_page
    assert "return requested" not in login_page
    assert 'SESSION_SIGNING_SECRET_ENV = "NICO_OPERATOR_SESSION_SIGNING_SECRET"' in specialist_access
    session_secret_body = specialist_access.split("def _session_secret()", 1)[1].split("def _b64url_encode", 1)[0]
    assert "NICO_ADMIN_TOKEN" not in session_secret_body
    assert "NICO_COMPREHENSIVE_OPERATOR_PASSWORD" not in session_secret_body
    assert "NICO_SARA_OPERATOR_PASSWORD" not in session_secret_body
    assert 'nico.api.specialist_ship_ready_bootstrap:app' in dockerfile
