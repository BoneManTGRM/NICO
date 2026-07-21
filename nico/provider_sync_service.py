from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Callable, Mapping, Protocol

from nico.provider_credentials import SecretValue
from nico.provider_live_clients import ProviderClientError, ProviderCollection
from nico.provider_neutral_contract import ProviderKind, normalize_provider
from nico.provider_webhook_verification import ReplayGuard, verify_provider_webhook


class ProviderSyncError(RuntimeError):
    pass


class ProviderSyncMissing(ProviderSyncError):
    pass


class ProviderSyncConflict(ProviderSyncError):
    pass


class SyncState(str, Enum):
    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    PARTIAL = "partial"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


@dataclass(frozen=True)
class ProviderSyncRecord:
    provider: ProviderKind
    repository_id: str
    state: SyncState
    requested_revision: str = ""
    collected_revision: str = ""
    last_event_id: str = ""
    last_event_sha256: str = ""
    last_success_at: str = ""
    last_attempt_at: str = ""
    next_poll_at: str = ""
    failure_count: int = 0
    requests_made: int = 0
    pages_fetched: int = 0
    evidence_digest: str = ""
    warnings: tuple[str, ...] = ()
    limitation_reason: str = ""
    revision: int = 1
    read_only: bool = True


@dataclass(frozen=True)
class StoredProviderSync:
    record: ProviderSyncRecord
    integrity_sha256: str
    updated_at: str


class ProviderCollector(Protocol):
    provider: ProviderKind

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_mapping(record: ProviderSyncRecord) -> dict[str, Any]:
    return {
        "provider": record.provider.value,
        "repository_id": record.repository_id,
        "state": record.state.value,
        "requested_revision": record.requested_revision,
        "collected_revision": record.collected_revision,
        "last_event_id": record.last_event_id,
        "last_event_sha256": record.last_event_sha256,
        "last_success_at": record.last_success_at,
        "last_attempt_at": record.last_attempt_at,
        "next_poll_at": record.next_poll_at,
        "failure_count": record.failure_count,
        "requests_made": record.requests_made,
        "pages_fetched": record.pages_fetched,
        "evidence_digest": record.evidence_digest,
        "warnings": list(record.warnings),
        "limitation_reason": record.limitation_reason,
        "revision": record.revision,
        "read_only": True,
    }


def _serialize(record: ProviderSyncRecord) -> str:
    return json.dumps(_record_mapping(record), sort_keys=True, separators=(",", ":"))


def _integrity(payload: str) -> str:
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


def _deserialize(payload: str) -> ProviderSyncRecord:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProviderSyncError("provider_sync_payload_invalid") from exc
    return ProviderSyncRecord(
        provider=normalize_provider(data.get("provider")),
        repository_id=str(data.get("repository_id") or ""),
        state=SyncState(str(data.get("state") or "invalid")),
        requested_revision=str(data.get("requested_revision") or ""),
        collected_revision=str(data.get("collected_revision") or ""),
        last_event_id=str(data.get("last_event_id") or ""),
        last_event_sha256=str(data.get("last_event_sha256") or ""),
        last_success_at=str(data.get("last_success_at") or ""),
        last_attempt_at=str(data.get("last_attempt_at") or ""),
        next_poll_at=str(data.get("next_poll_at") or ""),
        failure_count=int(data.get("failure_count") or 0),
        requests_made=int(data.get("requests_made") or 0),
        pages_fetched=int(data.get("pages_fetched") or 0),
        evidence_digest=str(data.get("evidence_digest") or ""),
        warnings=tuple(str(item) for item in data.get("warnings") or ()),
        limitation_reason=str(data.get("limitation_reason") or ""),
        revision=int(data.get("revision") or 1),
        read_only=True,
    )


class ProviderSyncStore:
    def __init__(self, connection_factory: Callable[[], Any], *, dialect: str = "sqlite") -> None:
        if dialect not in {"sqlite", "postgres"}:
            raise ValueError("provider_sync_dialect_unsupported")
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
                CREATE TABLE IF NOT EXISTS nico_provider_sync (
                    provider TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, repository_id)
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def load(self, provider: ProviderKind | str, repository_id: str) -> StoredProviderSync:
        kind = provider if isinstance(provider, ProviderKind) else normalize_provider(provider)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT payload_json, integrity_sha256, updated_at
                FROM nico_provider_sync
                WHERE provider = {self._placeholder} AND repository_id = {self._placeholder}
                """,
                (kind.value, repository_id),
            )
            row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            raise ProviderSyncMissing("provider_sync_not_found")
        payload, integrity, updated_at = str(row[0]), str(row[1]), str(row[2])
        if integrity != _integrity(payload):
            raise ProviderSyncError("provider_sync_integrity_mismatch")
        return StoredProviderSync(_deserialize(payload), integrity, updated_at)

    def upsert(self, record: ProviderSyncRecord, *, expected_revision: int | None = None) -> StoredProviderSync:
        payload = _serialize(record)
        integrity = _integrity(payload)
        updated_at = _iso(_utc_now())
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            if expected_revision is None:
                values = (
                    record.provider.value,
                    record.repository_id,
                    record.revision,
                    record.state.value,
                    payload,
                    integrity,
                    updated_at,
                )
                placeholders = ",".join([self._placeholder] * len(values))
                try:
                    cursor.execute(
                        f"""
                        INSERT INTO nico_provider_sync (
                            provider, repository_id, revision, state,
                            payload_json, integrity_sha256, updated_at
                        ) VALUES ({placeholders})
                        """,
                        values,
                    )
                except Exception as exc:
                    connection.rollback()
                    raise ProviderSyncConflict("provider_sync_already_exists") from exc
            else:
                if record.revision != expected_revision + 1:
                    raise ProviderSyncConflict("provider_sync_revision_increment_invalid")
                cursor.execute(
                    f"""
                    UPDATE nico_provider_sync
                    SET revision = {self._placeholder}, state = {self._placeholder},
                        payload_json = {self._placeholder}, integrity_sha256 = {self._placeholder},
                        updated_at = {self._placeholder}
                    WHERE provider = {self._placeholder} AND repository_id = {self._placeholder}
                      AND revision = {self._placeholder}
                    """,
                    (
                        record.revision,
                        record.state.value,
                        payload,
                        integrity,
                        updated_at,
                        record.provider.value,
                        record.repository_id,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise ProviderSyncConflict("provider_sync_revision_conflict")
            connection.commit()
        finally:
            connection.close()
        return StoredProviderSync(record, integrity, updated_at)


class ProviderSyncService:
    def __init__(
        self,
        store: ProviderSyncStore,
        *,
        poll_interval_seconds: int = 900,
        max_failure_backoff_seconds: int = 3600,
    ) -> None:
        self.store = store
        self.poll_interval_seconds = max(60, int(poll_interval_seconds))
        self.max_failure_backoff_seconds = max(self.poll_interval_seconds, int(max_failure_backoff_seconds))

    def _next_poll(self, failure_count: int = 0) -> str:
        seconds = self.poll_interval_seconds
        if failure_count:
            seconds = min(self.max_failure_backoff_seconds, seconds * (2 ** min(failure_count, 8)))
        return _iso(_utc_now() + timedelta(seconds=seconds))

    def ensure(self, *, provider: ProviderKind | str, repository_id: str, requested_revision: str = "") -> dict[str, Any]:
        kind = provider if isinstance(provider, ProviderKind) else normalize_provider(provider)
        try:
            return self.safe(self.store.load(kind, repository_id))
        except ProviderSyncMissing:
            record = ProviderSyncRecord(
                provider=kind,
                repository_id=repository_id,
                state=SyncState.IDLE,
                requested_revision=requested_revision,
                next_poll_at=self._next_poll(),
            )
            return self.safe(self.store.upsert(record))

    @staticmethod
    def safe(stored: StoredProviderSync) -> dict[str, Any]:
        return {
            **_record_mapping(stored.record),
            "integrity_sha256": stored.integrity_sha256,
            "updated_at": stored.updated_at,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def collect(
        self,
        collector: ProviderCollector,
        *,
        repository_id: str,
        requested_revision: str = "",
    ) -> dict[str, Any]:
        if not repository_id:
            raise ProviderSyncError("provider_sync_repository_required")
        kind = collector.provider
        try:
            stored = self.store.load(kind, repository_id)
        except ProviderSyncMissing:
            stored = self.store.upsert(
                ProviderSyncRecord(
                    provider=kind,
                    repository_id=repository_id,
                    state=SyncState.IDLE,
                    requested_revision=requested_revision,
                    next_poll_at=self._next_poll(),
                )
            )
        running = replace(
            stored.record,
            state=SyncState.RUNNING,
            requested_revision=requested_revision or stored.record.requested_revision,
            last_attempt_at=_iso(_utc_now()),
            limitation_reason="",
            revision=stored.record.revision + 1,
        )
        stored = self.store.upsert(running, expected_revision=stored.record.revision)
        try:
            collection = collector.collect(repository_id, revision=requested_revision)
            adapted = collection.adapt()
            envelope_json = json.dumps(
                {
                    "provider": adapted.envelope.identity.provider.value,
                    "repository_id": adapted.envelope.identity.repository_id,
                    "revision": adapted.envelope.snapshot.revision,
                    "source_fingerprint": adapted.envelope.snapshot.source_fingerprint,
                    "change_request_ids": [item.native_id for item in adapted.envelope.change_requests],
                    "ci_run_ids": [item.native_id for item in adapted.envelope.ci_runs],
                    "warnings": list(adapted.warnings),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            warnings = tuple(adapted.warnings)
            state = SyncState.PARTIAL if warnings else SyncState.READY
            success = replace(
                stored.record,
                state=state,
                collected_revision=collection.revision,
                last_success_at=_iso(_utc_now()) if state is SyncState.READY else stored.record.last_success_at,
                next_poll_at=self._next_poll(),
                failure_count=0,
                requests_made=collection.requests_made,
                pages_fetched=collection.pages_fetched,
                evidence_digest=f"sha256:{sha256(envelope_json.encode('utf-8')).hexdigest()}",
                warnings=warnings,
                limitation_reason="; ".join(warnings),
                revision=stored.record.revision + 1,
            )
            return self.safe(self.store.upsert(success, expected_revision=stored.record.revision))
        except ProviderClientError as exc:
            state = {
                "provider_auth_failed": SyncState.AUTH_FAILED,
                "provider_rate_limited": SyncState.RATE_LIMITED,
                "provider_service_unavailable": SyncState.UNAVAILABLE,
                "provider_network_unavailable": SyncState.UNAVAILABLE,
            }.get(exc.code, SyncState.INVALID)
            failures = stored.record.failure_count + 1
            failed = replace(
                stored.record,
                state=state,
                failure_count=failures,
                next_poll_at=self._next_poll(failures),
                limitation_reason=exc.code,
                revision=stored.record.revision + 1,
            )
            return self.safe(self.store.upsert(failed, expected_revision=stored.record.revision))

    def accept_webhook(
        self,
        *,
        provider: ProviderKind | str,
        repository_id: str,
        secret: SecretValue,
        headers: Mapping[str, str],
        body: bytes,
        replay_guard: ReplayGuard,
        now: int | None = None,
    ) -> dict[str, Any]:
        verified = verify_provider_webhook(
            provider=provider,
            secret=secret,
            headers=headers,
            body=body,
            replay_guard=replay_guard,
            now=now,
        )
        kind = normalize_provider(verified["provider"])
        try:
            stored = self.store.load(kind, repository_id)
        except ProviderSyncMissing:
            stored = self.store.upsert(
                ProviderSyncRecord(
                    provider=kind,
                    repository_id=repository_id,
                    state=SyncState.IDLE,
                    next_poll_at=self._next_poll(),
                )
            )
        pending = replace(
            stored.record,
            state=SyncState.PENDING,
            last_event_id=str(verified.get("event_id") or ""),
            last_event_sha256=str(verified.get("body_sha256") or ""),
            next_poll_at=_iso(_utc_now()),
            revision=stored.record.revision + 1,
        )
        return self.safe(self.store.upsert(pending, expected_revision=stored.record.revision))


__all__ = [
    "ProviderCollector",
    "ProviderSyncConflict",
    "ProviderSyncError",
    "ProviderSyncMissing",
    "ProviderSyncRecord",
    "ProviderSyncService",
    "ProviderSyncStore",
    "StoredProviderSync",
    "SyncState",
]
