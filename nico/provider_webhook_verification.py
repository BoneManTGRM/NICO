from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Mapping

from nico.provider_credentials import SecretValue
from nico.provider_neutral_contract import ProviderKind, normalize_provider


class WebhookVerificationError(RuntimeError):
    pass


@dataclass
class ReplayGuard:
    max_age_seconds: int = 300
    max_entries: int = 10_000
    _seen: dict[str, int] = field(default_factory=dict)

    def verify(self, *, event_id: str, timestamp: int, now: int | None = None) -> None:
        current = int(time.time() if now is None else now)
        if not event_id:
            raise WebhookVerificationError("webhook_event_id_required")
        if timestamp <= 0:
            raise WebhookVerificationError("webhook_timestamp_required")
        if abs(current - timestamp) > self.max_age_seconds:
            raise WebhookVerificationError("webhook_timestamp_outside_window")
        self._prune(current)
        if event_id in self._seen:
            raise WebhookVerificationError("webhook_replay_detected")
        self._seen[event_id] = timestamp
        if len(self._seen) > self.max_entries:
            oldest = sorted(self._seen.items(), key=lambda item: item[1])
            for key, _ in oldest[: len(self._seen) - self.max_entries]:
                self._seen.pop(key, None)

    def _prune(self, now: int) -> None:
        cutoff = now - self.max_age_seconds
        stale = [key for key, timestamp in self._seen.items() if timestamp < cutoff]
        for key in stale:
            self._seen.pop(key, None)


def _header(headers: Mapping[str, str], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value or "").strip()
    return ""


def _hex_signature(secret: SecretValue, body: bytes) -> str:
    return hmac.new(secret.reveal().encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_hmac_sha256(
    *,
    secret: SecretValue,
    body: bytes,
    supplied_signature: str,
    accepted_prefixes: tuple[str, ...] = ("sha256=", ""),
) -> None:
    token = str(supplied_signature or "").strip()
    for prefix in accepted_prefixes:
        candidate = token[len(prefix) :] if prefix and token.startswith(prefix) else token if not prefix else ""
        if candidate and hmac.compare_digest(_hex_signature(secret, body), candidate.lower()):
            return
    raise WebhookVerificationError("webhook_signature_invalid")


def verify_provider_webhook(
    *,
    provider: ProviderKind | str,
    secret: SecretValue,
    headers: Mapping[str, str],
    body: bytes,
    replay_guard: ReplayGuard | None = None,
    now: int | None = None,
) -> dict[str, object]:
    kind = provider if isinstance(provider, ProviderKind) else normalize_provider(provider)
    event_id = ""
    timestamp_text = ""

    if kind is ProviderKind.GITLAB:
        supplied = _header(headers, "X-Gitlab-Token")
        if not supplied or not secret.matches(supplied):
            raise WebhookVerificationError("gitlab_webhook_token_invalid")
        event_id = _header(headers, "X-Gitlab-Event-UUID") or _header(headers, "Idempotency-Key")
        timestamp_text = _header(headers, "X-NICO-Timestamp")
    elif kind is ProviderKind.BITBUCKET:
        verify_hmac_sha256(
            secret=secret,
            body=body,
            supplied_signature=_header(headers, "X-Hub-Signature"),
        )
        event_id = _header(headers, "X-Request-UUID") or _header(headers, "X-Hook-UUID")
        timestamp_text = _header(headers, "X-NICO-Timestamp")
    elif kind is ProviderKind.AZURE_DEVOPS:
        verify_hmac_sha256(
            secret=secret,
            body=body,
            supplied_signature=_header(headers, "X-NICO-Signature"),
        )
        event_id = _header(headers, "X-VSS-ActivityId") or _header(headers, "X-NICO-Event-ID")
        timestamp_text = _header(headers, "X-NICO-Timestamp")
    else:
        raise WebhookVerificationError("provider_webhook_not_supported")

    timestamp = 0
    if timestamp_text:
        try:
            timestamp = int(timestamp_text)
        except ValueError as exc:
            raise WebhookVerificationError("webhook_timestamp_invalid") from exc
    if replay_guard is not None:
        replay_guard.verify(event_id=event_id, timestamp=timestamp, now=now)

    return {
        "provider": kind.value,
        "verified": True,
        "event_id": event_id,
        "timestamp": timestamp,
        "body_sha256": hashlib.sha256(body).hexdigest(),
    }


__all__ = [
    "ReplayGuard",
    "WebhookVerificationError",
    "verify_hmac_sha256",
    "verify_provider_webhook",
]
