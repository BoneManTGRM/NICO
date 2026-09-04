from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "frontend": ROOT / ".github/workflows/frontend-production-release-proof.yml",
    "spanish": ROOT / ".github/workflows/spanish-comprehensive-production-proof.yml",
    "mobile": ROOT / ".github/workflows/mobile-restart-production-proof.yml",
    "webkit": ROOT / ".github/workflows/ios-webkit-paint-proof.yml",
    "unified": ROOT / ".github/workflows/two-service-production-acceptance.yml",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_github_actions_oidc_exchange_is_exact_release_and_workflow_bound() -> None:
    backend = _source(ROOT / "nico/github_actions_proof_session_v1.py")
    frontend = _source(ROOT / "apps/web/app/api/nico/github-actions-proof-session/route.ts")
    bootstrap = _source(ROOT / "nico/api/specialist_ship_ready_bootstrap.py")
    middleware = _source(ROOT / "nico/specialist_access_v1.py")

    assert 'AUDIENCE = "nico-production-proof"' in backend
    assert 'ISSUER = "https://token.actions.githubusercontent.com"' in backend
    assert 'REPOSITORY_ID = "1282576027"' in backend
    assert 'ENVIRONMENT = "production-smoke"' in backend
    assert '"release_sha": bool(expected_release_sha)' in backend
    assert '"workflow_ref": workflow_file in ALLOWED_WORKFLOW_FILES' in backend
    assert '"jti"' in backend and "_consume_jti" in backend
    assert 'new URL("/assessment/github-actions-proof-session", backend)' in frontend
    assert "httpOnly: true" in frontend
    assert 'sameSite: "strict"' in frontend
    assert 'secure: process.env.NODE_ENV === "production"' in frontend
    assert "install_github_actions_proof_session(app)" in bootstrap
    assert 'GITHUB_ACTIONS_PROOF_SESSION_ROUTE = "/assessment/github-actions-proof-session"' in middleware
    assert "if path in {SESSION_ROUTE, GITHUB_ACTIONS_PROOF_SESSION_ROUTE}" in middleware
    assert 'return path == "/assessment" or path.startswith(_PROTECTED_PREFIX)' in middleware


def test_live_proofs_use_oidc_sessions_without_password_secrets() -> None:
    spanish = _source(WORKFLOWS["spanish"])
    mobile = _source(WORKFLOWS["mobile"])
    webkit = _source(WORKFLOWS["webkit"])
    unified = _source(WORKFLOWS["unified"])

    for source in (spanish, mobile, webkit, unified):
        assert "id-token: write" in source
        assert "environment: production-smoke" in source
        assert "${{ secrets." not in source
        assert "NICO_ADMIN_TOKEN" not in source
        assert "NICO_COMPREHENSIVE_OPERATOR_PASSWORD" not in source
        assert "NICO_SARA_OPERATOR_PASSWORD" not in source
        assert "human_review_required" in source
        assert "client_delivery_allowed" in source

    assert "spanish_comprehensive_authenticated_live_acceptance_v4.py" in spanish
    assert "spanish_comprehensive_authenticated_existing_run_recovery_v2.py" in spanish
    assert "mobile_restart_authenticated_live_acceptance_v7.py" in mobile
    assert "mobile_restart_authenticated_webkit_acceptance_v7.py" in webkit
    assert "authenticated_completed_run_acceptance_v1.py" in unified


def test_frontend_release_proof_verifies_specialist_gate_not_public_workspace() -> None:
    workflow = _source(WORKFLOWS["frontend"])
    verifier = _source(ROOT / "scripts/production_specialist_release_identity_v1.py")

    assert "production_specialist_release_identity_v1.py" in workflow
    assert "production_frontend_release_identity.py" not in workflow
    assert 'redirect("/specialist-login")' in workflow
    assert 'redirect("/es/specialist-login")' in workflow
    assert "workspace_hidden_until_authentication" in verifier
    assert "unauthenticated_assessment_api_blocked" in verifier
    assert 'code != "specialist_authentication_required"' in verifier
    assert "specialist_readiness_green" in verifier


def test_proof_helpers_never_retain_oidc_or_session_values() -> None:
    client = _source(ROOT / "scripts/github_actions_proof_session_v1.py")
    completed = _source(ROOT / "scripts/authenticated_completed_run_acceptance_v1.py")
    browser = _source(ROOT / "scripts/authenticated_proof_browser_v1.py")

    assert '"session_cookie_value_exposed": False' in client
    assert '"oidc_token_exposed": False' in client
    assert '"session_cookie_value_exposed": False' in completed
    assert '"oidc_token_exposed": False' in completed
    assert "authenticate_browser_context" in browser
    assert "session_token" not in browser


def test_root_routes_are_fixed_locale_specialist_entrypoints() -> None:
    english_home = _source(ROOT / "apps/web/app/page.tsx")
    spanish_home = _source(ROOT / "apps/web/app/es/page.tsx")
    english_login = _source(ROOT / "apps/web/app/specialist-login/page.tsx")
    spanish_login = _source(ROOT / "apps/web/app/es/specialist-login/page.tsx")

    assert 'redirect("/specialist-login")' in english_home
    assert 'redirect("/es/specialist-login")' in spanish_home
    assert "URLSearchParams" not in english_login
    assert "URLSearchParams" not in spanish_login
    assert 'window.location.assign("/assessment?tier=comprehensive#assessment")' in english_login
    assert 'window.location.assign("/es/assessment?tier=comprehensive#assessment")' in spanish_login
