from __future__ import annotations

import json
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, Protocol

from nico.comprehensive_run_record import (
    restore_comprehensive_run_record,
    validate_comprehensive_run_record,
)

VERSION = "nico.comprehensive_run_store.v1"


class ConnectionLike(Protocol):
    def cursor(self) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[], ConnectionLike]


class ComprehensiveRunConflict(RuntimeError):
    pass


class ComprehensiveRunNotFound(KeyError):
    pass


class ComprehensiveRunStore:
    """Transactional persistence for canonical Comprehensive run records.

    The store uses optimistic revision checks so two workers cannot silently
    overwrite the same run. Payload integrity is revalidated on every write
    and read. The SQL is intentionally limited to portable DB-API operations;
    production can use a psycopg connection factory with ``dialect='postgres'``.

    The final-report lease store intentionally uses the same adapter. Read-only
    properties expose that adapter without requiring worker code to depend on private
    attributes or duplicate environment parsing.
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        dialect: str = "sqlite",
    ) -> None:
        normalized = dialect.strip().lower()
        if normalized not in {"sqlite", "postgres"}:
            raise ValueError("unsupported_dialect")
        self._connection_factory = connection_factory
        self._dialect = normalized

    @property
    def placeholder(self) -> str:
        return "%s" if self._dialect == "postgres" else "?"

    @property
    def connection_factory(self) -> ConnectionFactory:
        return self._connection_factory

    @property
    def dialect(self) -> str:
        return self._dialect

    @contextmanager
    def _connection(self) -> Iterator[ConnectionLike]:
        connection = self._connection_factory()
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        payload_type = "JSONB" if self._dialect == "postgres" else "TEXT"
        boolean_type = "BOOLEAN" if self._dialect == "postgres" else "INTEGER"
        statement = f"""
        CREATE TABLE IF NOT EXISTS nico_comprehensive_runs (
            run_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            repository TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            evidence_ledger_id TEXT NOT NULL,
            status TEXT NOT NULL,
            revision INTEGER NOT NULL,
            terminal {boolean_type} NOT NULL,
            integrity_sha256 TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload {payload_type} NOT NULL
        )
        """
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement)
            connection.commit()

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        canonical = self._validated_copy(record)
        identity = canonical["identity"]
        p = self.placeholder
        statement = f"""
        INSERT INTO nico_comprehensive_runs (
            run_id, customer_id, project_id, repository, commit_sha,
            evidence_ledger_id, status, revision, terminal,
            integrity_sha256, updated_at, payload
        ) VALUES ({','.join([p] * 12)})
        """
        values = self._row_values(canonical)
        with self._connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, values)
            except Exception as exc:
                connection.rollback()
                raise ComprehensiveRunConflict(
                    f"run_already_exists:{identity['run_id']}"
                ) from exc
            connection.commit()
        return deepcopy(canonical)

    def load(self, run_id: str) -> dict[str, Any]:
        normalized = str(run_id or "").strip()
        if not normalized:
            raise ValueError("run_id_required")
        p = self.placeholder
        statement = f"""
        SELECT payload FROM nico_comprehensive_runs WHERE run_id = {p}
        """
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, (normalized,))
            row = cursor.fetchone()
        if row is None:
            raise ComprehensiveRunNotFound(normalized)
        payload = self._decode_payload(row[0])
        restored = restore_comprehensive_run_record(payload)
        return self._validated_copy(restored)

    def save(
        self,
        record: dict[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        canonical = self._validated_copy(record)
        identity = canonical["identity"]
        p = self.placeholder
        statement = f"""
        UPDATE nico_comprehensive_runs
        SET customer_id = {p}, project_id = {p}, repository = {p},
            commit_sha = {p}, evidence_ledger_id = {p}, status = {p},
            revision = {p}, terminal = {p}, integrity_sha256 = {p},
            updated_at = {p}, payload = {p}
        WHERE run_id = {p} AND revision = {p}
        """
        values = (
            identity["customer_id"],
            identity["project_id"],
            identity["repository"],
            identity["commit_sha"],
            identity["evidence_ledger_id"],
            canonical["status"],
            int(canonical["revision"]),
            bool(canonical["terminal"]),
            canonical["integrity_sha256"],
            canonical["updated_at"],
            self._encode_payload(canonical),
            identity["run_id"],
            int(expected_revision),
        )
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, values)
            if int(cursor.rowcount or 0) != 1:
                connection.rollback()
                raise ComprehensiveRunConflict(
                    f"revision_conflict:{identity['run_id']}:{expected_revision}"
                )
            connection.commit()
        return deepcopy(canonical)

    def _validated_copy(self, record: dict[str, Any]) -> dict[str, Any]:
        candidate = deepcopy(record)
        validation = validate_comprehensive_run_record(candidate)
        if validation["status"] != "valid":
            raise ValueError(
                "invalid_comprehensive_run_record:"
                + ",".join(validation["violations"])
            )
        return candidate

    def _encode_payload(self, record: dict[str, Any]) -> Any:
        if self._dialect == "postgres":
            try:
                from psycopg.types.json import Jsonb

                return Jsonb(record)
            except ImportError:
                return json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
        return json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _decode_payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return deepcopy(value)
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            decoded = json.loads(value)
            if not isinstance(decoded, dict):
                raise ValueError("stored_payload_must_be_object")
            return decoded
        raise ValueError("stored_payload_unreadable")

    def _row_values(self, record: dict[str, Any]) -> tuple[Any, ...]:
        identity = record["identity"]
        return (
            identity["run_id"],
            identity["customer_id"],
            identity["project_id"],
            identity["repository"],
            identity["commit_sha"],
            identity["evidence_ledger_id"],
            record["status"],
            int(record["revision"]),
            bool(record["terminal"]),
            record["integrity_sha256"],
            record["updated_at"],
            self._encode_payload(record),
        )


__all__ = [
    "ComprehensiveRunConflict",
    "ComprehensiveRunNotFound",
    "ComprehensiveRunStore",
    "ConnectionFactory",
    "VERSION",
]
