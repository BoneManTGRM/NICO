import json
import logging
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from nico.review_pdf_admission_observability_v1 import AdmissionTrace, current_trace, phase, timed
from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard, CommitOutcomeUnknown


@pytest.fixture(autouse=True)
def synchronous_test_capture(monkeypatch):
    # Trace semantics independent of production's lossy bounded transport.
    from nico import review_pdf_admission_observability_v1 as obs
    monkeypatch.setattr(obs, '_offer', lambda encoded: obs._LOG.info('nico_pdf_admission_timing=%s', encoded))


def records(caplog):
    return [json.loads(record.args[0]) for record in caplog.records
            if record.msg == 'nico_pdf_admission_timing=%s']


def test_exact_phase_timing_privacy_and_bounded_output(caplog):
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    ticks = [100.]
    guard = DeadlineGuard(20, Event(), clock=lambda: ticks[0])
    trace = AdmissionTrace(guard)
    with trace.scope():
        with phase('policy'):
            ticks[0] += .25
        with phase('secret /private/path'):
            pass
        with phase('snapshot_read'):
            guard.call(lambda: timed('decode')(lambda: ticks.__setitem__(0, 101.))())
        guard.begin_commit()
        guard.end_commit()
    result, = records(caplog)
    assert result['phases']['policy']['elapsed_ms'] == 250
    assert result['phases']['decode']['elapsed_ms'] == 750
    assert result['deadline_remaining_ms'] == 19000
    assert result['phases']['decode']['remaining_ms_at_last_start'] == 19750
    assert result['commit_state'] == 'acknowledged'
    assert result['physical_calls_pending'] is False
    assert result['durable_job_outcome'] == 'not_established_by_timing'
    assert result['outcome'] == 'returned'
    assert 'secret' not in json.dumps(result) and '/private' not in json.dumps(result)
    assert len(json.dumps(result).encode()) < 4096
    assert current_trace() is None


@pytest.mark.parametrize('commit,ack', [(False,False),(True,False),(True,True)])
def test_exceptions_and_commit_uncertainty_are_not_job_absence(caplog, commit, ack):
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    guard = DeadlineGuard(20, Event())
    error = CommitOutcomeUnknown('password=private-do-not-log')
    with pytest.raises(CommitOutcomeUnknown) as caught:
        with AdmissionTrace(guard).scope():
            with phase('enqueue'):
                if commit: guard.begin_commit()
                if ack: guard.end_commit()
                raise error
    assert caught.value is error
    result, = records(caplog)
    assert result['commit_state'] == ('acknowledged' if ack else 'started_unacknowledged' if commit else 'not_started')
    assert result['outcome'] == 'raised'
    assert result['phases']['enqueue']['raised'] == 1
    assert result['durable_job_outcome'] == 'not_established_by_timing'
    assert 'password' not in caplog.text


def test_timeout_snapshot_retains_active_phase_and_late_completion_is_not_logged(caplog):
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    ticks, entered, release = [100.], Event(), Event()
    guard = DeadlineGuard(20, Event(), clock=lambda: ticks[0])
    errors = []
    def slow():
        with phase('record_restore_validation'):
            entered.set()
            assert release.wait(3)
    def caller():
        try:
            with AdmissionTrace(guard).scope():
                guard.call(slow)
        except RuntimeError as error:
            errors.append(error)
    thread = Thread(target=caller)
    thread.start()
    try:
        assert entered.wait(1)
        ticks[0] = 121.
        thread.join(1)
        assert not thread.is_alive() and errors
        result, = records(caplog)
        assert result['deadline_remaining_ms'] == 0
        assert result['physical_calls_pending'] is True
        assert result['phases']['record_restore_validation']['active'] == 1
        assert result['phases']['record_restore_validation']['active_span_ms'] == 21000
        assert result['phases']['record_restore_validation']['elapsed_ms'] == 0
    finally:
        release.set()
        thread.join(1)
        for worker in guard.threads: worker.join(1)
    assert guard.idle()
    assert len(records(caplog)) == 1  # Snapshot cannot be confused with late physical completion.


def test_no_trace_no_logging_and_logging_failure_preserves_result(monkeypatch, caplog):
    from nico import review_pdf_admission_observability_v1 as obs
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    assert timed('decode')(lambda: 4)() == 4
    assert records(caplog) == []
    guard = DeadlineGuard(20, Event())
    monkeypatch.setattr(obs._LOG, 'info', Mock(side_effect=OSError('private')))
    with AdmissionTrace(guard).scope():
        assert guard.call(lambda: 42) == 42
    error = ValueError('original')
    with pytest.raises(ValueError) as caught:
        with AdmissionTrace(guard).scope():
            raise error
    assert caught.value is error
    assert current_trace() is None


def test_simultaneous_traces_and_unrelated_thread_are_isolated(caplog):
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    from threading import Barrier
    barrier = Barrier(2)
    def caller(name):
        guard = DeadlineGuard(20, Event())
        with AdmissionTrace(guard).scope():
            def work():
                with phase(name): barrier.wait(timeout=2)
            guard.call(work)
    threads = [Thread(target=caller,args=(name,)) for name in ('decode','policy')]
    for thread in threads: thread.start()
    assert current_trace() is None
    for thread in threads:
        thread.join(3)
        assert not thread.is_alive()
    results = records(caplog)
    assert len(results) == 2
    assert len({r['trace_id'] for r in results}) == 2
    assert {tuple(r['phases']) for r in results} == {('decode',),('policy',)}


def test_all_allowlisted_phases_fit_log_bound_and_repetition_is_aggregated(caplog):
    from nico.review_pdf_admission_observability_v1 import _PHASES
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    guard = DeadlineGuard(20, Event())
    with AdmissionTrace(guard).scope():
        for _ in range(20):
            for name in _PHASES:
                with phase(name): pass
    result, = records(caplog)
    assert len(result['phases']) == len(_PHASES)
    assert all(p['calls'] == 20 for p in result['phases'].values())
    assert len(json.dumps(result).encode()) < 4096


def test_blocked_log_handler_cannot_block_admission_and_queue_is_bounded(monkeypatch):
    from nico import review_pdf_admission_observability_v1 as obs
    entered, release = Event(), Event()
    def handler(*args):
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(obs._LOG, 'info', handler)
    sink = obs._LogSink()
    monkeypatch.setattr(obs, '_offer', sink.offer)
    done = Event()
    def caller():
        with AdmissionTrace(DeadlineGuard(20, Event())).scope(): pass
        done.set()
    thread = Thread(target=caller)
    try:
        thread.start()
        assert entered.wait(1)
        assert done.wait(1)  # Logging handler remains blocked.
        for _ in range(50):
            with AdmissionTrace(DeadlineGuard(20, Event())).scope(): pass
        assert sink.queue.qsize() == 16
    finally:
        release.set()
        thread.join(1)
        sink.queue.join()


def test_real_snapshot_decode_history_and_integrity_phases_preserve_record(tmp_path, caplog):
    from tests.test_comprehensive_run_store import _store, _record
    store = _store(tmp_path)
    original = store.create(_record())
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    guard = DeadlineGuard(20, Event())
    with AdmissionTrace(guard).scope():
        restored = guard.call(store.load, original['identity']['run_id'])
    assert restored == original == store.load(original['identity']['run_id'])
    result, = records(caplog)
    assert set(result['phases']) == {'snapshot_read','snapshot_fetch','decode',
                                     'history_validation','record_restore_validation'}
    assert all(p['active'] == 0 and p['raised'] == 0 for p in result['phases'].values())
    assert result['commit_state'] == 'not_started'
    assert 'customer_acme' not in caplog.text and 'BoneManTGRM' not in caplog.text


def test_real_snapshot_failure_preserves_exception_and_hides_identifier(tmp_path, caplog):
    from tests.test_comprehensive_run_store import _store
    from nico.comprehensive_run_store import ComprehensiveRunNotFound
    store = _store(tmp_path)
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with pytest.raises(ComprehensiveRunNotFound):
        with AdmissionTrace(DeadlineGuard(20, Event())).scope():
            store.load('comprun_private_identifier')
    result, = records(caplog)
    assert result['phases']['snapshot_read']['raised'] == 1
    assert result['phases']['snapshot_fetch']['raised'] == 0
    assert 'private_identifier' not in caplog.text
    assert result['durable_job_outcome'] == 'not_established_by_timing'
