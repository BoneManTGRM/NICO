from pathlib import Path


def test_frontend_proxy_accepts_restricted_session_without_exposing_it():
    proxy = Path("apps/web/app/api/nico/assessment/[...path]/route.ts").read_text()
    exchange = Path("apps/web/app/api/nico/ci-session/route.ts").read_text()
    auth = Path("scripts/github_actions_nico_proof_auth_v1.py").read_text()
    live = Path(
        "scripts/spanish_comprehensive_authenticated_live_acceptance_v1.py"
    ).read_text()

    assert 'request.headers.get("x-nico-operator-session")' in proxy
    assert 'headers.set("X-NICO-Operator-Session", session)' in proxy
    assert "specialist_session_identity_conflict" in proxy
    assert "/assessment/github-actions-production-proof/session" in exchange
    assert '"Cache-Control": "no-store, private, max-age=0"' in exchange
    assert "ACTIONS_ID_TOKEN_REQUEST_TOKEN" in auth
    assert "print(session" not in auth
    assert "write_text(session" not in auth
    assert "write_bytes(session" not in auth

    # Retain only a boolean proving that the credential was discarded. Never retain
    # the credential itself under either the generic or proof-specific field name.
    assert 'result["production_proof_session_token_retained"] = False' in live
    assert 'result["session_token"]' not in live
    assert "result['session_token']" not in live
    assert 'result["production_proof_session_token"]' not in live
    assert "result['production_proof_session_token']" not in live
