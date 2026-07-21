from __future__ import annotations

import hashlib
import hmac

import pytest

from nico.provider_credentials import SecretValue
from nico.provider_webhook_verification import (
    ReplayGuard,
    WebhookVerificationError,
    verify_provider_webhook,
)


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_bitbucket_hmac_and_replay_protection() -> None:
    body = b'{"event":"repo:push"}'
    guard = ReplayGuard(max_age_seconds=60)
    headers = {
        "X-Hub-Signature": _signature("shared", body),
        "X-Request-UUID": "event-1",
        "X-NICO-Timestamp": "1000",
    }

    result = verify_provider_webhook(
        provider="bitbucket",
        secret=SecretValue("shared"),
        headers=headers,
        body=body,
        replay_guard=guard,
        now=1000,
    )
    assert result["verified"] is True
    assert result["event_id"] == "event-1"

    with pytest.raises(WebhookVerificationError, match="webhook_replay_detected"):
        verify_provider_webhook(
            provider="bitbucket",
            secret=SecretValue("shared"),
            headers=headers,
            body=body,
            replay_guard=guard,
            now=1000,
        )


def test_gitlab_token_uses_constant_time_secret_boundary() -> None:
    result = verify_provider_webhook(
        provider="gitlab",
        secret=SecretValue("token"),
        headers={
            "X-Gitlab-Token": "token",
            "X-Gitlab-Event-UUID": "gitlab-event",
            "X-NICO-Timestamp": "2000",
        },
        body=b"{}",
        replay_guard=ReplayGuard(max_age_seconds=60),
        now=2000,
    )
    assert result["provider"] == "gitlab"

    with pytest.raises(WebhookVerificationError, match="gitlab_webhook_token_invalid"):
        verify_provider_webhook(
            provider="gitlab",
            secret=SecretValue("token"),
            headers={"X-Gitlab-Token": "wrong"},
            body=b"{}",
        )


def test_azure_shared_signature_fails_closed() -> None:
    body = b"azure-event"
    with pytest.raises(WebhookVerificationError, match="webhook_signature_invalid"):
        verify_provider_webhook(
            provider="azure_devops",
            secret=SecretValue("shared"),
            headers={"X-NICO-Signature": "sha256=bad"},
            body=body,
        )


def test_stale_timestamp_is_rejected() -> None:
    body = b"{}"
    with pytest.raises(WebhookVerificationError, match="webhook_timestamp_outside_window"):
        verify_provider_webhook(
            provider="bitbucket",
            secret=SecretValue("shared"),
            headers={
                "X-Hub-Signature": _signature("shared", body),
                "X-Request-UUID": "event-old",
                "X-NICO-Timestamp": "1",
            },
            body=body,
            replay_guard=ReplayGuard(max_age_seconds=30),
            now=100,
        )
