from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.post_release_production_bootstrap import (
    DIAGNOSTICS_ROUTE,
    PostReleaseDependencies,
    PostReleaseRuntimeConfig,
    install_post_release_runtime,
)
from nico.provider_credentials import SecretValue
from nico.provider_live_clients import ProviderCollection
from nico.provider_neutral_contract import ProviderKind


class FakeCollector:
    provider = ProviderKind.GITLAB

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        exact = revision or "a" * 40
        return ProviderCollection(
            provider=self.provider,
            repository_id="17",
            revision=exact,
            payload={
                "instance_url": "https://gitlab.example.com",
                "project": {
                    "id": 17,
                    "path": "repo",
                    "path_with_namespace": repository_id,
                    "namespace": "group",
                    "default_branch": "main",
                },
                "revision": exact,
                "merge_requests": [],
                "pipelines": [{"id": 1, "sha": exact, "ref": "main", "status": "success"}],
                "scopes": ["read_api", "read_repository"],
                "collected_at": "2026-07-21T00:00:00Z",
            },
            pages_fetched=2,
            requests_made=3,
            collected_at="2026-07-21T00:00:00Z",
        )


def _connection_factory(path: Path):
    return lambda: sqlite3.connect(path)


def _paths(app: FastAPI) -> set[str]:
    return {str(route.path) for route in app.routes}


def test_disabled_runtime_adds_only_safe_diagnostics() -> None:
    app = FastAPI()
    status = install_post_release_runtime(
        app,
        config=PostReleaseRuntimeConfig(),
        dependencies=PostReleaseDependencies(),
    )

    assert status["status"] == "disabled"
    assert status["provider_sync"]["status"] == "disabled"
    assert status["monitor_execute"]["status"] == "disabled"
    assert DIAGNOSTICS_ROUTE in _paths(app)
    assert not any(path.startswith("/providers/") for path in _paths(app))
    assert not any(path.startswith("/monitor/") for path in _paths(app))

    payload = TestClient(app).get(DIAGNOSTICS_ROUTE).json()
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
    assert payload["production_execution_requires_explicit_approval"] is True


def test_enabled_features_without_database_remain_blocked_and_add_no_partial_routes() -> None:
    app = FastAPI()
    status = install_post_release_runtime(
        app,
        config=PostReleaseRuntimeConfig(
            enable_provider_sync=True,
            enable_monitor_execute=True,
        ),
        dependencies=PostReleaseDependencies(
            provider_collectors={ProviderKind.GITLAB: FakeCollector()},
        ),
    )

    assert status["status"] == "blocked"
    assert status["provider_sync"]["reason"] == "provider_sync_connection_factory_missing"
    assert status["monitor_execute"]["reason"] == "monitor_execute_connection_factory_missing"
    assert not any(path.startswith("/providers/") for path in _paths(app))
    assert not any(path.startswith("/monitor/") for path in _paths(app))


def test_fully_configured_runtime_mounts_each_route_once_and_survives_reinstall(tmp_path: Path) -> None:
    app = FastAPI()
    dependencies = PostReleaseDependencies(
        connection_factory=_connection_factory(tmp_path / "post-release.db"),
        provider_collectors={ProviderKind.GITLAB: FakeCollector()},
        provider_webhook_secrets={ProviderKind.GITLAB: SecretValue("shared")},
    )
    config = PostReleaseRuntimeConfig(
        enable_provider_sync=True,
        enable_monitor_execute=True,
        database_dialect="sqlite",
        provider_poll_interval_seconds=60,
        provider_max_failure_backoff_seconds=600,
    )

    first = install_post_release_runtime(app, config=config, dependencies=dependencies)
    route_count = len(app.routes)
    second = install_post_release_runtime(app, config=config, dependencies=dependencies)

    assert first["status"] == "ready"
    assert second["status"] == "ready"
    assert len(app.routes) == route_count
    assert all(value == 1 for value in first["provider_sync"]["route_counts"].values())
    assert all(value == 1 for value in first["monitor_execute"]["route_counts"].values())
    assert first["provider_sync"]["configured_collectors"] == ["gitlab"]
    assert first["provider_sync"]["configured_webhook_secrets"] == ["gitlab"]
    assert first["monitor_execute"]["approval_expiry_enforced"] is True
    assert first["monitor_execute"]["approval_revocation_enforced"] is True
    assert first["client_delivery_allowed"] is False

    client = TestClient(app)
    collected = client.post(
        "/providers/gitlab/repositories/group/repo/collect",
        json={"revision": "a" * 40},
    )
    created = client.post(
        "/monitor/work-items",
        json={
            "work_item_id": "work-1",
            "repository": "BoneManTGRM/NICO",
            "immutable_sha": "a" * 40,
            "customer_id": "customer-1",
            "project_id": "project-1",
            "evidence_id": "evidence-1",
            "finding": {"finding_id": "F-1", "severity": "high"},
        },
    )
    assert collected.status_code == 200
    assert collected.json()["state"] == "ready"
    assert created.status_code == 200
    assert created.json()["state"] == "observed"
    assert created.json()["production_execution_requires_explicit_approval"] is True


def test_collector_kind_mismatch_fails_before_route_registration(tmp_path: Path) -> None:
    app = FastAPI()
    status = install_post_release_runtime(
        app,
        config=PostReleaseRuntimeConfig(enable_provider_sync=True),
        dependencies=PostReleaseDependencies(
            connection_factory=_connection_factory(tmp_path / "mismatch.db"),
            provider_collectors={ProviderKind.BITBUCKET: FakeCollector()},
        ),
    )
    assert status["status"] == "blocked"
    assert status["provider_sync"]["reason"] == "provider_collector_kind_mismatch"
    assert not any(path.startswith("/providers/") for path in _paths(app))


def test_webhook_secret_without_matching_collector_is_blocked(tmp_path: Path) -> None:
    app = FastAPI()
    status = install_post_release_runtime(
        app,
        config=PostReleaseRuntimeConfig(enable_provider_sync=True),
        dependencies=PostReleaseDependencies(
            connection_factory=_connection_factory(tmp_path / "secret.db"),
            provider_collectors={ProviderKind.GITLAB: FakeCollector()},
            provider_webhook_secrets={ProviderKind.BITBUCKET: SecretValue("shared")},
        ),
    )
    assert status["provider_sync"]["status"] == "blocked"
    assert status["provider_sync"]["reason"] == "provider_webhook_secret_without_collector"
    assert not any(path.startswith("/providers/") for path in _paths(app))
