from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Iterator, Protocol

VERSION = "nico.comprehensive_final_report_job_store.v1"
DEFAULT_MAX_ACTIVE_WORKERS = 1
_POSTGRES_CLAIM_LOCK_ID = 9952026


class ConnectionLike(Protocol):
    def cursor(self) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[], ConnectionLike]


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


class ComprehensiveFinalReportJobStore:
    """Durable lease and capacity table for long final-report rendering.

    The canonical Comprehensive record remains the only source of report truth. This
    table stores ownership, heartbeat, retry, queue, and terminal worker metadata.

    Claims are serialized through a Postgres advisory transaction lock or SQLite
    ``BEGIN IMMEDIATE``. This enforces a database-wide active-render limit across app
    processes so simultaneous proof runs cannot saturate the production API.
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        dialect: str = "sqlite",
    ) -> None:
        normalized = _text(dialect).lower()
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
        statement = """
        CREATE TABLE IF NOT EXISTS nico_comprehensive_final_report_jobs (
            run_id TEXT PRIMARY KEY,
            repository TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            evidence_ledger_id TEXT NOT NULL,
            state TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            lease_owner TEXT,
            lease_expires_at TEXT,
            heartbeat_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            error_code TEXT,
            error_message TEXT,
            updated_at TEXT NOT NULL
        )
        """
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement)
            connection.commit()

    def load(self, run_id: str) -> dict[str, Any] | None:
        normalized = _text(run_id)
        if not normalized:
            raise ValueError("run_id_required")
        p = self.placeholder
        statement = f"""
        SELECT run_id, repository, commit_sha, evidence_ledger_id, state, attempt,
               lease_owner, lease_expires_at, heartbeat_at, started_at, finished_at,
               error_code, error_message, updated_at
        FROM nico_comprehensive_final_report_jobs
        WHERE run_id = {p}
        """
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, (normalized,))
            row = cursor.fetchone()
        return self._row(row) if row is not None else None

    def claim(
        self,
        *,
        run_id: str,
        repository: str,
        commit_sha: str,
        evidence_ledger_id: str,
        lease_owner: str,
        lease_seconds: int = 90,
        max_active_workers: int = DEFAULT_MAX_ACTIVE_WORKERS,
    ) -> dict[str, Any]:
        identity = {
            "run_id": _text(run_id),
            "repository": _text(repository),
            "commit_sha": _text(commit_sha),
            "evidence_ledger_id": _text(evidence_ledger_id),
        }
        if not all(identity.values()):
            raise ValueError("final_report_job_identity_required")
        owner = _text(lease_owner)
        if not owner:
            raise ValueError("lease_owner_required")
        capacity = max(1, int(max_active_workers))
        now = _now()
        now_text = _iso(now)
        expires_text = _iso(now + timedelta(seconds=max(30, int(lease_seconds))))
        p = self.placeholder
        insert = (
            f"INSERT INTO nico_comprehensive_final_report_jobs ("
            "run_id, repository, commit_sha, evidence_ledger_id, state, attempt, "
            "lease_owner, lease_expires_at, heartbeat_at, started_at, finished_at, "
            "error_code, error_message, updated_at) "
            f"VALUES ({','.join([p] * 14)}) "
            + (
                "ON CONFLICT (run_id) DO NOTHING"
                if self._dialect == "postgres"
                else "ON CONFLICT(run_id) DO NOTHING"
            )
        )
        insert_values = (
            identity["run_id"],
            identity["repository"],
            identity["commit_sha"],
            identity["evidence_ledger_id"],
            "queued",
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            now_text,
        )
        select_current = f"""
        SELECT run_id, repository, commit_sha, evidence_ledger_id, state, attempt,
               lease_owner, lease_expires_at, heartbeat_at, started_at, finished_at,
               error_code, error_message, updated_at
        FROM nico_comprehensive_final_report_jobs
        WHERE run_id = {p}
        """
        active_count = f"""
        SELECT COUNT(*)
        FROM nico_comprehensive_final_report_jobs
        WHERE state = 'running'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at >= {p}
          AND run_id <> {p}
        """
        update = f"""
        UPDATE nico_comprehensive_final_report_jobs
        SET state = {p},
            attempt = attempt + 1,
            lease_owner = {p},
            lease_expires_at = {p},
            heartbeat_at = {p},
            started_at = COALESCE(started_at, {p}),
            finished_at = NULL,
            error_code = NULL,
            error_message = NULL,
            updated_at = {p}
        WHERE run_id = {p}
          AND repository = {p}
          AND commit_sha = {p}
          AND evidence_ledger_id = {p}
          AND state <> 'complete'
          AND (
              lease_owner IS NULL
              OR lease_expires_at IS NULL
              OR lease_expires_at < {p}
              OR lease_owner = {p}
              OR state IN ('queued', 'failed')
          )
        """
        update_values = (
            "running",
            owner,
            expires_text,
            now_text,
            now_text,
            now_text,
            identity["run_id"],
            identity["repository"],
            identity["commit_sha"],
            identity["evidence_ledger_id"],
            now_text,
            owner,
        )

        claimed = False
        capacity_blocked = False
        with self._connection() as connection:
            cursor = connection.cursor()
            if self._dialect == "postgres":
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (_POSTGRES_CLAIM_LOCK_ID,),
                )
            else:
                cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(insert, insert_values)
            cursor.execute(select_current, (identity["run_id"],))
            current_row = cursor.fetchone()
            if current_row is None:
                raise RuntimeError("final_report_job_missing_after_insert")
            current = self._row(current_row)
            if (
                current["repository"] != identity["repository"]
                or current["commit_sha"] != identity["commit_sha"]
                or current["evidence_ledger_id"] != identity["evidence_ledger_id"]
            ):
                raise ValueError("final_report_job_identity_mismatch")

            lease_active = (
                current["state"] == "running"
                and bool(current.get("lease_owner"))
                and bool(current.get("lease_expires_at"))
                and str(current["lease_expires_at"]) >= now_text
                and current.get("lease_owner") != owner
            )
            if current["state"] != "complete" and not lease_active:
                cursor.execute(
                    active_count,
                    (now_text, identity["run_id"]),
                )
                row = cursor.fetchone()
                active = int(row[0] if row else 0)
                if active < capacity:
                    cursor.execute(update, update_values)
                    claimed = int(cursor.rowcount or 0) == 1
                else:
                    capacity_blocked = True
            connection.commit()

        job = self.load(identity["run_id"])
        if job is None:
            raise RuntimeError("final_report_job_missing_after_claim")
        return {
            **job,
            "claimed": claimed,
            "capacity_blocked": capacity_blocked,
            "max_active_workers": capacity,
        }

    def heartbeat(
        self,
        run_id: str,
        *,
        lease_owner: str,
        lease_seconds: int = 90,
    ) -> bool:
        now = _now()
        p = self.placeholder
        statement = f"""
        UPDATE nico_comprehensive_final_report_jobs
        SET heartbeat_at = {p}, lease_expires_at = {p}, updated_at = {p}
        WHERE run_id = {p} AND state = 'running' AND lease_owner = {p}
        """
        values = (
            _iso(now),
            _iso(now + timedelta(seconds=max(30, int(lease_seconds)))),
            _iso(now),
            _text(run_id),
            _text(lease_owner),
        )
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, values)
            changed = int(cursor.rowcount or 0) == 1
            connection.commit()
        return changed

    def finish(
        self,
        run_id: str,
        *,
        lease_owner: str,
        state: str,
        error_code: str = "",
        error_message: str = "",
    ) -> bool:
        normalized_state = _text(state).lower()
        if normalized_state not in {"complete", "failed"}:
            raise ValueError("final_report_job_terminal_state_invalid")
        now_text = _iso(_now())
        p = self.placeholder
        statement = f"""
        UPDATE nico_comprehensive_final_report_jobs
        SET state = {p}, lease_owner = NULL, lease_expires_at = NULL,
            heartbeat_at = {p}, finished_at = {p}, error_code = {p},
            error_message = {p}, updated_at = {p}
        WHERE run_id = {p} AND lease_owner = {p}
        """
        values = (
            normalized_state,
            now_text,
            now_text,
            _text(error_code) or None,
            _text(error_message) or None,
            now_text,
            _text(run_id),
            _text(lease_owner),
        )
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, values)
            changed = int(cursor.rowcount or 0) == 1
            connection.commit()
        return changed

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        keys = (
            "run_id",
            "repository",
            "commit_sha",
            "evidence_ledger_id",
            "state",
            "attempt",
            "lease_owner",
            "lease_expires_at",
            "heartbeat_at",
            "started_at",
            "finished_at",
            "error_code",
            "error_message",
            "updated_at",
        )
        result = dict(zip(keys, row, strict=True))
        result["attempt"] = int(result.get("attempt") or 0)
        result["artifact_schema"] = VERSION
        result["durable_lease"] = True
        return result


__all__ = [
    "ComprehensiveFinalReportJobStore",
    "ConnectionFactory",
    "DEFAULT_MAX_ACTIVE_WORKERS",
    "VERSION",
]
