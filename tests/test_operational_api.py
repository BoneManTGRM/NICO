from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.notification_delivery import DeliveryResult, NotificationDispatcher, NotificationStore
from nico.operational_api import (
    HeaderOperationalAuthorizer,
    OperationalRuntime,
    register_operational_routes,
)
from nico.post_release_observability import MetricPoint
from nico.provider_credentials import SecretValue


class _DeliveredAdapter:
    destination = "email"

    def send(self, message):
        return DeliveryResult(True, provider_message_id=f"sent:{message.notification_id}")


def _metrics() -> tuple[MetricPoint, ...]:
    timestamp = "2026-07-21T00:00:00Z"
    return (
        MetricPoint("storage_available", 1, timestamp),
        MetricPoint("storage_latency_ms", 10, timestamp),
        MetricPoint("queue_depth", 0, timestamp),
        MetricPoint("provider_collection_failures", 0, timestamp),
        MetricPoint("report_generation_failures", 0, timestamp),
        MetricPoint("delivery_gate_blocks", 0, timestamp),
        MetricPoint("delivery_failures", 0, timestamp),
        MetricPoint("active_runs", 0, timestamp),
        MetricPoint("stale_runs", 0, timestamp),
    )


def _client(path: Path) -> TestClient:
    store = NotificationStore(lambda: sqlite3.connect(path), dialect="sqlite")
    runtime = OperationalRuntime(
        authorizer=HeaderOperationalAuthorizer(SecretValue("operational-token")),
        exact_sha_provider=lambda: "a" * 40,
        metric_provider=_metrics,
        log_sample_provider=lambda: ("authorization: <redacted>",),
        forbidden_log_value_provider=lambda: ("operational-token",),
        notification_store=store,
        notification_dispatcher=NotificationDispatcher(store, {"email": _DeliveredAdapter()}),
    )
    app = FastAPI()
    register_operational_routes(app, runtime=runtime)
    return TestClient(app)


def test_operational_health_requires_authorization_and_returns_safe_truth(tmp_path: Path) -> None:
    client = _client(tmp_path / "health.sqlite3")

    assert client.get("/internal/operational-health").status_code == 403
    response = client.get(
        "/internal/operational-health",
        headers={"X-NICO-Operational-Token": "operational-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["status"] == "healthy"
    assert payload["snapshot"]["exact_sha"] == "a" * 40
    assert payload["alerts"] == []
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
    assert "operational-token" not in str(payload)


def test_notification_enqueue_is_idempotent_and_dispatch_is_auditable(tmp_path: Path) -> None:
    client = _client(tmp_path / "delivery.sqlite3")
    headers = {"X-NICO-Operational-Token": "operational-token"}
    request = {
        "dedup_key": "provider-degraded:gitlab",
        "destination": "email",
        "severity": "high",
        "subject": "Provider degraded",
        "body": "Provider collection requires human review.",
        "exact_sha": "b" * 40,
        "evidence_fingerprint": "sha256:evidence",
        "created_at": "2026-07-21T00:00:00Z",
    }

    first = client.post("/internal/notifications/enqueue", headers=headers, json=request)
    second = client.post("/internal/notifications/enqueue", headers=headers, json=request)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["notification"]["notification_id"] == second.json()["notification"]["notification_id"]

    dispatched = client.post(
        "/internal/notifications/dispatch",
        headers=headers,
        json={"limit": 10},
    )
    assert dispatched.status_code == 200
    payload = dispatched.json()
    assert payload["notification_count"] == 1
    assert payload["notifications"][0]["status"] == "delivered"
    assert payload["notifications"][0]["provider_message_id"].startswith("sent:sha256:")
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False


def test_operational_routes_reject_unexpected_fields(tmp_path: Path) -> None:
    client = _client(tmp_path / "invalid.sqlite3")
    headers = {"X-NICO-Operational-Token": "operational-token"}

    enqueue = client.post(
        "/internal/notifications/enqueue",
        headers=headers,
        json={"raw_secret": "must-not-be-accepted"},
    )
    dispatch = client.post(
        "/internal/notifications/dispatch",
        headers=headers,
        json={"limit": 1, "unexpected": True},
    )
    assert enqueue.status_code == 422
    assert dispatch.status_code == 422
