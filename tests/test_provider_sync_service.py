from __future__ import annotations

import hashlib
import hmac
import sqlite3
from pathlib import Path

from nico.provider_credentials import SecretValue
from nico.provider_live_clients import ProviderClientError, ProviderCollection
from nico.provider_neutral_contract import ProviderKind
from nico.provider_sync_service import ProviderSyncService, ProviderSyncStore
from nico.provider_webhook_verification import ReplayGuard


class FakeGitLabCollector:
    provider = ProviderKind.GITLAB

    def __init__(self, *, fail: ProviderClientError | None = None) -> None:
        self.fail = fail

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        if self.fail is not None:
            raise self.fail
        exact = revision or "a" * 40
        return ProviderCollection(
            provider=ProviderKind.GITLAB,
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
            pages_fetched=4,
            requests_made=5,
            collected_at="2026-07-21T00:00:00Z",
        )


def _service(path: Path) -> ProviderSyncService:
    store = ProviderSyncStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return ProviderSyncService(store, poll_interval_seconds=60, max_failure_backoff_seconds=600)


def test_successful_collection_persists_ready_exact_revision(tmp_path: Path) -> None:
    path = tmp_path / "sync.db"
    service = _service(path)
    result = service.collect(
        FakeGitLabCollector(),
        repository_id="group/repo",
        requested_revision="a" * 40,
    )
    restarted = _service(path)
    loaded = restarted.ensure(provider="gitlab", repository_id="group/repo")

    assert result["state"] == "ready"
    assert result["collected_revision"] == "a" * 40
    assert result["requests_made"] == 5
    assert result["pages_fetched"] == 4
    assert result["evidence_digest"].startswith("sha256:")
    assert loaded["collected_revision"] == result["collected_revision"]
    assert loaded["integrity_sha256"] == result["integrity_sha256"]
    assert loaded["read_only"] is True
    assert loaded["client_delivery_allowed"] is False


def test_auth_rate_limit_and_outage_never_appear_ready(tmp_path: Path) -> None:
    cases = (
        (ProviderClientError("provider_auth_failed", status_code=401), "auth_failed"),
        (ProviderClientError("provider_rate_limited", status_code=429, retryable=True), "rate_limited"),
        (ProviderClientError("provider_service_unavailable", status_code=503, retryable=True), "unavailable"),
    )
    for index, (error, expected) in enumerate(cases):
        service = _service(tmp_path / f"sync-{index}.db")
        result = service.collect(
            FakeGitLabCollector(fail=error),
            repository_id="group/repo",
        )
        assert result["state"] == expected
        assert result["limitation_reason"] == error.code
        assert result["failure_count"] == 1
        assert result["client_delivery_allowed"] is False


def test_verified_webhook_marks_sync_pending_and_replay_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path / "webhook.db")
    body = b'{"event":"push"}'
    signature = "sha256=" + hmac.new(b"shared", body, hashlib.sha256).hexdigest()
    headers = {
        "X-Hub-Signature": signature,
        "X-Request-UUID": "event-1",
        "X-NICO-Timestamp": "1000",
    }
    guard = ReplayGuard(max_age_seconds=60)

    result = service.accept_webhook(
        provider="bitbucket",
        repository_id="workspace/repo",
        secret=SecretValue("shared"),
        headers=headers,
        body=body,
        replay_guard=guard,
        now=1000,
    )
    assert result["state"] == "pending"
    assert result["last_event_id"] == "event-1"
    assert result["last_event_sha256"] == hashlib.sha256(body).hexdigest()


def test_failure_backoff_increases_without_losing_identity(tmp_path: Path) -> None:
    service = _service(tmp_path / "backoff.db")
    collector = FakeGitLabCollector(
        fail=ProviderClientError("provider_network_unavailable", retryable=True)
    )
    first = service.collect(collector, repository_id="group/repo")
    second = service.collect(collector, repository_id="group/repo")

    assert first["failure_count"] == 1
    assert second["failure_count"] == 2
    assert second["provider"] == "gitlab"
    assert second["repository_id"] == "group/repo"
    assert second["revision"] > first["revision"]
