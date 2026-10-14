"""Local test scaffold for a review-PDF ledger in a SQLite runtime collection.

No worker, route, schema initialization or assessment write is installed here.
SQLite adapter type does not establish deployment durability or replica sharing.
This implementation is not suitable for activation on the current production
service, which has no volume; PostgreSQL support remains unimplemented.
Callers must authenticate and validate the retained source before enqueueing.
Rendered is deliberately unverified: this slice cannot authorize a download.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from uuid import uuid4

from nico.durable_runtime_storage import SQLiteRuntimeAdapter

WORKFLOW = 'review_pdf_preparation.v1'
PREFIX = 'reviewpdfprep_'


class PreparationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparationIdentity:
    customer_id: str
    project_id: str
    run_id: str
    repository: str
    commit_sha: str
    source_revision: int
    source_integrity_sha256: str
    canonical_truth_sha256: str
    source_artifact_sha256: str
    renderer_revision: str
    policy_sha256: str
    language: str

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key == 'source_revision':
                if type(value) is not int or value < 1:
                    raise ValueError('invalid_source_revision')
            elif type(value) is not str or not value or value != value.strip() or len(value) > 2048:
                raise ValueError('invalid_preparation_identity')
        for key in ('source_integrity_sha256', 'canonical_truth_sha256',
                    'source_artifact_sha256', 'policy_sha256'):
            if not re.fullmatch('[0-9a-f]{64}', getattr(self, key)):
                raise ValueError('invalid_preparation_digest')
        for key in ('commit_sha', 'renderer_revision'):
            if not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', getattr(self, key)):
                raise ValueError('invalid_preparation_revision')
        if self.language not in ('en', 'es-MX'):
            raise ValueError('invalid_preparation_language')

    @property
    def job_id(self):
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(',', ':')).encode()
        return PREFIX + hashlib.sha256(encoded).hexdigest()


class ReviewPdfPreparationJobs:
    """Atomic metadata-only transactions; no memory fallback or implicit migration."""

    def __init__(self, adapter):
        if not isinstance(adapter, SQLiteRuntimeAdapter):
            raise TypeError('review_pdf_jobs_require_existing_sqlite_runtime')
        self.adapter = adapter

    @contextmanager
    def _transaction(self):
        connection = self.adapter._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _now(connection):
        return float(connection.execute("SELECT (julianday('now') - 2440587.5) * 86400.0").fetchone()[0])

    @staticmethod
    def _read(connection, identity):
        row = connection.execute(
            "SELECT customer_id, project_id, payload FROM nico_records WHERE table_name='client_jobs' AND item_id=?",
            (identity.job_id,),
        ).fetchone()
        if row is None:
            return None
        job = json.loads(row['payload'])
        if (row['customer_id'] != identity.customer_id or row['project_id'] != identity.project_id
                or job.get('workflow') != WORKFLOW or job.get('identity') != asdict(identity)
                or job.get('job_id') != identity.job_id):
            raise PreparationConflict('preparation_identity_conflict')
        return job

    @staticmethod
    def _write(connection, identity, job):
        # Caller owns the write transaction. Never call the adapter's separate
        # upsert transaction, and never write the source assessment collection.
        connection.execute(
            "INSERT INTO nico_records(table_name,item_id,customer_id,project_id,created_at,updated_at,payload) "
            "VALUES('client_jobs',?,?,?,?,?,?) ON CONFLICT(table_name,item_id) DO UPDATE SET "
            "updated_at=excluded.updated_at,payload=excluded.payload",
            (identity.job_id, identity.customer_id, identity.project_id,
             str(job['created_epoch']), str(job['updated_epoch']), json.dumps(job, sort_keys=True)),
        )

    def get(self, identity):
        connection = self.adapter._connect()
        try:
            return self._read(connection, identity)
        finally:
            connection.close()

    def enqueue(self, identity, *, preparation_authorized=False):
        if preparation_authorized is not True:
            raise PermissionError('explicit_review_pdf_preparation_required')
        with self._transaction() as connection:
            prior = self._read(connection, identity)
            if prior is not None:
                return prior
            now = self._now(connection)
            job = dict(job_id=identity.job_id, workflow=WORKFLOW, identity=asdict(identity),
                       status='queued', attempts=0, created_epoch=now, updated_epoch=now,
                       deadline_epoch=now + 900, lease_id='', lease_until_epoch=0,
                       human_review_required=True, client_delivery_allowed=False)
            self._write(connection, identity, job)
            return job

    def claim(self, identity):
        """Claim only after the future coordinator acquires existing render capacity."""
        with self._transaction() as connection:
            job = self._read(connection, identity)
            if job is None:
                raise PreparationConflict('preparation_not_enqueued')
            now = self._now(connection)
            if job['status'] not in ('queued', 'rendering'):
                return None
            if now >= job['deadline_epoch'] or job['attempts'] >= 2 and now >= job['lease_until_epoch']:
                job.update(status='budget_exhausted', updated_epoch=now, lease_id='')
                self._write(connection, identity, job)
                return None
            if job['status'] == 'rendering' and now < job['lease_until_epoch']:
                return None
            job.update(status='rendering', attempts=job['attempts'] + 1,
                       lease_id=uuid4().hex, lease_until_epoch=min(now + 30, job['deadline_epoch']),
                       updated_epoch=now)
            self._write(connection, identity, job)
            return job

    def _owned(self, connection, identity, lease_id):
        job = self._read(connection, identity)
        now = self._now(connection)
        if (job is None or job['status'] != 'rendering' or not lease_id
                or job['lease_id'] != lease_id or now >= job['lease_until_epoch']
                or now >= job['deadline_epoch']):
            raise PreparationConflict('preparation_lease_not_owned')
        return job, now

    def heartbeat(self, identity, lease_id):
        with self._transaction() as connection:
            job, now = self._owned(connection, identity, lease_id)
            job.update(updated_epoch=now, lease_until_epoch=min(now + 30, job['deadline_epoch']))
            self._write(connection, identity, job)
            return job

    def record_rendered(self, identity, lease_id, *, observed_source, pdf_sha256):
        """Fence stale results. This is not semantic validation or publication."""
        if observed_source != identity:
            raise PreparationConflict('preparation_source_changed')
        if type(pdf_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', pdf_sha256):
            raise ValueError('invalid_rendered_pdf_digest')
        with self._transaction() as connection:
            job, now = self._owned(connection, identity, lease_id)
            job.update(status='rendered_unverified', updated_epoch=now,
                       pdf_sha256=pdf_sha256, lease_id='', lease_until_epoch=0)
            self._write(connection, identity, job)
            return job

    def fail(self, identity, lease_id):
        with self._transaction() as connection:
            job, now = self._owned(connection, identity, lease_id)
            job.update(status='failed', updated_epoch=now, lease_id='', lease_until_epoch=0)
            self._write(connection, identity, job)
            return job
