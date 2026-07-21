from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping

from nico.monitor_scheduler import MonitorCadence, MonitorRunState, RepositoryObservation, next_run_state


class MonitorRuntimeError(RuntimeError):
    pass


class MonitorLeaseConflict(MonitorRuntimeError):
    pass


class MonitorDefinitionMissing(MonitorRuntimeError):
    pass


@dataclass(frozen=True)
class MonitorDefinition:
    monitor_id: str
    repository: str
    customer_id: str
    project_id: str
    cadence: MonitorCadence
    enabled: bool = True
    revision: int = 1


@dataclass(frozen=True)
class MonitorLease:
    monitor_id: str
    lease_id: str
    owner_id: str
    acquired_at: str
    expires_at: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    token = str(value or "").strip()
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    parsed = datetime.fromisoformat(token)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required(value: Any, code: str) -> str:
    token = " ".join(str(value or "").split())
    if not token:
        raise MonitorRuntimeError(code)
    return token


def _digest(parts: tuple[str, ...]) -> str:
    return f"sha256:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


def _definition_payload(definition: MonitorDefinition) -> str:
    return json.dumps(
        {
            "monitor_id": definition.monitor_id,
            "repository": definition.repository,
            "customer_id": definition.customer_id,
            "project_id": definition.project_id,
            "cadence": definition.cadence.__dict__,
            "enabled": definition.enabled,
            "revision": definition.revision,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _state_payload(state: MonitorRunState) -> str:
    return json.dumps(state.__dict__, sort_keys=True, separators=(",", ":"))


class MonitorRuntimeStore:
    def __init__(self, connection_factory: Callable[[], Any], *, dialect: str = "sqlite") -> None:
        if dialect not in {"sqlite", "postgres"}:
            raise ValueError("monitor_runtime_dialect_unsupported")
        self._connection_factory = connection_factory
        self.dialect = dialect

    @property
    def _p(self) -> str:
        return "?" if self.dialect == "sqlite" else "%s"

    def ensure_schema(self) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_monitor_definitions (
                    monitor_id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_monitor_runtime_state (
                    monitor_id TEXT PRIMARY KEY,
                    next_run_at TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_monitor_leases (
                    monitor_id TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_monitor_observations (
                    observation_id TEXT PRIMARY KEY,
                    monitor_id TEXT NOT NULL,
                    immutable_sha TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_sha256 TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nico_monitor_due
                ON nico_monitor_runtime_state (next_run_at)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def create_definition(self, definition: MonitorDefinition, *, now: datetime | None = None) -> MonitorDefinition:
        definition.cadence.validate()
        if not definition.monitor_id or not definition.repository or not definition.customer_id or not definition.project_id:
            raise MonitorRuntimeError("monitor_definition_identity_required")
        timestamp = _iso(now or _utc_now())
        payload = _definition_payload(definition)
        integrity = _digest((payload,))
        state = MonitorRunState(
            monitor_id=definition.monitor_id,
            repository=definition.repository,
            customer_id=definition.customer_id,
            project_id=definition.project_id,
            next_run_at=timestamp,
        )
        state_payload = _state_payload(state)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute("BEGIN")
            try:
                cursor.execute(
                    f"INSERT INTO nico_monitor_definitions VALUES ({','.join([self._p] * 9)})",
                    (
                        definition.monitor_id,
                        definition.repository,
                        definition.customer_id,
                        definition.project_id,
                        int(definition.enabled),
                        definition.revision,
                        payload,
                        integrity,
                        timestamp,
                    ),
                )
                cursor.execute(
                    f"INSERT INTO nico_monitor_runtime_state VALUES ({','.join([self._p] * 6)})",
                    (
                        definition.monitor_id,
                        state.next_run_at,
                        state.revision,
                        state_payload,
                        _digest((state_payload,)),
                        timestamp,
                    ),
                )
            except Exception as exc:
                connection.rollback()
                raise MonitorRuntimeError("monitor_definition_already_exists") from exc
            connection.commit()
        finally:
            connection.close()
        return definition

    def load_definition(self, monitor_id: str) -> MonitorDefinition:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT payload_json, integrity_sha256 FROM nico_monitor_definitions WHERE monitor_id = {self._p}",
                (monitor_id,),
            )
            row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            raise MonitorDefinitionMissing("monitor_definition_not_found")
        payload, integrity = str(row[0]), str(row[1])
        if integrity != _digest((payload,)):
            raise MonitorRuntimeError("monitor_definition_integrity_mismatch")
        data = json.loads(payload)
        return MonitorDefinition(
            monitor_id=data["monitor_id"],
            repository=data["repository"],
            customer_id=data["customer_id"],
            project_id=data["project_id"],
            cadence=MonitorCadence(**data["cadence"]),
            enabled=bool(data["enabled"]),
            revision=int(data["revision"]),
        )

    def load_state(self, monitor_id: str) -> MonitorRunState:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT payload_json, integrity_sha256 FROM nico_monitor_runtime_state WHERE monitor_id = {self._p}",
                (monitor_id,),
            )
            row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            raise MonitorDefinitionMissing("monitor_runtime_state_not_found")
        payload, integrity = str(row[0]), str(row[1])
        if integrity != _digest((payload,)):
            raise MonitorRuntimeError("monitor_runtime_state_integrity_mismatch")
        return MonitorRunState(**json.loads(payload))

    def due(self, *, now: datetime | None = None, limit: int = 100) -> tuple[str, ...]:
        timestamp = _iso(now or _utc_now())
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT s.monitor_id
                FROM nico_monitor_runtime_state s
                JOIN nico_monitor_definitions d ON d.monitor_id = s.monitor_id
                WHERE s.next_run_at <= {self._p} AND d.enabled = {self._p}
                ORDER BY s.next_run_at ASC
                LIMIT {self._p}
                """,
                (timestamp, 1, max(1, min(500, int(limit)))),
            )
            rows = cursor.fetchall()
        finally:
            connection.close()
        return tuple(str(row[0]) for row in rows)

    def acquire_lease(
        self,
        monitor_id: str,
        *,
        owner_id: str,
        lease_seconds: int = 900,
        now: datetime | None = None,
    ) -> MonitorLease:
        current = now or _utc_now()
        owner = _required(owner_id, "monitor_lease_owner_required")
        if lease_seconds < 30 or lease_seconds > 3600:
            raise MonitorRuntimeError("monitor_lease_duration_invalid")
        lease_id = _digest((monitor_id, owner, _iso(current)))
        expires = current + timedelta(seconds=lease_seconds)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute("BEGIN")
            cursor.execute(
                f"SELECT lease_id, owner_id, acquired_at, expires_at FROM nico_monitor_leases WHERE monitor_id = {self._p}",
                (monitor_id,),
            )
            row = cursor.fetchone()
            if row is not None and _parse(str(row[3])) > current:
                connection.rollback()
                raise MonitorLeaseConflict("monitor_lease_active")
            if row is None:
                cursor.execute(
                    f"INSERT INTO nico_monitor_leases VALUES ({','.join([self._p] * 5)})",
                    (monitor_id, lease_id, owner, _iso(current), _iso(expires)),
                )
            else:
                cursor.execute(
                    f"""
                    UPDATE nico_monitor_leases
                    SET lease_id = {self._p}, owner_id = {self._p}, acquired_at = {self._p}, expires_at = {self._p}
                    WHERE monitor_id = {self._p}
                    """,
                    (lease_id, owner, _iso(current), _iso(expires), monitor_id),
                )
            connection.commit()
        finally:
            connection.close()
        return MonitorLease(monitor_id, lease_id, owner, _iso(current), _iso(expires))

    def release_lease(self, lease: MonitorLease) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"DELETE FROM nico_monitor_leases WHERE monitor_id = {self._p} AND lease_id = {self._p}",
                (lease.monitor_id, lease.lease_id),
            )
            connection.commit()
        finally:
            connection.close()

    def complete_run(
        self,
        lease: MonitorLease,
        *,
        success: bool,
        observation: RepositoryObservation | None = None,
        error: str = "",
        now: datetime | None = None,
    ) -> MonitorRunState:
        definition = self.load_definition(lease.monitor_id)
        state = self.load_state(lease.monitor_id)
        current = now or _utc_now()
        if success and observation is None:
            raise MonitorRuntimeError("monitor_success_observation_required")
        next_state = next_run_state(
            state,
            cadence=definition.cadence,
            success=success,
            observed_sha="" if observation is None else observation.immutable_sha,
            error=error,
            now=current,
        )
        payload = _state_payload(next_state)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute("BEGIN")
            cursor.execute(
                f"SELECT lease_id, expires_at FROM nico_monitor_leases WHERE monitor_id = {self._p}",
                (lease.monitor_id,),
            )
            row = cursor.fetchone()
            if row is None or str(row[0]) != lease.lease_id or _parse(str(row[1])) <= current:
                connection.rollback()
                raise MonitorLeaseConflict("monitor_lease_missing_or_expired")
            cursor.execute(
                f"""
                UPDATE nico_monitor_runtime_state
                SET next_run_at = {self._p}, revision = {self._p}, payload_json = {self._p},
                    integrity_sha256 = {self._p}, updated_at = {self._p}
                WHERE monitor_id = {self._p} AND revision = {self._p}
                """,
                (
                    next_state.next_run_at,
                    next_state.revision,
                    payload,
                    _digest((payload,)),
                    _iso(current),
                    lease.monitor_id,
                    state.revision,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise MonitorRuntimeError("monitor_state_revision_conflict")
            if observation is not None:
                observation_payload = json.dumps(
                    {
                        **observation.__dict__,
                        "findings": [dict(item) for item in observation.findings],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                observation_id = _digest((lease.monitor_id, observation.immutable_sha, observation.observed_at))
                cursor.execute(
                    f"INSERT INTO nico_monitor_observations VALUES ({','.join([self._p] * 6)})",
                    (
                        observation_id,
                        lease.monitor_id,
                        observation.immutable_sha,
                        observation.observed_at,
                        observation_payload,
                        _digest((observation_payload,)),
                    ),
                )
            cursor.execute(
                f"DELETE FROM nico_monitor_leases WHERE monitor_id = {self._p} AND lease_id = {self._p}",
                (lease.monitor_id, lease.lease_id),
            )
            connection.commit()
        finally:
            connection.close()
        return next_state


__all__ = [
    "MonitorDefinition",
    "MonitorDefinitionMissing",
    "MonitorLease",
    "MonitorLeaseConflict",
    "MonitorRuntimeError",
    "MonitorRuntimeStore",
]
