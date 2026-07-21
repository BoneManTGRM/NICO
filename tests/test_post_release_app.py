from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.api.post_release_app import build_app


def _paths(app: FastAPI) -> set[str]:
    return {str(route.path) for route in app.routes}


def test_default_environment_keeps_new_runtime_disabled() -> None:
    app = build_app(base_app=FastAPI(), environ={})
    status = app.state.nico_post_release_runtime

    assert status["status"] == "disabled"
    assert status["storage"]["configured"] is False
    assert status["provider_configuration"]["collectors"] == []
    assert not any(path.startswith("/providers/") for path in _paths(app))
    assert not any(path.startswith("/monitor/") for path in _paths(app))
    diagnostics = TestClient(app).get("/diagnostics/post-release-runtime").json()
    assert diagnostics["client_delivery_allowed"] is False
    assert diagnostics["production_execution_requires_explicit_approval"] is True


def test_monitor_runtime_requires_explicit_flag_and_durable_database(tmp_path: Path) -> None:
    blocked = build_app(
        base_app=FastAPI(),
        environ={"NICO_ENABLE_MONITOR_EXECUTE": "true"},
    )
    assert blocked.state.nico_post_release_runtime["status"] == "blocked"
    assert not any(path.startswith("/monitor/") for path in _paths(blocked))

    ready = build_app(
        base_app=FastAPI(),
        environ={
            "NICO_ENABLE_MONITOR_EXECUTE": "true",
            "NICO_ENABLE_SQLITE_DURABLE_STORAGE": "true",
            "NICO_ALLOW_NON_VOLUME_SQLITE": "true",
            "NICO_POST_RELEASE_SQLITE_PATH": str(tmp_path / "runtime.sqlite3"),
        },
    )
    status = ready.state.nico_post_release_runtime
    assert status["status"] == "ready"
    assert status["storage"]["adapter"] == "railway_volume_sqlite"
    assert status["monitor_execute"]["approval_expiry_enforced"] is True
    assert any(path == "/monitor/work-items" for path in _paths(ready))


def test_provider_runtime_configures_read_only_gitlab_without_network_call(tmp_path: Path) -> None:
    token = "provider-token-value"
    app = build_app(
        base_app=FastAPI(),
        environ={
            "NICO_ENABLE_PROVIDER_SYNC": "true",
            "NICO_ENABLE_SQLITE_DURABLE_STORAGE": "true",
            "NICO_ALLOW_NON_VOLUME_SQLITE": "true",
            "NICO_POST_RELEASE_SQLITE_PATH": str(tmp_path / "providers.sqlite3"),
            "NICO_GITLAB_URL": "https://gitlab.example.com",
            "NICO_GITLAB_TOKEN": token,
            "NICO_GITLAB_WEBHOOK_SECRET": "webhook-secret",
            "NICO_PROVIDER_POLL_INTERVAL_SECONDS": "60",
            "NICO_PROVIDER_MAX_BACKOFF_SECONDS": "600",
        },
    )
    status = app.state.nico_post_release_runtime
    rendered = str(status)

    assert status["status"] == "ready"
    assert status["provider_sync"]["configured_collectors"] == ["gitlab"]
    assert status["provider_sync"]["configured_webhook_secrets"] == ["gitlab"]
    assert status["provider_configuration"]["raw_secret_exposed"] is False
    assert token not in rendered
    assert "webhook-secret" not in rendered
    assert any(path.startswith("/providers/") for path in _paths(app))


def test_provider_flag_without_collector_is_blocked_and_adds_no_routes(tmp_path: Path) -> None:
    app = build_app(
        base_app=FastAPI(),
        environ={
            "NICO_ENABLE_PROVIDER_SYNC": "true",
            "NICO_ENABLE_SQLITE_DURABLE_STORAGE": "true",
            "NICO_ALLOW_NON_VOLUME_SQLITE": "true",
            "NICO_POST_RELEASE_SQLITE_PATH": str(tmp_path / "providers.sqlite3"),
        },
    )
    status = app.state.nico_post_release_runtime
    assert status["status"] == "blocked"
    assert status["provider_sync"]["reason"] == "provider_collectors_missing"
    assert not any(path.startswith("/providers/") for path in _paths(app))


def test_invalid_database_url_and_non_volume_sqlite_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="database_url_must_be_postgres"):
        build_app(
            base_app=FastAPI(),
            environ={
                "NICO_ENABLE_MONITOR_EXECUTE": "true",
                "DATABASE_URL": "mysql://unsupported",
            },
        )

    with pytest.raises(RuntimeError, match="sqlite_requires_persistent_data_path"):
        build_app(
            base_app=FastAPI(),
            environ={
                "NICO_ENABLE_MONITOR_EXECUTE": "true",
                "NICO_ENABLE_SQLITE_DURABLE_STORAGE": "true",
                "NICO_POST_RELEASE_SQLITE_PATH": str(tmp_path / "not-volume.sqlite3"),
            },
        )


def test_cloud_and_data_center_bitbucket_cannot_share_one_provider_runtime(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="multiple_bitbucket_collectors"):
        build_app(
            base_app=FastAPI(),
            environ={
                "NICO_ENABLE_PROVIDER_SYNC": "true",
                "NICO_ENABLE_SQLITE_DURABLE_STORAGE": "true",
                "NICO_ALLOW_NON_VOLUME_SQLITE": "true",
                "NICO_POST_RELEASE_SQLITE_PATH": str(tmp_path / "bitbucket.sqlite3"),
                "NICO_BITBUCKET_CLOUD_TOKEN": "cloud-token",
                "NICO_BITBUCKET_DC_URL": "https://bitbucket.example.com",
                "NICO_BITBUCKET_DC_TOKEN": "dc-token",
            },
        )
