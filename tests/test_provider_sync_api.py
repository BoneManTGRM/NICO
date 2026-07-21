from __future__ import annotations

import hashlib
import hmac
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.provider_credentials import SecretValue
from nico.provider_live_clients import ProviderCollection
from nico.provider_neutral_contract import ProviderKind
from nico.provider_sync_api import ProviderSyncRuntime, register_provider_sync_routes
from nico.provider_sync_service import ProviderSyncService, ProviderSyncStore


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


def _runtime(path: Path) -> ProviderSyncRuntime:
    store = ProviderSyncStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return ProviderSyncRuntime(
        service=ProviderSyncService(store, poll_interval_seconds=60),
        collectors={ProviderKind.GITLAB: FakeCollector()},
        webhook_secrets={ProviderKind.GITLAB: SecretValue("shared")},
    )


def test_collect_and_status_routes_preserve_read_only_truth(tmp_path: Path) -> None:
    app = FastAPI()
    register_provider_sync_routes(app, runtime=_runtime(tmp_path / "sync.db"))
    client = TestClient(app)

    collected = client.post(
        "/providers/gitlab/repositories/group/repo/collect",
        json={"revision": "a" * 40},
    )
    status = client.get("/providers/gitlab/repositories/group/repo/sync")

    assert collected.status_code == 200
    assert collected.json()["state"] == "ready"
    assert collected.json()["collected_revision"] == "a" * 40
    assert collected.json()["read_only"] is True
    assert collected.json()["client_delivery_allowed"] is False
    assert status.status_code == 200
    assert status.json()["integrity_sha256"] == collected.json()["integrity_sha256"]


def test_unconfigured_runtime_and_collector_fail_closed(tmp_path: Path) -> None:
    unconfigured = FastAPI()
    register_provider_sync_routes(unconfigured)
    response = TestClient(unconfigured).post(
        "/providers/gitlab/repositories/group/repo/collect",
        json={},
    )
    assert response.status_code == 503

    runtime = _runtime(tmp_path / "missing.db")
    runtime.collectors.clear()
    app = FastAPI()
    register_provider_sync_routes(app, runtime=runtime)
    missing = TestClient(app).post(
        "/providers/gitlab/repositories/group/repo/collect",
        json={},
    )
    assert missing.status_code == 422
    assert missing.json()["detail"] == "provider_collector_not_configured"


def test_verified_gitlab_webhook_schedules_pending_sync(tmp_path: Path, monkeypatch) -> None:
    app = FastAPI()
    runtime = _runtime(tmp_path / "webhook.db")
    register_provider_sync_routes(app, runtime=runtime)
    client = TestClient(app)

    monkeypatch.setattr("nico.provider_webhook_verification.time.time", lambda: 1000)
    response = client.post(
        "/providers/gitlab/repositories/group/repo/webhook",
        content=b'{"event":"push"}',
        headers={
            "X-Gitlab-Token": "shared",
            "X-Gitlab-Event-UUID": "event-1",
            "X-NICO-Timestamp": "1000",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "pending"
    assert response.json()["last_event_id"] == "event-1"
    assert response.json()["operation"] == "webhook_verified_and_scheduled"
    assert response.json()["client_delivery_allowed"] is False


def test_invalid_signature_and_replay_are_rejected(tmp_path: Path, monkeypatch) -> None:
    app = FastAPI()
    runtime = _runtime(tmp_path / "replay.db")
    register_provider_sync_routes(app, runtime=runtime)
    client = TestClient(app)
    monkeypatch.setattr("nico.provider_webhook_verification.time.time", lambda: 1000)

    bad = client.post(
        "/providers/gitlab/repositories/group/repo/webhook",
        content=b"{}",
        headers={"X-Gitlab-Token": "wrong", "Content-Type": "application/json"},
    )
    assert bad.status_code == 422

    headers = {
        "X-Gitlab-Token": "shared",
        "X-Gitlab-Event-UUID": "event-1",
        "X-NICO-Timestamp": "1000",
        "Content-Type": "application/json",
    }
    first = client.post("/providers/gitlab/repositories/group/repo/webhook", content=b"{}", headers=headers)
    replay = client.post("/providers/gitlab/repositories/group/repo/webhook", content=b"{}", headers=headers)
    assert first.status_code == 200
    assert replay.status_code == 422
    assert replay.json()["detail"] == "webhook_replay_detected"


def test_route_registration_is_idempotent_and_partial_groups_fail(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "routes.db")
    app = FastAPI()
    register_provider_sync_routes(app, runtime=runtime)
    count = len(app.routes)
    register_provider_sync_routes(app, runtime=runtime)
    assert len(app.routes) == count

    partial = FastAPI()

    @partial.get("/providers/{provider}/repositories/{repository_id:path}/sync")
    async def existing():
        return {}

    try:
        register_provider_sync_routes(partial, runtime=runtime)
    except RuntimeError as exc:
        assert str(exc) == "provider_sync_partial_route_group_detected"
    else:
        raise AssertionError("partial provider route group should fail")
