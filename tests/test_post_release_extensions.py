from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.api.post_release_full_app import build_app


def _paths(app: FastAPI) -> set[str]:
    return {str(route.path) for route in app.routes}


def _sqlite_environ(tmp_path: Path) -> dict[str, str]:
    return {
        "NICO_ENABLE_SQLITE_DURABLE_STORAGE": "true",
        "NICO_ALLOW_NON_VOLUME_SQLITE": "true",
        "NICO_POST_RELEASE_SQLITE_PATH": str(tmp_path / "extensions.sqlite3"),
    }


def test_extensions_are_disabled_by_default() -> None:
    app = build_app(base_app=FastAPI(), environ={})
    status = app.state.nico_post_release_runtime

    assert status["extensions"]["provider_admin"]["status"] == "disabled"
    assert status["extensions"]["operational_api"]["status"] == "disabled"
    assert not any(path.startswith("/admin/providers/") for path in _paths(app))
    assert not any(path.startswith("/internal/") for path in _paths(app))
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False


def test_provider_admin_mounts_only_with_database_token_and_collector(tmp_path: Path) -> None:
    admin_token = "admin-control-token"
    provider_token = "gitlab-provider-token"
    environ = {
        **_sqlite_environ(tmp_path),
        "NICO_ENABLE_PROVIDER_ADMIN": "true",
        "NICO_PROVIDER_ADMIN_TOKEN": admin_token,
        "NICO_GITLAB_URL": "https://gitlab.example.com",
        "NICO_GITLAB_TOKEN": provider_token,
    }
    app = build_app(base_app=FastAPI(), environ=environ)
    status = app.state.nico_post_release_runtime
    rendered = str(status)

    assert status["extensions"]["provider_admin"]["status"] == "ready"
    assert status["extensions"]["provider_admin"]["collectors"] == ["gitlab"]
    assert any(path.startswith("/admin/providers/") for path in _paths(app))
    assert admin_token not in rendered
    assert provider_token not in rendered
    assert status["extensions"]["provider_admin"]["credential_rotation_dual_control"] is True

    unauthorized = TestClient(app).get(
        "/admin/providers/gitlab/credentials/gitlab-prod/versions"
    )
    assert unauthorized.status_code == 403
    authorized = TestClient(app).get(
        "/admin/providers/gitlab/credentials/gitlab-prod/versions",
        headers={"X-NICO-Admin-Token": admin_token},
    )
    assert authorized.status_code == 200
    assert authorized.json()["versions"] == []
    assert authorized.json()["client_delivery_allowed"] is False


def test_operational_api_mounts_with_exact_sha_and_notification_adapter(tmp_path: Path) -> None:
    operational_token = "operations-control-token"
    webhook_secret = "notification-signing-secret"
    environ = {
        **_sqlite_environ(tmp_path),
        "NICO_ENABLE_OPERATIONAL_API": "true",
        "NICO_OPERATIONAL_TOKEN": operational_token,
        "NICO_EXACT_SHA": "a" * 40,
        "NICO_NOTIFICATION_WEBHOOK_URL": "https://alerts.example.com/nico",
        "NICO_NOTIFICATION_WEBHOOK_SECRET": webhook_secret,
    }
    app = build_app(base_app=FastAPI(), environ=environ)
    status = app.state.nico_post_release_runtime
    rendered = str(status)

    assert status["extensions"]["operational_api"]["status"] == "ready"
    assert status["extensions"]["operational_api"]["adapters"] == ["webhook"]
    assert "/internal/operational-health" in _paths(app)
    assert operational_token not in rendered
    assert webhook_secret not in rendered

    response = TestClient(app).get(
        "/internal/operational-health",
        headers={"X-NICO-Operational-Token": operational_token},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["exact_sha"] == "a" * 40
    assert payload["snapshot"]["status"] == "healthy"
    assert payload["client_delivery_allowed"] is False


def test_enabled_extensions_fail_closed_without_required_configuration(tmp_path: Path) -> None:
    app = build_app(
        base_app=FastAPI(),
        environ={
            **_sqlite_environ(tmp_path),
            "NICO_ENABLE_PROVIDER_ADMIN": "true",
            "NICO_ENABLE_OPERATIONAL_API": "true",
        },
    )
    status = app.state.nico_post_release_runtime["extensions"]

    assert status["provider_admin"]["status"] == "blocked"
    assert status["provider_admin"]["reason"] == "provider_admin_token_not_configured"
    assert status["operational_api"]["status"] == "blocked"
    assert status["operational_api"]["reason"] == "operational_token_not_configured"
    assert not any(path.startswith("/admin/providers/") for path in _paths(app))
    assert not any(path.startswith("/internal/") for path in _paths(app))
