from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from nico.notification_delivery import (
    DeliveryResult,
    NotificationDispatcher,
    NotificationStore,
    build_notification,
)


class FakeAdapter:
    destination = "email"

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def send(self, message):
        self.calls += 1
        return self.results.pop(0)


def _store(path: Path) -> NotificationStore:
    store = NotificationStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _message():
    return build_notification(
        dedup_key="event-1",
        destination="email",
        severity="high",
        subject="Provider degraded",
        body="Provider collection requires attention.",
        exact_sha="a" * 40,
        evidence_fingerprint="sha256:evidence",
        created_at="2026-07-21T00:00:00Z",
    )


def test_enqueue_is_idempotent_by_event_and_destination(tmp_path: Path) -> None:
    store = _store(tmp_path / "notify.db")
    first = store.enqueue(_message())
    duplicate = store.enqueue(_message())

    assert duplicate.notification_id == first.notification_id
    assert len(store.due(now=datetime(2026, 7, 21, tzinfo=timezone.utc))) == 1


def test_retry_backoff_and_eventual_delivery_are_durable(tmp_path: Path) -> None:
    path = tmp_path / "retry.db"
    store = _store(path)
    message = store.enqueue(_message())
    adapter = FakeAdapter(
        [
            DeliveryResult(False, retryable=True, error_code="temporary_failure"),
            DeliveryResult(True, provider_message_id="provider-1"),
        ]
    )
    dispatcher = NotificationDispatcher(
        store,
        {"email": adapter},
        base_retry_seconds=60,
        max_retry_seconds=600,
    )
    first = dispatcher.dispatch(message, now=datetime(2026, 7, 21, tzinfo=timezone.utc))
    assert first.status == "retry"
    assert first.attempts == 1
    assert first.last_error == "temporary_failure"

    restarted = NotificationDispatcher(_store(path), {"email": adapter})
    due = restarted.run_due(now=datetime(2026, 7, 21, 0, 2, tzinfo=timezone.utc))
    assert len(due) == 1
    assert due[0].status == "delivered"
    assert due[0].attempts == 2
    assert due[0].provider_message_id == "provider-1"
    assert due[0].delivered_at


def test_missing_adapter_fails_without_infinite_retry(tmp_path: Path) -> None:
    store = _store(tmp_path / "missing.db")
    message = store.enqueue(_message())
    result = NotificationDispatcher(store, {}).dispatch(message)
    assert result.status == "failed"
    assert result.last_error == "notification_adapter_not_configured"
    assert result.next_attempt_at == ""


def test_non_retryable_failure_is_terminal(tmp_path: Path) -> None:
    store = _store(tmp_path / "terminal.db")
    message = store.enqueue(_message())
    adapter = FakeAdapter([DeliveryResult(False, retryable=False, error_code="recipient_rejected")])
    result = NotificationDispatcher(store, {"email": adapter}).dispatch(message)
    assert result.status == "failed"
    assert result.attempts == 1
    assert result.last_error == "recipient_rejected"
