from pathlib import Path


def test_specialist_frontend_and_runtime_contracts_are_fail_closed():
    session_route = Path("apps/web/app/api/nico/operator-session/route.ts").read_text()
    assessment_proxy = Path("apps/web/app/api/nico/assessment/[...path]/route.ts").read_text()
    login_page = Path("apps/web/app/specialist-login/page.tsx").read_text()
    middleware = Path("apps/web/middleware.ts").read_text()
    dockerfile = Path("Dockerfile").read_text()

    assert 'httpOnly: true' in session_route
    assert 'sameSite: "strict"' in session_route
    assert 'secure: process.env.NODE_ENV === "production"' in session_route
    assert 'X-NICO-Operator-Session' in assessment_proxy
    assert 'specialist_authentication_required' in assessment_proxy
    assert 'nico-specialist-session' in middleware
    assert 'type="password"' in login_page
    assert 'nico.api.specialist_ship_ready_bootstrap:app' in dockerfile
