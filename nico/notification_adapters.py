from __future__ import annotations

import hmac
import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from hashlib import sha256
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import httpx

from nico.notification_delivery import DeliveryResult, NotificationMessage
from nico.provider_credentials import SecretValue


class NotificationAdapterError(RuntimeError):
    pass


def _https_url(value: str, *, allowed_hosts: tuple[str, ...]) -> str:
    token = str(value or "").strip()
    parsed = urlparse(token)
    if parsed.scheme != "https" or not parsed.hostname:
        raise NotificationAdapterError("notification_https_url_required")
    normalized = parsed.hostname.lower()
    allowed = {str(host).lower() for host in allowed_hosts}
    if not allowed or normalized not in allowed:
        raise NotificationAdapterError("notification_host_not_allowed")
    return token


def _safe_payload(message: NotificationMessage) -> dict[str, Any]:
    return {
        "notification_id": message.notification_id,
        "dedup_key": message.dedup_key,
        "severity": message.severity,
        "subject": message.subject,
        "body": message.body,
        "exact_sha": message.exact_sha,
        "evidence_fingerprint": message.evidence_fingerprint,
        "created_at": message.created_at,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


@dataclass
class SignedWebhookNotificationAdapter:
    destination: str
    url: str
    signing_secret: SecretValue
    allowed_hosts: tuple[str, ...]
    client: httpx.Client | None = None
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        self.url = _https_url(self.url, allowed_hosts=self.allowed_hosts)
        self._client = self.client or httpx.Client(timeout=self.timeout_seconds)
        self._owns_client = self.client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def send(self, message: NotificationMessage) -> DeliveryResult:
        payload = _safe_payload(message)
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            self.signing_secret.reveal().encode("utf-8"),
            body,
            sha256,
        ).hexdigest()
        try:
            response = self._client.post(
                self.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-NICO-Notification-ID": message.notification_id,
                    "X-NICO-Signature": f"sha256={signature}",
                    "Idempotency-Key": message.notification_id,
                    "User-Agent": "nico-notification-delivery/1",
                },
                timeout=self.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return DeliveryResult(False, retryable=True, error_code="notification_webhook_network_failure")
        provider_message_id = str(
            response.headers.get("X-Message-ID")
            or response.headers.get("X-Request-ID")
            or ""
        )
        if 200 <= response.status_code < 300:
            return DeliveryResult(True, provider_message_id=provider_message_id)
        if response.status_code == 429 or 500 <= response.status_code <= 599:
            return DeliveryResult(
                False,
                retryable=True,
                error_code=f"notification_webhook_retryable_{response.status_code}",
            )
        return DeliveryResult(
            False,
            retryable=False,
            error_code=f"notification_webhook_rejected_{response.status_code}",
        )


class SmtpSender:
    def __init__(
        self,
        *,
        host: str,
        port: int = 465,
        username: str = "",
        password: SecretValue | None = None,
        timeout_seconds: float = 20.0,
        use_ssl: bool = True,
    ) -> None:
        self.host = str(host or "").strip()
        self.port = int(port)
        self.username = str(username or "").strip()
        self.password = password
        self.timeout_seconds = float(timeout_seconds)
        self.use_ssl = bool(use_ssl)
        if not self.host or self.port < 1 or self.port > 65535:
            raise NotificationAdapterError("notification_smtp_configuration_invalid")
        if self.username and self.password is None:
            raise NotificationAdapterError("notification_smtp_password_required")

    def __call__(self, message: EmailMessage) -> str:
        if self.use_ssl:
            client = smtplib.SMTP_SSL(
                self.host,
                self.port,
                timeout=self.timeout_seconds,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds)
            client.starttls(context=ssl.create_default_context())
        try:
            if self.username and self.password is not None:
                client.login(self.username, self.password.reveal())
            result = client.send_message(message)
            if result:
                raise NotificationAdapterError("notification_smtp_recipient_rejected")
            return str(message.get("Message-ID") or "")
        finally:
            client.quit()


@dataclass
class EmailNotificationAdapter:
    destination: str
    from_address: str
    to_addresses: tuple[str, ...]
    sender: Callable[[EmailMessage], str]

    def __post_init__(self) -> None:
        if "@" not in self.from_address:
            raise NotificationAdapterError("notification_email_sender_invalid")
        if not self.to_addresses or any("@" not in item for item in self.to_addresses):
            raise NotificationAdapterError("notification_email_recipient_invalid")

    def send(self, message: NotificationMessage) -> DeliveryResult:
        email = EmailMessage()
        email["From"] = self.from_address
        email["To"] = ", ".join(self.to_addresses)
        email["Subject"] = f"[{message.severity.upper()}] {message.subject}"
        email["Message-ID"] = f"<{message.notification_id.removeprefix('sha256:')}@nicoaudit.local>"
        email["X-NICO-Notification-ID"] = message.notification_id
        email["X-NICO-Exact-SHA"] = message.exact_sha
        email.set_content(
            "\n".join(
                (
                    message.body,
                    "",
                    f"Exact SHA: {message.exact_sha}",
                    f"Evidence: {message.evidence_fingerprint}",
                    "Human review required: yes",
                    "Client delivery allowed: no",
                )
            )
        )
        try:
            provider_message_id = self.sender(email)
        except (TimeoutError, OSError, smtplib.SMTPException):
            return DeliveryResult(False, retryable=True, error_code="notification_smtp_transport_failure")
        except NotificationAdapterError as exc:
            return DeliveryResult(False, retryable=False, error_code=str(exc))
        return DeliveryResult(True, provider_message_id=provider_message_id)


__all__ = [
    "EmailNotificationAdapter",
    "NotificationAdapterError",
    "SignedWebhookNotificationAdapter",
    "SmtpSender",
]
