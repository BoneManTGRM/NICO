from __future__ import annotations

import hashlib
import hmac
import json
from email.message import EmailMessage

import httpx

from nico.notification_adapters import EmailNotificationAdapter, SignedWebhookNotificationAdapter
from nico.notification_delivery import build_notification
from nico.provider_credentials import SecretValue


def _message():
    return build_notification(
        dedup_key="event-1",
        destination="webhook",
        severity="high",
        subject="Provider degraded",
        body="Provider collection requires attention.",
        exact_sha="a" * 40,
        evidence_fingerprint="sha256:evidence",
        created_at="2026-07-21T00:00:00Z",
    )


def test_signed_webhook_uses_hmac_idempotency_and_safe_payload() -> None:
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["headers"] = dict(request.headers)
        observed["body"] = request.content
        return httpx.Response(202, headers={"X-Message-ID": "provider-1"})

    adapter = SignedWebhookNotificationAdapter(
        destination="webhook",
        url="https://alerts.example.com/nico",
        signing_secret=SecretValue("shared-secret"),
        allowed_hosts=("alerts.example.com",),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = adapter.send(_message())

    assert result.delivered is True
    assert result.provider_message_id == "provider-1"
    assert observed["headers"]["idempotency-key"] == _message().notification_id
    expected = hmac.new(b"shared-secret", observed["body"], hashlib.sha256).hexdigest()
    assert observed["headers"]["x-nico-signature"] == f"sha256={expected}"
    payload = json.loads(observed["body"])
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
    assert "shared-secret" not in str(payload)


def test_webhook_maps_retryable_and_terminal_statuses() -> None:
    statuses = iter((429, 503, 400))

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(next(statuses))

    adapter = SignedWebhookNotificationAdapter(
        destination="webhook",
        url="https://alerts.example.com/nico",
        signing_secret=SecretValue("shared-secret"),
        allowed_hosts=("alerts.example.com",),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rate = adapter.send(_message())
    outage = adapter.send(_message())
    rejected = adapter.send(_message())
    assert rate.retryable is True
    assert outage.retryable is True
    assert rejected.retryable is False
    assert rejected.error_code == "notification_webhook_rejected_400"


def test_email_adapter_builds_auditable_message() -> None:
    observed: list[EmailMessage] = []

    def sender(message: EmailMessage) -> str:
        observed.append(message)
        return "smtp-message-1"

    adapter = EmailNotificationAdapter(
        destination="email",
        from_address="nico@example.com",
        to_addresses=("owner@example.com",),
        sender=sender,
    )
    result = adapter.send(_message())

    assert result.delivered is True
    assert result.provider_message_id == "smtp-message-1"
    assert observed[0]["Subject"] == "[HIGH] Provider degraded"
    body = observed[0].get_content()
    assert "Exact SHA: " + "a" * 40 in body
    assert "Human review required: yes" in body
    assert "Client delivery allowed: no" in body
