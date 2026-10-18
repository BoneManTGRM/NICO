"""Explicit-constructor, one-artifact qualification prototype; NEVER runtime wiring.

No environment switches, schema changes, deletion, expiry cleanup or replacement.
The ordinary API still instantiates the original, unchanged ledger classes. All
writers to a qualified database must use this protocol; mixed writers are not safe.
66 MiB bounds logical JSON bytes, not PostgreSQL disk/WAL or process memory.
"""
from contextlib import contextmanager
import hashlib
import json
import re
from uuid import uuid4

from nico.review_pdf_preparation_jobs_v1 import (
    PREFIX, PreparationConflict, ReviewPdfPreparationJobs, PostgresReviewPdfPreparationJobs,
)

VERSION = 'review-pdf-one-artifact-qualification.v1'
MAX_SERIALIZED_BYTES = 66 * 1024 * 1024
# Stable across replicas/processes; independent of Python's randomized hash().
GLOBAL_LOCK_KEY = int.from_bytes(hashlib.sha256(b'nico.review-pdf.single-artifact.qualification-lock').digest()[:8], 'big', signed=True)


def serialized_size(job):
    return len(json.dumps(job, sort_keys=True, ensure_ascii=True, allow_nan=False).encode('utf-8'))


class _OneArtifactQualification:
    def _reservation(self, job):
        value = job.get('qualification')
        if (not isinstance(value, dict) or value.get('version') != VERSION
                or type(value.get('reserved_bytes')) is not int
                or value['reserved_bytes'] != MAX_SERIALIZED_BYTES
                or value.get('execution_state') not in {'never_started', 'held', 'released'}
                or not isinstance(value.get('execution_owner'), str)):
            raise PreparationConflict('qualification_reservation_unverified')
        state, owner = value['execution_state'], value['execution_owner']
        if (type(job.get('attempts')) is not int
                or (state == 'never_started' and (owner or job['attempts'] != 0))
                or (state != 'never_started' and (not re.fullmatch('[0-9a-f]{32}', owner) or job['attempts'] != 1))):
            raise PreparationConflict('qualification_execution_state_invalid')
        if serialized_size(job) > MAX_SERIALIZED_BYTES:
            raise PreparationConflict('qualification_serialized_limit')
        return value

    def _write(self, connection, identity, job):
        # The global transaction lock (SQLite write lock in fixtures) is already held.
        ids = self._queue_ids(connection)
        if any(value != identity.job_id for value in ids) or len(ids) > 1:
            raise PreparationConflict('qualification_one_artifact_full')
        if not ids:
            if job.get('status') != 'queued' or job.get('attempts') != 0 or 'qualification' in job:
                raise PreparationConflict('qualification_initial_reservation_required')
            job['qualification'] = dict(version=VERSION, reserved_bytes=MAX_SERIALIZED_BYTES,
                execution_state='never_started', execution_owner='')
        current = self._reservation(job)
        if ids:
            prior = self._reservation(self._read(connection, identity))
            transition = (prior['execution_state'], current['execution_state'])
            if transition not in {('never_started', 'never_started'), ('never_started', 'held'),
                                  ('held', 'held'), ('held', 'released'), ('released', 'released')}:
                raise PreparationConflict('qualification_execution_transition_invalid')
            if prior['execution_state'] != 'never_started' and prior['execution_owner'] != current['execution_owner']:
                raise PreparationConflict('qualification_execution_owner_changed')
        return super()._write(connection, identity, job)

    def claim(self, identity):
        with self._transaction(identity) as connection:
            job = self._read(connection, identity)
            if job is None:
                raise PreparationConflict('preparation_not_enqueued')
            reservation = self._reservation(job)
            # No lease-expiry reclaim or automatic second attempt in this prototype.
            # A lost owner leaves durable occupancy held until physical exit is proven.
            if (job['status'] != 'queued' or job['attempts'] != 0
                    or reservation['execution_state'] != 'never_started'):
                return None
            now = self._now(connection)
            if now >= job['deadline_epoch']:
                job.update(status='budget_exhausted', updated_epoch=now, lease_id='')
                self._write(connection, identity, job)
                return None
            owner = uuid4().hex
            reservation.update(execution_state='held', execution_owner=owner)
            job.update(status='rendering', phase='preparing', attempts=1,
                       lease_id=owner, lease_until_epoch=min(now + 30, job['deadline_epoch']),
                       updated_epoch=now)
            self._write(connection, identity, job)
            return job

    def _owned(self, connection, identity, lease_id):
        # Preserve every original status/lease/deadline check for publication.
        job, now = super()._owned(connection, identity, lease_id)
        reservation = self._reservation(job)
        if (reservation['execution_state'] != 'held'
                or reservation['execution_owner'] != lease_id):
            raise PreparationConflict('qualification_execution_owner_changed')
        return job, now

    def confirm_execution_exit(self, identity, owner, *, state, supervisor):
        """Internal cleanup receipt, not a route or lease/publication override.

        The coordinator invokes this only after actual child exit, all guarded
        operations and private-file cleanup. Lost/unconfirmed owners cannot call it.
        Lifecycle status, lease and retained bytes are deliberately left unchanged.
        """
        if (state.get('physical_worker_exit_confirmed') is not True
                or state.get('temporary_files_cleanup_confirmed') is not True
                or any(not guard.idle() for guard in state['pending_guards'])
                or (supervisor is not None and supervisor.is_alive())):
            raise PreparationConflict('qualification_physical_exit_unconfirmed')
        with self._transaction(identity) as connection:
            job = self._read(connection, identity)
            if job is None:
                raise PreparationConflict('qualification_owner_missing')
            reservation = self._reservation(job)
            if not owner or reservation['execution_owner'] != owner:
                raise PreparationConflict('qualification_execution_owner_changed')
            if reservation['execution_state'] == 'released':
                return  # Same owner's acknowledged receipt is idempotent.
            if reservation['execution_state'] != 'held':
                raise PreparationConflict('qualification_execution_not_held')
            reservation['execution_state'] = 'released'
            job['updated_epoch'] = self._now(connection)
            self._write(connection, identity, job)


class QualificationOnlySQLiteJobs(_OneArtifactQualification, ReviewPdfPreparationJobs):
    """Disposable fixture adapter. SQLite BEGIN IMMEDIATE serializes all writers."""
    def _queue_ids(self, connection):
        rows = connection.execute(
            "SELECT item_id FROM nico_records WHERE table_name='client_jobs' AND "
            "(substr(item_id,1,?)=? OR CASE WHEN json_valid(payload) "
            "THEN json_extract(payload,'$.workflow') ELSE '' END LIKE 'review_pdf_preparation.%') LIMIT 2",
            (len(PREFIX), PREFIX),
        ).fetchall()
        return [row['item_id'] for row in rows]


class QualificationOnlyPostgresJobs(_OneArtifactQualification, PostgresReviewPdfPreparationJobs):
    """Existing client_jobs only; requires real-PG qualification before any use."""
    @contextmanager
    def _transaction(self, identity, *, commit_guard=None):
        connection = self.adapter._connect()
        try:
            connection.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            connection.execute("SET LOCAL lock_timeout = '5s'")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            # One lock order for admission, claim, cancellation, publish and cleanup.
            connection.execute('SELECT pg_advisory_xact_lock(%s)', (GLOBAL_LOCK_KEY,))
            identity_key = int.from_bytes(hashlib.sha256(identity.job_id.encode()).digest()[:8], 'big', signed=True)
            connection.execute('SELECT pg_advisory_xact_lock(%s)', (identity_key,))
            yield connection
            if commit_guard is not None:
                commit_guard.begin_commit()
            connection.commit()
            if commit_guard is not None:
                commit_guard.end_commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _queue_ids(self, connection):
        rows = connection.execute(
            "SELECT job_id FROM client_jobs WHERE left(job_id,%s)=%s "
            "OR payload->>'workflow' LIKE %s LIMIT 2",
            (len(PREFIX), PREFIX, 'review_pdf_preparation.%'),
        ).fetchall()
        return [row['job_id'] for row in rows]
