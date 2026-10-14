"""Dormant synchronous coordinator seam. No scheduler, routes or startup wiring."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from threading import Event

from nico.review_pdf_preparation_jobs_v1 import PreparationConflict, PostgresReviewPdfPreparationJobs
from nico.review_pdf_preparation_worker_v1 import run_worker, validate_result


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class CapturedSource:
    status: dict
    storage_sha256: str


class RetainedSourceAuthority:
    """Use the existing full record restoration/projection, never continuation.

    The source store and ledger MUST target the same database. Publication checks
    the canonical row through the ledger connection and locks it until commit.
    No missing review-history commitment is initialized by this reader.
    """
    def __init__(self, store, controller, policy):
        self.store, self.controller, self.policy = store, controller, policy

    def check_policy(self, identity):
        if self.policy() != (identity.renderer_revision, identity.policy_sha256):
            raise PreparationConflict('preparation_policy_changed')

    def capture(self, identity):
        self.check_policy(identity)
        def consume(row, restore):
            if row[1] is None or row[2] is None:
                raise PreparationConflict('preparation_review_commitment_required')
            record = restore()  # Includes existing integrity/history validation.
            status = self.controller._status_artifact_from_record(record)
            expected = dict(run_id=identity.run_id, customer_id=identity.customer_id,
                project_id=identity.project_id, repository=identity.repository,
                commit_sha=identity.commit_sha)
            if (any(record['identity'].get(k) != v for k, v in expected.items())
                    or record.get('revision') != identity.source_revision
                    or record.get('integrity_sha256') != identity.source_integrity_sha256
                    or record.get('terminal') is not True):
                raise PreparationConflict('preparation_source_changed')
            reports = status.get('reports') or {}
            if (reports.get('canonical_truth_sha256') != identity.canonical_truth_sha256
                    or reports.get('pdf_sha256') != identity.source_artifact_sha256):
                raise PreparationConflict('preparation_source_artifact_changed')
            return CapturedSource(status, _fingerprint([row[0], row[1], row[2]]))
        return self.store._consume_read_snapshot(identity.run_id, consume)

    def lock_and_recheck(self, connection, identity, *, postgres, storage_sha256):
        self.check_policy(identity)
        p = '%s' if postgres else '?'
        row = connection.execute(
            'SELECT runs.customer_id, runs.project_id, runs.repository, runs.commit_sha, '
            'runs.revision, runs.integrity_sha256, runs.terminal, runs.payload, '
            'commitments.event_count, commitments.chain_sha256 '
            'FROM nico_comprehensive_runs AS runs '
            'JOIN nico_comprehensive_review_history_commitments AS commitments '
            'ON commitments.run_id=runs.run_id '
            f'WHERE runs.run_id={p}' + (' FOR SHARE OF runs, commitments' if postgres else ''),
            (identity.run_id,),
        ).fetchone()
        expected = dict(customer_id=identity.customer_id, project_id=identity.project_id,
            repository=identity.repository, commit_sha=identity.commit_sha,
            revision=identity.source_revision, integrity_sha256=identity.source_integrity_sha256)
        if row is None or any(row[k] != v for k, v in expected.items()) or not row['terminal']:
            raise PreparationConflict('preparation_source_changed')
        self.check_policy(identity)
        if _fingerprint([row['payload'], row['event_count'], row['chain_sha256']]) != storage_sha256:
            raise PreparationConflict('preparation_source_snapshot_changed')


class ReviewPdfPreparationService:
    def __init__(self, jobs, source, *, capacity, worker=run_worker):
        # The caller supplies the existing configured capacity, never a new pool.
        self.jobs, self.source, self.capacity, self.worker = jobs, source, capacity, worker

    def run_once(self, identity, *, stop=None):
        stop = stop if stop is not None else Event()
        if not self.capacity.acquire(blocking=False):
            return None
        lease = None
        state = {'physical_worker_exit_confirmed': True}
        try:
            if stop.is_set():
                return None
            lease = self.jobs.claim(identity)
            if lease is None:
                return None
            captured = self.source.capture(identity)
            status = captured.status
            before = _fingerprint(status)
            result = self.worker(status, identity, stop=stop,
                heartbeat=lambda **kwargs: self.jobs.heartbeat(identity, lease['lease_id'], **kwargs), state=state,
                max_seconds=min(900, lease['deadline_epoch'] - lease['updated_epoch']))
            if not state.get('physical_worker_exit_confirmed') or stop.is_set():
                raise PreparationConflict('preparation_worker_not_finished')
            if _fingerprint(status) != before:
                raise PreparationConflict('preparation_input_mutated')
            pdf, digest = validate_result(result, identity, parse_pdf=False)
            # Full authoritative restoration after rendering, before row lock/CAS.
            refreshed = self.source.capture(identity)
            if (_fingerprint(refreshed.status) != before
                    or refreshed.storage_sha256 != captured.storage_sha256):
                raise PreparationConflict('preparation_source_changed')
            with self.jobs._transaction(identity) as connection:
                self.source.lock_and_recheck(connection, identity,
                    postgres=isinstance(self.jobs, PostgresReviewPdfPreparationJobs),
                    storage_sha256=captured.storage_sha256)
                job, now = self.jobs._owned(connection, identity, lease['lease_id'])
                if stop.is_set():
                    raise PreparationConflict('preparation_cancelled')
                # Bytes and metadata become visible together in one existing row.
                # Ready is review-artifact availability, NEVER delivery approval.
                job.update(status='ready', updated_epoch=now, lease_id='', lease_until_epoch=0,
                    pdf_sha256=digest, pdf_base64=base64.b64encode(pdf).decode('ascii'),
                    result_owner=lease['lease_id'], source_snapshot_sha256=before,
                    source_storage_sha256=captured.storage_sha256,
                    validated_page_count=result['validated_page_count'],
                    result_headers=dict(result['headers']), human_review_required=True,
                    client_delivery_allowed=False)
                self.jobs._write(connection, identity, job)
            return job
        except BaseException:
            if lease is not None:
                try:
                    self.jobs.fail(identity, lease['lease_id'])
                except PreparationConflict:
                    pass  # A superseded owner must not change its successor.
            raise
        finally:
            # Unconfirmed physical exit quarantines capacity instead of overbooking.
            if state.get('physical_worker_exit_confirmed'):
                self.capacity.release()
