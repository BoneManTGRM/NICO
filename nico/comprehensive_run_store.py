from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, Protocol

from nico.comprehensive_run_record import restore_comprehensive_run_record, validate_comprehensive_run_record

VERSION = "nico.comprehensive_run_store.v4"
_FINAL_REPORT_JOB_TERMINAL_STATUSES = (
    "complete",
    "blocked",
    "failed",
    "cancelled",
    "superseded",
    "expired",
)


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


def _copy_record_for_store(record: Mapping[str, Any]) -> dict[str, Any]:
    """Detach mutable record boundaries without cloning retained stage evidence."""

    copied: dict[str, Any] = {}
    for key, value in record.items():
        if key == "stage_results" and isinstance(value, Mapping):
            copied[key] = dict(value)
        else:
            copied[key] = deepcopy(value)
    copied.setdefault("stage_results", {})
    return copied


class ComprehensiveRunStore:
    """Transactional persistence for canonical Comprehensive run records.

    The store uses optimistic revision checks so two workers cannot silently
    overwrite the same run. Payload integrity is revalidated on every write
    and read. The SQL is intentionally limited to portable DB-API operations;
    production can use a psycopg connection factory with ``dialect='postgres'``.

    Final-report background coordination stores only a tiny lease/heartbeat row in
    the same durable database. The generated report package never passes through the
    lease table; it is committed only through the canonical run transaction.

    Completed stage results are append-only canonical evidence. Persistence copies
    the mutable record and stage-map boundaries, while retaining prior stage values
    by reference until canonical JSON serialization. This avoids multiplying the
    multi-megabyte evidence tree during late-stage continuation without weakening
    integrity validation or optimistic revision checks.
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
        epoch_type = "DOUBLE PRECISION" if self._dialect == "postgres" else "REAL"
        run_statement = f"""
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
        final_report_job_statement = f"""
        CREATE TABLE IF NOT EXISTS nico_comprehensive_final_report_jobs (
            lease_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_epoch {epoch_type} NOT NULL,
            heartbeat_epoch {epoch_type} NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(run_statement)
            cursor.execute(final_report_job_statement)
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
        return _copy_record_for_store(canonical)

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
        return _copy_record_for_store(canonical)

    def create_final_report_job(
        self,
        *,
        lease_id: str,
        run_id: str,
        started_epoch: float,
        heartbeat_epoch: float,
        updated_at: str,
        status: str = "running",
    ) -> dict[str, Any]:
        lease = str(lease_id or "").strip()
        run = str(run_id or "").strip()
        normalized_status = str(status or "").strip().lower()
        if not lease or not run or not normalized_status:
            raise ValueError("final_report_lease_run_and_status_required")
        p = self.placeholder
        statement = f"""
        INSERT INTO nico_comprehensive_final_report_jobs (
            lease_id, run_id, status, started_epoch, heartbeat_epoch, updated_at
        ) VALUES ({','.join([p] * 6)})
        """
        values = (
            lease,
            run,
            normalized_status,
            float(started_epoch),
            float(heartbeat_epoch),
            str(updated_at),
        )
        with self._connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, values)
            except Exception as exc:
                connection.rollback()
                raise ComprehensiveRunConflict(f"final_report_lease_exists:{lease}") from exc
            connection.commit()
        return {
            "lease_id": lease,
            "run_id": run,
            "status": normalized_status,
            "started_epoch": float(started_epoch),
            "heartbeat_epoch": float(heartbeat_epoch),
            "updated_at": str(updated_at),
        }

    def load_final_report_job(self, lease_id: str) -> dict[str, Any] | None:
        lease = str(lease_id or "").strip()
        if not lease:
            return None
        p = self.placeholder
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT lease_id, run_id, status, started_epoch, heartbeat_epoch, updated_at
                FROM nico_comprehensive_final_report_jobs
                WHERE lease_id = {p}
                """,
                (lease,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "lease_id": str(row[0]),
            "run_id": str(row[1]),
            "status": str(row[2]),
            "started_epoch": float(row[3]),
            "heartbeat_epoch": float(row[4]),
            "updated_at": str(row[5]),
        }

    def transition_final_report_job_to_rendering(
        self,
        lease_id: str,
        *,
        started_epoch: float,
        heartbeat_epoch: float,
        updated_at: str,
    ) -> bool:
        """Atomically start rendering only from an active pre-render lease state."""

        lease = str(lease_id or "").strip()
        if not lease:
            raise ValueError("final_report_lease_required")
        p = self.placeholder
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                UPDATE nico_comprehensive_final_report_jobs
                SET status = {p}, started_epoch = {p}, heartbeat_epoch = {p}, updated_at = {p}
                WHERE lease_id = {p} AND status IN ({p}, {p})
                """,
                (
                    "rendering",
                    float(started_epoch),
                    float(heartbeat_epoch),
                    str(updated_at),
                    lease,
                    "queued",
                    "running",
                ),
            )
            changed = int(cursor.rowcount or 0) == 1
            connection.commit()
        return changed

    def update_final_report_job(
        self,
        lease_id: str,
        *,
        status: str,
        heartbeat_epoch: float,
        updated_at: str,
        started_epoch: float | None = None,
    ) -> bool:
        """Update one lease without allowing a terminal state to be reopened.

        The terminal-status fence is enforced in the same SQL write as the heartbeat
        update. This closes the cross-thread and cross-process read-then-write race where
        a stale heartbeat or provider finalizer could otherwise change an already
        ``expired`` lease back to ``rendering`` or another terminal outcome.
        """

        lease = str(lease_id or "").strip()
        normalized_status = str(status or "").strip().lower()
        if not lease or not normalized_status:
            raise ValueError("final_report_lease_and_status_required")
        p = self.placeholder
        terminal_placeholders = ",".join([p] * len(_FINAL_REPORT_JOB_TERMINAL_STATUSES))
        terminal_guard = (
            f"lease_id = {p} AND "
            f"(status NOT IN ({terminal_placeholders}) OR status = {p})"
        )
        if started_epoch is None:
            statement = f"""
                UPDATE nico_comprehensive_final_report_jobs
                SET status = {p}, heartbeat_epoch = {p}, updated_at = {p}
                WHERE {terminal_guard}
            """
            values = (
                normalized_status,
                float(heartbeat_epoch),
                str(updated_at),
                lease,
                *_FINAL_REPORT_JOB_TERMINAL_STATUSES,
                normalized_status,
            )
        else:
            statement = f"""
                UPDATE nico_comprehensive_final_report_jobs
                SET status = {p}, started_epoch = {p}, heartbeat_epoch = {p}, updated_at = {p}
                WHERE {terminal_guard}
            """
            values = (
                normalized_status,
                float(started_epoch),
                float(heartbeat_epoch),
                str(updated_at),
                lease,
                *_FINAL_REPORT_JOB_TERMINAL_STATUSES,
                normalized_status,
            )
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, values)
            changed = int(cursor.rowcount or 0) == 1
            connection.commit()
        return changed

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
        canonical = _copy_record_for_store(record)
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
