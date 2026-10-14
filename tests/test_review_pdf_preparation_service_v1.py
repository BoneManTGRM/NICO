"""Synthetic seam tests; no real PostgreSQL or private retained-report rerun."""
import base64
from copy import deepcopy
from dataclasses import asdict
import hashlib
import io
from threading import BoundedSemaphore, Event
from unittest.mock import Mock

import pytest
from pypdf import PdfWriter

from tests.test_review_pdf_preparation_jobs_v1 import identity
from nico.durable_runtime_storage import SQLiteRuntimeAdapter
from nico.review_pdf_preparation_jobs_v1 import ReviewPdfPreparationJobs, PreparationConflict
from nico.review_pdf_preparation_service_v1 import ReviewPdfPreparationService, RetainedSourceAuthority, CapturedSource
from nico import review_pdf_preparation_worker_v1 as worker_module


def artifact():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = io.BytesIO()
    writer.write(stream)
    data = stream.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    i = identity()
    return dict(validated_page_count=1, pdf_base64=base64.b64encode(data).decode(), identity=asdict(i), headers={
        'x-nico-run-id': i.run_id, 'x-nico-commit-sha': i.commit_sha,
        'x-nico-report-language': i.language, 'x-nico-canonical-truth-sha256': i.canonical_truth_sha256,
        'x-nico-assessment-rerun': 'false', 'x-nico-approval-status': 'pending_human_approval',
        'x-nico-delivery-status': 'blocked_pending_human_approval',
        'x-nico-client-delivery-allowed': 'false', 'x-nico-pdf-sha256': sha,
        'x-nico-artifact-sha256': sha})


@pytest.fixture
def seam(tmp_path, monkeypatch):
    jobs = ReviewPdfPreparationJobs(SQLiteRuntimeAdapter(tmp_path / 'existing.sqlite'))
    clock = [1000.]
    monkeypatch.setattr(jobs, '_now', lambda con: clock[0])
    status = {'scores': [92, 88], 'findings': ['all original findings'],
              'approval_status': 'pending_human_approval', 'client_delivery_allowed': False}
    source = Mock()
    source.capture.side_effect = lambda i: CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.lock_and_recheck.return_value = None
    capacity = BoundedSemaphore(1)
    worker = Mock(return_value=artifact())
    service = ReviewPdfPreparationService(jobs, source, capacity=capacity, worker=worker)
    jobs.enqueue(identity(), preparation_authorized=True)
    return service, jobs, source, capacity, worker, clock, status


def test_success_atomic_ready_duplicate_and_approval_preserved(seam):
    service, jobs, source, capacity, worker, clock, status = seam
    before = deepcopy(status)
    result = service.run_once(identity())
    assert result == jobs.get(identity())
    assert result['status'] == 'ready'
    assert result['result_owner']
    assert result['client_delivery_allowed'] is False
    assert result['human_review_required'] is True
    assert hashlib.sha256(base64.b64decode(result['pdf_base64'])).hexdigest() == result['pdf_sha256']
    assert status == before
    assert source.capture.call_count == 2
    source.lock_and_recheck.assert_called_once()
    assert service.run_once(identity()) is None
    worker.assert_called_once()
    assert capacity.acquire(blocking=False)


@pytest.mark.parametrize('problem', ['builder', 'malformed', 'checksum', 'identity', 'approval', 'source', 'locked_source', 'expired', 'cancel', 'mutation'])
def test_failed_results_never_ready(seam, problem):
    service, jobs, source, capacity, worker, clock, status = seam
    stop = Event()
    def run(snapshot, i, **kwargs):
        if problem == 'builder':
            raise ValueError('synthetic builder error')
        result = artifact()
        if problem == 'malformed':
            result['validated_page_count'] = 0
            result['pdf_base64'] = base64.b64encode(b'%PDF broken').decode()
            sha = hashlib.sha256(b'%PDF broken').hexdigest()
            result['headers'].update({'x-nico-pdf-sha256': sha, 'x-nico-artifact-sha256': sha})
        if problem == 'checksum':
            result['headers']['x-nico-pdf-sha256'] = '0' * 64
        if problem == 'identity':
            result['identity']['source_revision'] = 67
        if problem == 'approval':
            result['headers']['x-nico-client-delivery-allowed'] = 'true'
        if problem == 'source':
            status['scores'] = [100, 100]
        if problem == 'locked_source':
            source.lock_and_recheck.side_effect = PreparationConflict('changed under lock')
        if problem == 'expired':
            clock[0] += 31
        if problem == 'cancel':
            stop.set()
        if problem == 'mutation':
            snapshot['scores'] = [100, 100]
        return result
    worker.side_effect = run
    with pytest.raises(Exception):
        service.run_once(identity(), stop=stop)
    assert jobs.get(identity())['status'] != 'ready'
    assert 'pdf_base64' not in jobs.get(identity())
    assert capacity.acquire(blocking=False)


def test_capacity_and_cancellation_do_not_claim(seam):
    service, jobs, source, capacity, worker, clock, status = seam
    capacity.acquire()
    assert service.run_once(identity()) is None
    assert jobs.get(identity())['attempts'] == 0
    capacity.release()
    stop = Event(); stop.set()
    assert service.run_once(identity(), stop=stop) is None
    assert jobs.get(identity())['attempts'] == 0
    worker.assert_not_called()


def test_unconfirmed_exit_quarantines_capacity(seam):
    service, jobs, source, capacity, worker, clock, status = seam
    def run(*args, **kwargs):
        kwargs['state']['physical_worker_exit_confirmed'] = False
        raise RuntimeError('termination unconfirmed')
    worker.side_effect = run
    with pytest.raises(RuntimeError):
        service.run_once(identity())
    assert not capacity.acquire(blocking=False)


def test_late_owner_cannot_overwrite_reclaimed_job(seam):
    service, jobs, source, capacity, worker, clock, status = seam
    newer = []
    def run(*args, **kwargs):
        clock[0] += 31
        newer.append(jobs.claim(identity()))
        return artifact()
    worker.side_effect = run
    with pytest.raises(PreparationConflict):
        service.run_once(identity())
    assert jobs.get(identity())['lease_id'] == newer[0]['lease_id']
    assert jobs.get(identity())['status'] == 'rendering'


def test_missing_commitment_never_calls_restore():
    store, controller = Mock(), Mock()
    restore = Mock(side_effect=AssertionError('must not initialize'))
    store._consume_read_snapshot.side_effect = lambda run, consume: consume([None, None, None], restore)
    authority = RetainedSourceAuthority(store, controller, lambda: ('e' * 40, 'f' * 64))
    with pytest.raises(PreparationConflict):
        authority.capture(identity())
    restore.assert_not_called()


def test_policy_change_blocks_source_capture():
    store = Mock()
    authority = RetainedSourceAuthority(store, Mock(), lambda: ('0' * 40, 'f' * 64))
    with pytest.raises(PreparationConflict):
        authority.capture(identity())
    store._consume_read_snapshot.assert_not_called()


def test_subprocess_cleanup_and_database_environment(monkeypatch):
    paths = []
    class Process:
        pid = 12345
        returncode = 0
        def poll(self): return 0
    def spawn(command, **kwargs):
        from pathlib import Path
        root = Path(command[-1]); paths.append(root)
        assert not any(key.startswith('PG') for key in kwargs['env'])
        assert 'DATABASE_URL' not in kwargs['env']
        assert kwargs['env']['NICO_ENABLE_SQLITE_DURABLE_STORAGE'] == 'false'
        assert kwargs['env']['NICO_DISABLE_POSTGRES'] == 'true'
        worker_module._atomic_json(root / 'output.json', artifact())
        return Process()
    monkeypatch.setenv('DATABASE_URL', 'synthetic-not-a-connection')
    monkeypatch.setenv('PGHOST', 'synthetic')
    monkeypatch.setattr(worker_module.subprocess, 'Popen', spawn)
    terminate = Mock(return_value=True)
    monkeypatch.setattr(worker_module, 'terminate_process', terminate)
    state = {}
    result = worker_module.run_worker({}, identity(), stop=Event(), heartbeat=Mock(), state=state, max_seconds=10)
    assert result == artifact()
    assert state['physical_worker_exit_confirmed']
    assert not paths[0].exists()
    terminate.assert_called_once()


@pytest.mark.parametrize('change', ['payload', 'commitment', 'revision', 'policy'])
def test_locked_source_checks_exact_payload_commitment_and_policy(change):
    from nico.review_pdf_preparation_service_v1 import _fingerprint
    i = identity()
    row = dict(customer_id=i.customer_id, project_id=i.project_id, repository=i.repository,
        commit_sha=i.commit_sha, revision=i.source_revision, integrity_sha256=i.source_integrity_sha256,
        terminal=True, payload={'full': 'canonical payload'}, event_count=1, chain_sha256='chain')
    binding = _fingerprint([row['payload'], row['event_count'], row['chain_sha256']])
    policy = lambda: (i.renderer_revision, i.policy_sha256)
    authority = RetainedSourceAuthority(Mock(), Mock(), policy)
    con = Mock(); con.execute.return_value.fetchone.return_value = row
    authority.lock_and_recheck(con, i, postgres=True, storage_sha256=binding)
    assert 'FOR SHARE OF runs, commitments' in con.execute.call_args.args[0]
    if change == 'payload': row['payload']['full'] = 'changed without metadata update'
    if change == 'commitment': row['chain_sha256'] = 'different chain'
    if change == 'revision': row['revision'] += 1
    if change == 'policy': authority.policy = lambda: ('0' * 40, 'f' * 64)
    with pytest.raises(PreparationConflict):
        authority.lock_and_recheck(con, i, postgres=True, storage_sha256=binding)


@pytest.mark.parametrize('problem', ['cancel', 'heartbeat', 'builder'])
def test_worker_cleanup_on_cancel_lease_error_and_builder_exit(monkeypatch, problem):
    paths = []
    class Process:
        pid = 12345
        returncode = 1 if problem == 'builder' else None
        def poll(self): return self.returncode
    def spawn(command, **kwargs):
        from pathlib import Path
        paths.append(Path(command[-1]))
        return Process()
    monkeypatch.setattr(worker_module.subprocess, 'Popen', spawn)
    terminated = Mock(return_value=True)
    monkeypatch.setattr(worker_module, 'terminate_process', terminated)
    stop = Event()
    def heartbeat():
        if problem == 'heartbeat': raise PreparationConflict('lease expired')
        stop.set()
    state = {}
    with pytest.raises((RuntimeError, PreparationConflict)):
        worker_module.run_worker({}, identity(), stop=stop, heartbeat=heartbeat, state=state, max_seconds=1)
    terminated.assert_called_once()
    assert not paths[0].exists()
    assert state['physical_worker_exit_confirmed'] is True


def test_complete_child_bootstrap_is_connection_free_before_rejecting_invalid_snapshot():
    import os
    import subprocess
    import sys
    script = '''
import sqlite3, psycopg, socket
attempts = []
def deny(*args, **kwargs):
    attempts.append('connection')
    raise AssertionError('connection attempted')
sqlite3.connect = psycopg.connect = socket.create_connection = deny
from nico.review_pdf_preparation_worker_v1 import child_build
try:
    child_build({'status': {}, 'language': 'es-MX', 'identity': {}})
except ValueError as exc:
    assert str(exc) == 'terminal_report_required', str(exc)
else:
    raise AssertionError('invalid source accepted')
from nico import review_pdf_preparation_worker_v1 as worker
assert worker._CONNECTION_ATTEMPTS == 0
assert attempts == [], attempts
'''
    # No app lifespan, real source, assessment or database configuration.
    env = {'PATH': os.environ['PATH'], 'NICO_DISABLE_POSTGRES': 'true',
        'NICO_ENABLE_SQLITE_DURABLE_STORAGE': 'false',
        'NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE': 'false'}
    result = subprocess.run([sys.executable, '-c', script], env=env,
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-2000:]


def test_real_isolated_worker_renders_complete_synthetic_locale(monkeypatch):
    from dataclasses import replace
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    status = _fixed_status('en')
    canonical = status['reports']['json']
    i = replace(identity(), run_id=status['run_id'], repository=status['repository'],
        commit_sha=status['commit_sha'], customer_id=canonical['identity']['customer_id'],
        project_id=canonical['identity']['project_id'],
        canonical_truth_sha256=status['reports']['canonical_truth_sha256'],
        source_artifact_sha256=status['reports']['pdf_sha256'])
    before = deepcopy(status)
    state = {}
    heartbeat = Mock()
    result = worker_module.run_worker(status, i, stop=Event(), heartbeat=heartbeat,
                                     state=state, max_seconds=60)
    pdf, digest = worker_module.validate_result(result, i)
    assert pdf.startswith(b'%PDF') and digest
    from nico.comprehensive_same_run_locale_report_v1 import build_same_run_locale_pdf_response
    baseline = build_same_run_locale_pdf_response(deepcopy(status), i.language)
    assert hashlib.sha256(baseline.body).hexdigest() == digest
    assert status == before
    assert state['physical_worker_exit_confirmed'] is True
    assert result['headers']['x-nico-client-delivery-allowed'] == 'false'


def test_cleanup_exception_never_confirms_exit(monkeypatch):
    class Process:
        pid = 12345
        returncode = 1
        def poll(self): return 1
    monkeypatch.setattr(worker_module.subprocess, 'Popen', lambda *a, **kw: Process())
    monkeypatch.setattr(worker_module, 'terminate_process', Mock(side_effect=OSError('synthetic kill failure')))
    state = {'physical_worker_exit_confirmed': True}
    with pytest.raises(OSError):
        worker_module.run_worker({}, identity(), stop=Event(), heartbeat=Mock(), state=state, max_seconds=1)
    assert state['physical_worker_exit_confirmed'] is False


def test_parent_validation_does_not_parse_pdf(monkeypatch):
    import pypdf
    monkeypatch.setattr(pypdf, 'PdfReader', Mock(side_effect=AssertionError('unbounded parent parsing')))
    worker_module.validate_result(artifact(), identity(), parse_pdf=False)


def test_full_validator_rejects_malformed_pdf():
    result = artifact()
    data = b'%PDF malformed'
    result['pdf_base64'] = base64.b64encode(data).decode()
    sha = hashlib.sha256(data).hexdigest()
    result['headers'].update({'x-nico-pdf-sha256': sha, 'x-nico-artifact-sha256': sha})
    with pytest.raises(Exception):
        worker_module.validate_result(result, identity())


def test_worker_wall_deadline_terminates_before_result(monkeypatch):
    class Process:
        pid = 12345
        returncode = None
        def poll(self): return None
    monkeypatch.setattr(worker_module.subprocess, 'Popen', lambda *a, **kw: Process())
    terminated = Mock(return_value=True)
    monkeypatch.setattr(worker_module, 'terminate_process', terminated)
    from types import SimpleNamespace
    ticks = [100.]
    monkeypatch.setattr(worker_module, 'time', SimpleNamespace(monotonic=lambda: ticks[0]))
    def spawn(*args, **kwargs):
        ticks[0] = 102.
        return Process()
    monkeypatch.setattr(worker_module.subprocess, 'Popen', spawn)
    state = {}
    with pytest.raises(RuntimeError, match='cancelled_or_expired'):
        worker_module.run_worker({}, identity(), stop=Event(), heartbeat=Mock(), state=state, max_seconds=1)
    terminated.assert_called_once()
    assert state['physical_worker_exit_confirmed'] is True


def test_worker_reports_child_verification_without_publishing_ready(monkeypatch):
    class Process:
        pid = 12345
        returncode = 0
        polls = 0
        def poll(self):
            self.polls += 1
            return None if self.polls == 1 else 0
    def spawn(command, **kwargs):
        from pathlib import Path
        root = Path(command[-1])
        worker_module._atomic_json(root / 'phase.json', {'phase':'verifying'})
        worker_module._atomic_json(root / 'output.json', artifact())
        return Process()
    monkeypatch.setattr(worker_module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(worker_module, 'terminate_process', Mock(return_value=True))
    heartbeat = Mock()
    worker_module.run_worker({}, identity(), stop=Event(), heartbeat=heartbeat, state={}, max_seconds=10)
    heartbeat.assert_called_once_with(phase='verifying')
