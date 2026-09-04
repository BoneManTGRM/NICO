from __future__ import annotations


def test_verified_specialist_readiness_self_tests_credentials_without_exposure(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "specialist-test-password")
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "independent-test-signing-secret-with-at-least-thirty-two-bytes",
    )
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "railway-deployment-test")

    from nico.api import specialist_ship_verified_bootstrap as bootstrap

    base = {
        "specialist_access_installed": True,
        "authenticated_comprehensive_routes_enforced": True,
        "operator_password_configured": True,
        "session_signing_configured": True,
        "credential_separation_verified": True,
        "rate_limiting_enabled": True,
        "comprehensive_runtime_ready": True,
        "durable_storage_verified": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "secrets_exposed": False,
        "release_provenance": {
            "deployment_identity_established": True,
            "backend_build_commit": "a" * 40,
            "railway_deployment_id": "railway-deployment-test",
            "frontend_identity_established": False,
            "frontend_build_commit": "unavailable",
        },
    }
    monkeypatch.setattr(bootstrap, "base_specialist_readiness", lambda: dict(base))

    result = bootstrap.verified_specialist_readiness()

    assert result["status"] == "ready"
    assert result["operator_credential_self_test"] is True
    assert result["session_round_trip_self_test"] is True
    assert result["positive_authentication_verified_server_side"] is True
    assert result["backend_release_identity_complete"] is True
    assert result["frontend_identity_available"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["secrets_exposed"] is False
    serialized = str(result)
    assert "specialist-test-password" not in serialized
    assert "independent-test-signing-secret" not in serialized


def test_verified_readiness_fails_closed_when_positive_authentication_fails(monkeypatch):
    monkeypatch.delenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", raising=False)
    monkeypatch.delenv("NICO_SARA_OPERATOR_PASSWORD", raising=False)
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "independent-test-signing-secret-with-at-least-thirty-two-bytes",
    )

    from nico.api import specialist_ship_verified_bootstrap as bootstrap

    base = {
        "specialist_access_installed": True,
        "authenticated_comprehensive_routes_enforced": True,
        "operator_password_configured": False,
        "session_signing_configured": True,
        "credential_separation_verified": True,
        "rate_limiting_enabled": True,
        "comprehensive_runtime_ready": True,
        "durable_storage_verified": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "secrets_exposed": False,
        "release_provenance": {
            "deployment_identity_established": True,
            "backend_build_commit": "a" * 40,
            "railway_deployment_id": "railway-deployment-test",
        },
    }
    monkeypatch.setattr(bootstrap, "base_specialist_readiness", lambda: dict(base))

    result = bootstrap.verified_specialist_readiness()

    assert result["status"] == "blocked"
    assert result["operator_credential_self_test"] is False
    assert result["positive_authentication_verified_server_side"] is False
