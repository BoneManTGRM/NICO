from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, Protocol

from nico.comprehensive_run_record import (
    restore_comprehensive_run_record,
    validate_comprehensive_run_record,
)

VERSION = "nico.comprehensive_run_store.v5"
_FINAL_REPORT_JOB_TERMINAL_STATUSES = (
    "complete",
    "blocked",
    "failed",
    "cancelled",
    "superseded",
    "expired",
)


def _review_history(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = record.get("review_history")
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("review_history_commitment_payload_invalid")
    return [dict(item) for item in value]


def _review_history_sha256(history: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        history,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _decode_run_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("persisted_payload_must_be_object")
    return payload


def _browser_projection_json(projection: Mapping[str, Any]) -> str:
    return json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _browser_projection_sha256(projection: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _browser_projection_json(projection).encode("utf-8")
    ).hexdigest()


def _assert_review_history_commitment(
    record: Mapping[str, Any],
    *,
    committed_count: Any,
    committed_sha256: Any,
    allow_append: bool,
) -> list[dict[str, Any]]:
    if isinstance(committed_count, bool) or not isinstance(committed_count, int):
        raise ValueError("review_history_commitment_count_invalid")
    committed_digest = str(committed_sha256 or "").strip().casefold()
    history = _review_history(record)
    if committed_count < 0 or len(history) < committed_count:
        raise ValueError("review_history_commitment_cannot_be_truncated")
    if _review_history_sha256(history[:committed_count]) != committed_digest:
        raise ValueError("review_history_commitment_prefix_mismatch")
    if not allow_append and len(history) != committed_count:
        raise ValueError("review_history_commitment_uncommitted_events")
    return history


def _initialize_missing_review_history_commitment(
    cursor: Any,
    *,
    placeholder: str,
    run_id: str,
    payload: Any,
) -> tuple[int, str]:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        raise ValueError("review_history_commitment_run_id_required")
    history = _review_history(_decode_run_payload(payload))
    history_digest = _review_history_sha256(history)
    cursor.execute(
        """
        INSERT INTO nico_comprehensive_review_history_commitments (
            run_id, event_count, chain_sha256
        ) VALUES ("""
        + ",".join([placeholder] * 3)
        + ") ON CONFLICT (run_id) DO NOTHING",
        (normalized_run_id, len(history), history_digest),
    )
    cursor.execute(
        f"""
        SELECT event_count, chain_sha256
        FROM nico_comprehensive_review_history_commitments
        WHERE run_id = {placeholder}
        """,
        (normalized_run_id,),
    )
    commitment = cursor.fetchone()
    if commitment is None or (
        int(commitment[0]) != len(history)
        or str(commitment[1]).strip().casefold() != history_digest
    ):
        raise ValueError("review_history_commitment_backfill_conflict")
    return int(commitment[0]), str(commitment[1])


class ConnectionLike(Protocol):
    def cursor(self) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[], ConnectionLike]
BrowserProjectionBuilder = Callable[[dict[str, Any]], dict[str, Any]]


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
        self._browser_projection_builder: BrowserProjectionBuilder | None = None

    def bind_browser_projection_builder(
        self,
        builder: BrowserProjectionBuilder,
    ) -> None:
        """Bind the request-layer projector used for durable bounded status reads."""

        if not callable(builder):
            raise TypeError("browser_projection_builder_must_be_callable")
        self._browser_projection_builder = builder

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
        review_history_statement = """
        CREATE TABLE IF NOT EXISTS nico_comprehensive_review_history_commitments (
            run_id TEXT PRIMARY KEY,
            event_count INTEGER NOT NULL,
            chain_sha256 TEXT NOT NULL
        )
        """
        browser_projection_statement = f"""
        CREATE TABLE IF NOT EXISTS nico_comprehensive_browser_projections (
            run_id TEXT PRIMARY KEY,
            revision INTEGER NOT NULL,
            run_integrity_sha256 TEXT NOT NULL,
            projection_sha256 TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            projection {payload_type} NOT NULL
        )
        """
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(run_statement)
            cursor.execute(final_report_job_statement)
            cursor.execute(review_history_statement)
            cursor.execute(browser_projection_statement)
            connection.commit()

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        canonical = self._validated_copy(record)
        browser_projection = self._build_browser_projection(canonical)
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
        history = _review_history(canonical)
        with self._connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, values)
                p = self.placeholder
                cursor.execute(
                    """
                    INSERT INTO nico_comprehensive_review_history_commitments (
                        run_id, event_count, chain_sha256
                    ) VALUES ("""
                    + ",".join([p] * 3)
                    + ")",
                    (
                        identity["run_id"],
                        len(history),
                        _review_history_sha256(history),
                    ),
                )
                self._write_browser_projection(
                    cursor,
                    canonical,
                    browser_projection,
                )
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
            cursor.execute(
                f"""
                SELECT runs.payload, commitments.event_count, commitments.chain_sha256
                FROM nico_comprehensive_runs AS runs
                LEFT JOIN nico_comprehensive_review_history_commitments AS commitments
                    ON commitments.run_id = runs.run_id
                WHERE runs.run_id = {p}
                """,
                (normalized,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ComprehensiveRunNotFound(normalized)
            payload = _decode_run_payload(row[0])
            initialized = row[1] is None or row[2] is None
            commitment = (
                _initialize_missing_review_history_commitment(
                    cursor,
                    placeholder=p,
                    run_id=normalized,
                    payload=payload,
                )
                if initialized
                else (int(row[1]), str(row[2]))
            )
            _assert_review_history_commitment(
                payload,
                committed_count=commitment[0],
                committed_sha256=commitment[1],
                allow_append=False,
            )
            restored = restore_comprehensive_run_record(payload)
            if initialized:
                connection.commit()
            return restored

    def load_browser_projection(self, run_id: str) -> dict[str, Any] | None:
        """Load a small, transaction-bound browser response without the canonical tree.

        The full run remains the only artifact and review authority. This projection is
        generated from a fully validated run during the same create/save transaction,
        then hash-checked and cross-checked against the canonical row metadata here.
        Missing legacy projections fall back to the established full read path at the
        route boundary; a present but inconsistent projection fails closed.
        """

        normalized = str(run_id or "").strip()
        if not normalized:
            raise ValueError("run_id_required")
        p = self.placeholder
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT projections.projection,
                       projections.projection_sha256,
                       projections.revision,
                       projections.run_integrity_sha256,
                       runs.customer_id,
                       runs.project_id,
                       runs.repository,
                       runs.commit_sha,
                       runs.status,
                       runs.revision,
                       runs.terminal,
                       runs.integrity_sha256
                FROM nico_comprehensive_browser_projections AS projections
                INNER JOIN nico_comprehensive_runs AS runs
                    ON runs.run_id = projections.run_id
                WHERE projections.run_id = {p}
                """,
                (normalized,),
            )
            row = cursor.fetchone()
        if row is None:
            return None

        projection = _decode_run_payload(row[0])
        claimed_projection_sha256 = str(row[1] or "").strip().casefold()
        if claimed_projection_sha256 != _browser_projection_sha256(projection):
            raise ValueError("browser_projection_hash_mismatch")

        projection_revision = int(row[2])
        projection_run_integrity = str(row[3] or "").strip().casefold()
        run_revision = int(row[9])
        run_integrity = str(row[11] or "").strip().casefold()
        if projection_revision != run_revision:
            raise ValueError("browser_projection_revision_mismatch")
        if projection_run_integrity != run_integrity:
            raise ValueError("browser_projection_run_integrity_mismatch")

        record = (
            projection.get("record")
            if isinstance(projection.get("record"), Mapping)
            else {}
        )
        identity = (
            record.get("identity")
            if isinstance(record.get("identity"), Mapping)
            else {}
        )
        response_projection = (
            projection.get("response_projection")
            if isinstance(projection.get("response_projection"), Mapping)
            else {}
        )
        expected_values = {
            "run_id": normalized,
            "customer_id": str(row[4]),
            "project_id": str(row[5]),
            "repository": str(row[6]),
            "commit_sha": str(row[7]),
        }
        for field, expected in expected_values.items():
            observed = str(
                projection.get(field)
                if field in projection
                else identity.get(field)
                or ""
            ).strip()
            if observed != expected:
                raise ValueError(f"browser_projection_identity_mismatch:{field}")
        if int(projection.get("revision") or -1) != run_revision:
            raise ValueError("browser_projection_response_revision_mismatch")
        if (
            str(projection.get("integrity_sha256") or "").strip().casefold()
            != run_integrity
        ):
            raise ValueError("browser_projection_response_integrity_mismatch")
        if str(projection.get("canonical_status") or "").strip() != str(row[8]):
            raise ValueError("browser_projection_status_mismatch")
        if bool(projection.get("terminal")) != bool(row[10]):
            raise ValueError("browser_projection_terminal_mismatch")
        if response_projection.get("browser_projection") is not True:
            raise ValueError("browser_projection_contract_missing")
        if response_projection.get("durable_projection") is not True:
            raise ValueError("browser_projection_durability_contract_missing")
        return deepcopy(projection)

    def save(self, record: dict[str, Any], *, expected_revision: int) -> dict[str, Any]:
        canonical = self._validated_copy(record)
        browser_projection = self._build_browser_projection(canonical)
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
            cursor.execute(
                f"""
                SELECT runs.payload, commitments.event_count, commitments.chain_sha256
                FROM nico_comprehensive_runs AS runs
                LEFT JOIN nico_comprehensive_review_history_commitments AS commitments
                    ON commitments.run_id = runs.run_id
                WHERE runs.run_id = {p}
                """,
                (identity["run_id"],),
            )
            persisted = cursor.fetchone()
            if persisted is None:
                raise ComprehensiveRunConflict(
                    f"review_history_commitment_missing:{identity['run_id']}"
                )
            commitment = (
                _initialize_missing_review_history_commitment(
                    cursor,
                    placeholder=p,
                    run_id=identity["run_id"],
                    payload=persisted[0],
                )
                if persisted[1] is None or persisted[2] is None
                else (int(persisted[1]), str(persisted[2]))
            )
            history = _assert_review_history_commitment(
                canonical,
                committed_count=commitment[0],
                committed_sha256=commitment[1],
                allow_append=True,
            )
            cursor.execute(statement, values)
            if int(cursor.rowcount or 0) != 1:
                connection.rollback()
                raise ComprehensiveRunConflict(
                    f"stale_revision:{identity['run_id']}:expected:{int(expected_revision)}"
                )
            cursor.execute(
                f"""
                UPDATE nico_comprehensive_review_history_commitments
                SET event_count = {p}, chain_sha256 = {p}
                WHERE run_id = {p} AND event_count = {p} AND chain_sha256 = {p}
                """,
                (
                    len(history),
                    _review_history_sha256(history),
                    identity["run_id"],
                    int(commitment[0]),
                    str(commitment[1]),
                ),
            )
            if int(cursor.rowcount or 0) != 1:
                connection.rollback()
                raise ComprehensiveRunConflict(
                    f"review_history_commitment_conflict:{identity['run_id']}"
                )
            self._write_browser_projection(
                cursor,
                canonical,
                browser_projection,
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
        SELECT runs.run_id, runs.payload,
               commitments.event_count, commitments.chain_sha256
        FROM nico_comprehensive_runs AS runs
        LEFT JOIN nico_comprehensive_review_history_commitments AS commitments
            ON commitments.run_id = runs.run_id
        WHERE runs.customer_id = {p} AND runs.project_id = {p}
        ORDER BY runs.updated_at DESC, runs.run_id DESC
        LIMIT {p}
        """
        records: list[dict[str, Any]] = []
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, (customer, project, bounded_limit))
            rows = cursor.fetchall()
            initialized = False
            for row in rows:
                payload = _decode_run_payload(row[1])
                row_initialized = row[2] is None or row[3] is None
                commitment = (
                    _initialize_missing_review_history_commitment(
                        cursor,
                        placeholder=p,
                        run_id=str(row[0]),
                        payload=payload,
                    )
                    if row_initialized
                    else (int(row[2]), str(row[3]))
                )
                _assert_review_history_commitment(
                    payload,
                    committed_count=commitment[0],
                    committed_sha256=commitment[1],
                    allow_append=False,
                )
                records.append(restore_comprehensive_run_record(payload))
                initialized = initialized or row_initialized
            if initialized:
                connection.commit()
        return records

    def _build_browser_projection(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any] | None:
        builder = self._browser_projection_builder
        if builder is None:
            return None
        projection = builder(record)
        if not isinstance(projection, dict):
            raise TypeError("browser_projection_must_be_object")
        return projection

    def _write_browser_projection(
        self,
        cursor: Any,
        record: dict[str, Any],
        projection: dict[str, Any] | None,
    ) -> None:
        if projection is None:
            return
        identity = record["identity"]
        run_id = str(identity["run_id"])
        revision = int(record["revision"])
        run_integrity = str(record["integrity_sha256"])
        updated_at = str(record["updated_at"])
        serialized = _browser_projection_json(projection)
        projection_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        p = self.placeholder
        cursor.execute(
            f"""
            INSERT INTO nico_comprehensive_browser_projections (
                run_id, revision, run_integrity_sha256,
                projection_sha256, updated_at, projection
            ) VALUES ({','.join([p] * 6)})
            ON CONFLICT (run_id) DO UPDATE SET
                revision = excluded.revision,
                run_integrity_sha256 = excluded.run_integrity_sha256,
                projection_sha256 = excluded.projection_sha256,
                updated_at = excluded.updated_at,
                projection = excluded.projection
            """,
            (
                run_id,
                revision,
                run_integrity,
                projection_sha256,
                updated_at,
                serialized,
            ),
        )

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
    "BrowserProjectionBuilder",
    "ComprehensiveRunConflict",
    "ComprehensiveRunNotFound",
    "ComprehensiveRunStore",
    "ConnectionFactory",
    "VERSION",
]
