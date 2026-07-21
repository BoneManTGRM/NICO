from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping, Protocol


class NotificationDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class NotificationMessage:
    notification_id: str
    dedup_key: str
    destination: str
    severity: str
    subject: str
    body: str
    exact_sha: str
    evidence_fingerprint: str
    created_at: str
    status: str = "pending"
    attempts: int = 0
    next_attempt_at: str = ""
    delivered_at: str = ""
    last_error: str = ""
    provider_message_id: str = ""


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    provider_message_id: str = ""
    retryable: bool = False
    error_code: str = ""


class NotificationAdapter(Protocol):
    destination: str

    def send(self, message: NotificationMessage) -> DeliveryResult:
        ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required(value: Any, code: str) -> str:
    token = " ".join(str(value or "").split())
    if not token:
        raise NotificationDeliveryError(code)
    return token


def build_notification(
    *,
    dedup_key: str,
    destination: str,
    severity: str,
    subject: str,
    body: str,
    exact_sha: str,
    evidence_fingerprint: str,
    created_at: str = "",
) -> NotificationMessage:
    dedup = _required(dedup_key, "notification_dedup_key_required")
    target = _required(destination, "notification_destination_required")
    timestamp = created_at or _iso(_utc_now())
    identity = f"sha256:{sha256(f'{dedup}|{target}'.encode('utf-8')).hexdigest()}"
    return NotificationMessage(
        notification_id=identity,
        dedup_key=dedup,
        destination=target,
        severity=_required(severity, "notification_severity_required"),
        subject=_required(subject, "notification_subject_required"),
        body=_required(body, "notification_body_required"),
        exact_sha=_required(exact_sha, "notification_exact_sha_required"),
        evidence_fingerprint=_required(evidence_fingerprint, "notification_evidence_required"),
        created_at=timestamp,
        next_attempt_at=timestamp,
    )


class NotificationStore:
    def __init__(self, connection_factory: Callable[[], Any], *, dialect: str = "sqlite") -> None:
        if dialect not in {"sqlite", "postgres"}:
            raise ValueError("notification_store_dialect_unsupported")
        self._connection_factory = connection_factory
        self.dialect = dialect

    @property
    def _placeholder(self) -> str:
        return "?" if self.dialect == "sqlite" else "%s"

    def ensure_schema(self) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_notification_delivery (
                    notification_id TEXT PRIMARY KEY,
                    dedup_key TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    status TEXT NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (dedup_key, destination)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nico_notification_due
                ON nico_notification_delivery (status, next_attempt_at)
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _serialize(message: NotificationMessage) -> str:
        return json.dumps(message.__dict__, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _deserialize(payload: str) -> NotificationMessage:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise NotificationDeliveryError("notification_payload_invalid") from exc
        return NotificationMessage(**data)

    def enqueue(self, message: NotificationMessage) -> NotificationMessage:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            values = (
                message.notification_id,
                message.dedup_key,
                message.destination,
                message.status,
                message.next_attempt_at,
                self._serialize(message),
                _iso(_utc_now()),
            )
            placeholders = ",".join([self._placeholder] * len(values))
            try:
                cursor.execute(
                    f"""
                    INSERT INTO nico_notification_delivery (
                        notification_id, dedup_key, destination, status,
                        next_attempt_at, payload_json, updated_at
                    ) VALUES ({placeholders})
                    """,
                    values,
                )
            except Exception:
                connection.rollback()
                cursor.execute(
                    f"""
                    SELECT payload_json FROM nico_notification_delivery
                    WHERE dedup_key = {self._placeholder} AND destination = {self._placeholder}
                    """,
                    (message.dedup_key, message.destination),
                )
                row = cursor.fetchone()
                if row is None:
                    raise NotificationDeliveryError("notification_enqueue_conflict")
                return self._deserialize(str(row[0]))
            connection.commit()
        finally:
            connection.close()
        return message

    def save(self, message: NotificationMessage) -> NotificationMessage:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                UPDATE nico_notification_delivery
                SET status = {self._placeholder}, next_attempt_at = {self._placeholder},
                    payload_json = {self._placeholder}, updated_at = {self._placeholder}
                WHERE notification_id = {self._placeholder}
                """,
                (
                    message.status,
                    message.next_attempt_at,
                    self._serialize(message),
                    _iso(_utc_now()),
                    message.notification_id,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise NotificationDeliveryError("notification_not_found")
            connection.commit()
        finally:
            connection.close()
        return message

    def due(self, *, now: datetime | None = None, limit: int = 100) -> tuple[NotificationMessage, ...]:
        current = _iso(now or _utc_now())
        bounded = max(1, min(500, int(limit)))
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT payload_json FROM nico_notification_delivery
                WHERE status IN ({self._placeholder}, {self._placeholder})
                  AND next_attempt_at <= {self._placeholder}
                ORDER BY next_attempt_at ASC
                LIMIT {self._placeholder}
                """,
                ("pending", "retry", current, bounded),
            )
            rows = cursor.fetchall()
        finally:
            connection.close()
        return tuple(self._deserialize(str(row[0])) for row in rows)


class NotificationDispatcher:
    def __init__(
        self,
        store: NotificationStore,
        adapters: Mapping[str, NotificationAdapter],
        *,
        max_attempts: int = 5,
        base_retry_seconds: int = 60,
        max_retry_seconds: int = 3600,
    ) -> None:
        self.store = store
        self.adapters = dict(adapters)
        self.max_attempts = max(1, int(max_attempts))
        self.base_retry_seconds = max(1, int(base_retry_seconds))
        self.max_retry_seconds = max(self.base_retry_seconds, int(max_retry_seconds))

    def dispatch(self, message: NotificationMessage, *, now: datetime | None = None) -> NotificationMessage:
        current = now or _utc_now()
        if message.status == "delivered":
            return message
        adapter = self.adapters.get(message.destination)
        if adapter is None:
            failed = replace(
                message,
                status="failed",
                attempts=message.attempts + 1,
                next_attempt_at="",
                last_error="notification_adapter_not_configured",
            )
            return self.store.save(failed)
        result = adapter.send(message)
        attempts = message.attempts + 1
        if result.delivered:
            delivered = replace(
                message,
                status="delivered",
                attempts=attempts,
                delivered_at=_iso(current),
                next_attempt_at="",
                last_error="",
                provider_message_id=result.provider_message_id,
            )
            return self.store.save(delivered)
        if result.retryable and attempts < self.max_attempts:
            delay = min(self.max_retry_seconds, self.base_retry_seconds * (2 ** (attempts - 1)))
            retry = replace(
                message,
                status="retry",
                attempts=attempts,
                next_attempt_at=_iso(current + timedelta(seconds=delay)),
                last_error=result.error_code or "notification_delivery_retryable",
            )
            return self.store.save(retry)
        failed = replace(
            message,
            status="failed",
            attempts=attempts,
            next_attempt_at="",
            last_error=result.error_code or "notification_delivery_failed",
        )
        return self.store.save(failed)

    def run_due(self, *, now: datetime | None = None, limit: int = 100) -> tuple[NotificationMessage, ...]:
        current = now or _utc_now()
        return tuple(self.dispatch(message, now=current) for message in self.store.due(now=current, limit=limit))


__all__ = [
    "DeliveryResult",
    "NotificationAdapter",
    "NotificationDeliveryError",
    "NotificationDispatcher",
    "NotificationMessage",
    "NotificationStore",
    "build_notification",
]
