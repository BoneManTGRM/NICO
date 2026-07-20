from __future__ import annotations

import json
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, Protocol

from nico.comprehensive_run_record import restore_comprehensive_run_record, validate_comprehensive_run_record

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
    """

    def __init__(self, connection_factory: ConnectionFactory, *, dialect: str = "sqlite") -> None:
        normalized = dialect.strip().lower()
        if normalized not in {"sqlite", "postgres"}:
            raise ValueError("unsupported_dialect")
        self._connection_factory = connection_factory
        self._dialect = normalized

    @property
    def placeholder(self) -> str:
        return "%s" if self._dialect == "postgres" else "?"

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
                raise ComprehensiveRunConflict(f"run_already_exists:{identity['run_id']}") from exc
            connection.commit()
        return deepcopy(canonical)

    def load(self, run_id: str) -> dict[str, Any]:
        normalized = str(run_id or "").strip()
        if not normalized:
            raise ValueError("run_id_required")
        p = self.placeholder
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT payload FROM nico_comprehensive_runs WHERE run_id = {p}", (normalized,))
            row = cursor.fetchone()
        if row is None:
            raise ComprehensiveRunNotFound(normalized)
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("persisted_payload_must_be_object")
        return restore_comprehensive_run_record(payload)

    def save(self, record: dict[str, Any], *, expected_revision: int) -> dict[str, Any]:
        canonical = self._validated_copy(record)
        identity = canonical["identity"]
        current_revision = int(canonical["revision"])
        if current_revision != int(expected_revision) + 1:
            raise ComprehensiveRunConflict(
                f"revision_must_advance_once:expected:{int(expected_revision) + 1}:actual:{current_revision}"
            )
        p = self.placeholder
        statement = f"""
        UPDATE nico_comprehensive_runs SET
            customer_id = {p}, project_id = {p}, repository = {p}, commit_sha = {p},
            evidence_ledger_id = {p}, status = {p}, revision = {p}, terminal = {p},
            integrity_sha256 = {p}, updated_at = {p}, payload = {p}
        WHERE run_id = {p} AND revision = {p}
        """
        values = self._row_values(canonical)[1:] + (identity["run_id"], int(expected_revision))
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, values)
            if int(cursor.rowcount or 0) != 1:
                connection.rollback()
                raise ComprehensiveRunConflict(
                    f"stale_revision:{identity['run_id']}:expected:{int(expected_revision)}"
                )
            connection.commit()
        return deepcopy(canonical)

    def list_recent(self, *, customer_id: str, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
        customer = str(customer_id or "").strip()
        project = str(project_id or "").strip()
        if not customer or not project:
            raise ValueError("customer_and_project_required")
        bounded_limit = max(1, min(200, int(limit)))
        p = self.placeholder
        statement = f"""
        SELECT payload FROM nico_comprehensive_runs
        WHERE customer_id = {p} AND project_id = {p}
        ORDER BY updated_at DESC, run_id DESC
        LIMIT {p}
        """
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, (customer, project, bounded_limit))
            rows = cursor.fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            records.append(restore_comprehensive_run_record(payload))
        return records

    def _validated_copy(self, record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise TypeError("run_record_must_be_object")
        canonical = deepcopy(record)
        validation = validate_comprehensive_run_record(canonical)
        if validation["status"] != "valid":
            raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
        return canonical

    def _row_values(self, record: dict[str, Any]) -> tuple[Any, ...]:
        identity = record["identity"]
        payload: Any = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if self._dialect == "postgres":
            # psycopg accepts serialized JSON for JSONB columns without requiring a hard dependency here.
            payload = payload
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
            payload,
        )


__all__ = [
    "ComprehensiveRunConflict",
    "ComprehensiveRunNotFound",
    "ComprehensiveRunStore",
    "ConnectionFactory",
    "VERSION",
]
