"""Synthetic lease expiry and persistence faults; no real report assessment."""
import sqlite3
import threading

import pytest

from test_comprehensive_final_report_watchdog_v1 import (
    _accelerate_watchdog, _context, _record, _store, _valid_result,
    _wait_for_complete, _wait_for_exhausted_failure,
)
import nico.comprehensive_final_report_background_v1 as background
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID


@pytest.mark.parametrize(('expiry_origin', 'fault_at'), [
    (origin, fault)
    for origin in ['watchdog', 'advance']
    for fault in ['before_rewind', 'after_rewind', 'before_claim', 'after_claim',
                  'concurrent_claim', 'competitor_after_failed_claim', 'expiry_commit_renderer_exit']
] + [('concurrent_advance', fault) for fault in ['after_rewind', 'after_claim']])
@pytest.mark.parametrize('second_outcome', ['complete', 'expire', 'cleanup'])
def test_watchdog_reconciles_recovery_persistence(tmp_path, monkeypatch, fault_at, second_outcome, expiry_origin):
    background.reset_final_report_publication_tasks_for_tests()
    _accelerate_watchdog(monkeypatch)
    store = _store(tmp_path)
    record = _record('comprun_recovery_persistence')
    run_id = record['identity']['run_id']
    store.create(record)
    coordinator = background.FinalReportPublicationCoordinator(store)
    started = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    fault_seen = threading.Event()
    recovery_read_retried = threading.Event()
    renderer_cleanup = threading.Event()
    supervisor_stopped_during_save = []
    advance_finished = threading.Event()
    watchdog_snapshot_loaded = threading.Event()
    expired = set()
    lock = threading.Lock()
    calls, faults, threads, leases = [], [], [], []
    real_deadline = background._job_deadline_state
    real_save = store.save
    real_load = store.load
    real_start = coordinator._start_worker
    real_recover = coordinator._recover_after_deadline
    real_release_capacity = background._release_local_task_capacity

    def controlled_deadline(job, *, now_epoch):
        observed = real_deadline(job, now_epoch=now_epoch)
        if observed['active'] and observed['phase'] == 'rendering':
            with lock:
                elapsed = observed['deadline_seconds'] + 1 if job['lease_id'] in expired else 0
            if (expiry_origin == 'advance' and not advance_finished.is_set()
                and threading.current_thread().name.startswith('nico-final-report-watchdog-')):
                elapsed = 0
            return real_deadline(job, now_epoch=observed['started_epoch'] + elapsed)
        return observed

    def save_with_fault(candidate, **kwargs):
        history = candidate.get('recovery_history') or []
        if (fault_at == 'expiry_commit_renderer_exit' and not history
            and candidate.get('terminal') is True):
            persisted = real_save(candidate, **kwargs)
            with background._LOCAL_TASKS_LOCK:
                first_state = background._LOCAL_TASKS[leases[0]]
            release[0].set()
            assert renderer_cleanup.wait(2)
            supervisor_stopped_during_save.append(first_state['watchdog_stop'].wait(0.2))
            return persisted
        rewind = len(history) == 1 and FINAL_REPORT_STAGE_ID not in candidate['stage_results']
        claim = len(history) == 1 and bool(background._marker_lease(candidate))
        inject = not faults and (claim if fault_at in {'before_claim', 'after_claim', 'competitor_after_failed_claim'} else rewind)
        if inject:
            faults.append(fault_at)
            if fault_at.startswith('after_') or fault_at == 'expiry_commit_renderer_exit':
                real_save(candidate, **kwargs)
            elif fault_at == 'concurrent_claim':
                saved = real_save(candidate, **kwargs)
                coordinator._claim_and_launch(saved, executor, _context(saved))
            elif fault_at == 'competitor_after_failed_claim':
                saved = real_load(run_id)
                coordinator._claim_and_launch(saved, executor, _context(saved))
            fault_seen.set()
            raise sqlite3.OperationalError('controlled recovery persistence fault')
        return real_save(candidate, **kwargs)

    def load_with_outage(run):
        if (second_outcome == 'cleanup' and fault_seen.is_set()
            and threading.current_thread().name.startswith('nico-final-report-watchdog-')):
            recovery_read_retried.set()
            raise sqlite3.OperationalError('controlled continuing recovery read outage')
        snapshot = real_load(run)
        if (expiry_origin == 'concurrent_advance' and not watchdog_snapshot_loaded.is_set()
            and threading.current_thread().name.startswith('nico-final-report-watchdog-')
            and background._marker_lease(snapshot)):
            # Hold the watchdog after its canonical read, before state_lock.
            # advance() must finish its after-commit failure before this stale
            # snapshot is returned to the watchdog.
            watchdog_snapshot_loaded.set()
            assert advance_finished.wait(5)
        return snapshot

    def track_cleanup(state):
        if threading.current_thread().name.startswith('nico-final-report-publication-'):
            renderer_cleanup.set()
        real_release_capacity(state)

    def recover_after_origin(*args, **kwargs):
        if (expiry_origin == 'advance'
            and threading.current_thread().name.startswith('nico-final-report-watchdog-')):
            assert advance_finished.wait(5)
        return real_recover(*args, **kwargs)

    def track_start(**kwargs):
        real_start(**kwargs)
        with background._LOCAL_TASKS_LOCK:
            state = background._LOCAL_TASKS[kwargs['lease_id']]
            threads.extend(value for value in state.values() if isinstance(value, threading.Thread))
        leases.append(kwargs['lease_id'])

    def executor(context):
        with lock:
            index = len(calls)
            calls.append(context)
        assert index < 2, 'persistence retry must not create a third rendering attempt'
        started[index].set()
        assert release[index].wait(10), 'test must release each synthetic renderer'
        return _valid_result(context, suffix=f'attempt{index}')

    monkeypatch.setattr(background, '_job_deadline_state', controlled_deadline)
    monkeypatch.setattr(store, 'save', save_with_fault)
    monkeypatch.setattr(store, 'load', load_with_outage)
    monkeypatch.setattr(background, '_release_local_task_capacity', track_cleanup)
    monkeypatch.setattr(coordinator, '_start_worker', track_start)
    monkeypatch.setattr(coordinator, '_recover_after_deadline', recover_after_origin)
    try:
        claimed = coordinator.advance(record, executor, _context(record))
        assert started[0].wait(1)
        first = background._marker_lease(claimed)
        with lock:
            expired.add(first)
        if expiry_origin in {'advance', 'concurrent_advance'}:
            if expiry_origin == 'concurrent_advance':
                assert watchdog_snapshot_loaded.wait(1.5), 'watchdog must read before advance enters'
            try:
                with pytest.raises(sqlite3.OperationalError, match='controlled recovery persistence fault'):
                    coordinator.advance(claimed, executor, _context(claimed))
            finally:
                advance_finished.set()
        assert fault_seen.wait(1.5), 'fault must occur after controlled expiry'
        assert store.load_final_report_job(first)['status'] == 'expired'
        if fault_at == 'expiry_commit_renderer_exit':
            assert supervisor_stopped_during_save == [False]
        # The old renderer exits while recovery is pending; it cannot terminate
        # recovery supervision or publish its late result.
        release[0].set()
        if second_outcome == 'cleanup':
            assert recovery_read_retried.wait(1.5), 'supervision must survive the post-fence failure'
            background.reset_final_report_publication_tasks_for_tests()
            release[1].set()
            for worker in threads:
                worker.join(timeout=2)
            assert not any(worker.is_alive() for worker in threads)
            assert len(calls) == (2 if fault_at in {'concurrent_claim', 'competitor_after_failed_claim'} else 1)
            with background._LOCAL_TASKS_LOCK:
                assert not any(lease in background._LOCAL_TASKS for lease in leases)
            assert background._PUBLICATION_SLOT.acquire(blocking=False)
            background._PUBLICATION_SLOT.release()
            return
        assert started[1].wait(1.5), 'watchdog abandoned post-expiry recovery'
        current = store.load(run_id)
        second = background._marker_lease(current)
        assert second and second != first
        assert len(current['recovery_history']) == 1
        if second_outcome == 'expire':
            with lock:
                expired.add(second)
            terminal = _wait_for_exhausted_failure(store, run_id)
            assert store.load_final_report_job(second)['status'] == 'expired'
            release[1].set()
        else:
            release[1].set()
            terminal = _wait_for_complete(store, run_id)
            assert terminal['stage_results'][FINAL_REPORT_STAGE_ID]['report_package']['report_id'].endswith('attempt1')
        for worker in threads:
            worker.join(timeout=2)
        assert not any(worker.is_alive() for worker in threads)
        persisted = store.load(run_id)
        assert persisted == terminal, 'late render results must not change canonical state'
        assert len(calls) == 2 and faults == [fault_at]
        with store._connection() as connection:
            jobs = connection.execute(
                'SELECT lease_id,status FROM nico_comprehensive_final_report_jobs WHERE run_id=?',
                (run_id,),
            ).fetchall()
        if fault_at == 'competitor_after_failed_claim':
            assert len(jobs) == 3
            assert sum(status == 'superseded' for _, status in jobs) == 1
        else:
            assert len(jobs) == 2, 'reconciliation must reuse the pending claim, not leak queued jobs'
        assert all(status in {'complete', 'expired', 'superseded'} for _, status in jobs)
        assert len(persisted['recovery_history']) == 1
        assert persisted['identity'] == record['identity']
        for stage in record['completed_stages']:
            assert persisted['stage_results'][stage] == record['stage_results'][stage]
        assert persisted['human_review_required'] is True
        assert persisted['client_delivery_allowed'] is False
        with background._LOCAL_TASKS_LOCK:
            assert not any(lease in background._LOCAL_TASKS for lease in leases)
        assert background._PUBLICATION_SLOT.acquire(blocking=False)
        background._PUBLICATION_SLOT.release()
    finally:
        advance_finished.set()
        for event in release:
            event.set()
        background.reset_final_report_publication_tasks_for_tests()
        for worker in threads:
            worker.join(timeout=2)
