"""Synthetic isolated recovery faults; no production renderer or service polling."""
import sqlite3
from types import SimpleNamespace

import pytest

from nico import comprehensive_final_report_background_v1 as background
from nico import comprehensive_final_report_process_isolation_v1 as isolation
from test_comprehensive_final_report_watchdog_v1 import _context, _record, _store


@pytest.mark.parametrize('fault_at', ['before_rewind', 'after_rewind', 'before_claim', 'after_claim'])
def test_local_deadline_retains_recovery_phase(tmp_path, monkeypatch, fault_at):
    store = _store(tmp_path)
    record = _record('comprun_isolated_recovery')
    store.create(record)
    coordinator = background.FinalReportPublicationCoordinator(store)
    launched = []
    monkeypatch.setattr(coordinator, '_start_worker', lambda **kwargs: launched.append(kwargs['lease_id']))
    monkeypatch.setattr(isolation, 'time', SimpleNamespace(time=isolation.time.time, sleep=lambda _: None))
    context = _context(record)
    claimed = coordinator.advance(record, lambda _: None, context)
    first = background._marker_lease(claimed)
    real_save = store.save
    faults = []

    def save_with_fault(candidate, **kwargs):
        history = candidate.get('recovery_history') or []
        claim = bool(background._marker_lease(candidate))
        target = claim if fault_at.endswith('claim') else not claim
        if len(history) == 1 and target and not faults:
            faults.append(fault_at)
            if fault_at.startswith('after_'):
                real_save(candidate, **kwargs)
            raise sqlite3.OperationalError('controlled isolated recovery persistence fault')
        return real_save(candidate, **kwargs)

    monkeypatch.setattr(store, 'save', save_with_fault)
    outcome = isolation._publish_local_deadline_and_recover(
        coordinator, lease_id=first, executor=lambda _: None, context=context,
        state={'worker_terminated': True, 'physical_worker_exit_confirmed': True},
        render_started_epoch=1.0,
    )
    current = store.load(context['run_id'])
    assert faults == [fault_at]
    assert len(launched) == 2, 'timeout recovery must launch without service polling'
    assert background._marker_lease(current) == launched[1] != first
    assert outcome == 'expired'
    assert len(current['recovery_history']) == 1
    assert current['identity'] == record['identity']
    assert current['human_review_required'] is True
    assert current['client_delivery_allowed'] is False
    assert store.load_final_report_job(first)['status'] == 'blocked'


@pytest.mark.parametrize(('origin', 'fault_at'), [
    (origin, fault)
    for origin in ['local', 'watchdog', 'watchdog_local_race']
    for fault in ['before_publication', 'after_publication', 'before_rewind', 'after_rewind',
                  'before_claim', 'after_claim', 'read', 'burst', 'termination', 'cleanup']
] + [(origin, fault) for origin in ['advance', 'concurrent_advance']
     for fault in ['before_rewind', 'after_rewind', 'before_claim', 'after_claim']]
  + [('watchdog_local_before_save', fault)
     for fault in ['before_publication', 'before_fallback', 'after_fallback']])
def test_isolated_supervisor_retries_after_renderer_exit(tmp_path, monkeypatch, origin, fault_at):
    import threading
    from test_comprehensive_final_report_watchdog_v1 import _valid_result

    background.reset_final_report_publication_tasks_for_tests()
    store = _store(tmp_path)
    record = _record('comprun_isolated_supervision')
    store.create(record)
    context = _context(record)
    coordinator = background.FinalReportPublicationCoordinator(store)
    started = threading.Event()
    replacement = threading.Event()
    child_gone = threading.Event()
    fault_seen = threading.Event()
    permit_exit = threading.Event()
    watchdog_loaded = threading.Event()
    advance_finished = threading.Event()
    local_expiry = threading.Event()
    states, launched, faults = [], [], []
    real_save, real_load = store.save, store.load
    real_deadline = background._job_deadline_state
    monkeypatch.setattr(background, '_heartbeat_seconds', lambda: 0.02)
    monkeypatch.setattr(isolation, '_production_final_report_executor', lambda _: True)
    monkeypatch.setattr(isolation, '_enabled', lambda: True)
    monkeypatch.setattr(isolation, '_LOCAL_DEADLINE_PERSIST_RETRIES', 2)
    monkeypatch.setattr(isolation, 'time', SimpleNamespace(time=isolation.time.time, sleep=lambda _: None))

    def render(_context, *, stop, state, **kwargs):
        states.append(state)
        started.set()
        if origin == 'watchdog_local_before_save':
            assert local_expiry.wait(5), 'test must trigger independent local expiry'
            state['local_render_deadline_expired'] = True
            state['deadline_expired'] = True
            state['worker_terminated'] = True
        elif origin != 'local':
            assert stop.wait(5), 'watchdog must fence the synthetic renderer'
            if origin == 'watchdog_local_race':
                state['local_render_deadline_expired'] = True
        else:
            state['local_render_deadline_expired'] = True
            state['worker_terminated'] = True
        child_gone.set()
        raise isolation.IsolatedFinalReportCancelled('synthetic renderer stopped')

    def start(**kwargs):
        launched.append(kwargs['lease_id'])
        if len(launched) == 1:
            isolation._isolated_start_worker(coordinator, **kwargs)
        else:
            assert len(launched) == 2
            assert child_gone.is_set(), 'replacement must wait for physical exit'
            replacement.set()

    def terminate(state):
        if fault_at == 'termination' and not permit_exit.is_set():
            fault_seen.set()
            return False
        return True

    def deadline(job, *, now_epoch):
        observed = real_deadline(job, now_epoch=now_epoch)
        if (origin == 'advance' and not advance_finished.is_set()
            and threading.current_thread().name.startswith('nico-final-report-watchdog-')):
            return observed
        if origin != 'local' and started.is_set() and observed['active']:
            return real_deadline(job, now_epoch=observed['started_epoch'] + observed['deadline_seconds'] + 1)
        return observed

    def save(candidate, **kwargs):
        history = candidate.get('recovery_history') or []
        phase = ('publication' if candidate.get('terminal') is True and not history
                 else 'claim' if history and background._marker_lease(candidate)
                 else 'rewind' if history else '')
        fallback_fault = fault_at.endswith('fallback')
        limit = 2 if fallback_fault else 100000 if fault_at == 'cleanup' else 3 if fault_at == 'burst' else 1
        target = 'publication' if fallback_fault else 'rewind' if fault_at in {'burst', 'cleanup'} else fault_at.split('_')[-1]
        if phase == target and len(faults) < limit:
            faults.append(fault_at)
            if origin == 'watchdog_local_before_save':
                local_expiry.set()
                states[0]['invoke_thread'].join(timeout=2)
                assert not states[0]['invoke_thread'].is_alive()
                assert store.load_final_report_job(launched[0])['status'] == 'expired'
                assert background._marker_lease(real_load(context['run_id'])) == launched[0]
            if fault_at.startswith('after_') and (not fallback_fault or len(faults) == 2):
                real_save(candidate, **kwargs)
            fault_seen.set()
            raise sqlite3.OperationalError('synthetic isolated save outage')
        return real_save(candidate, **kwargs)

    def load(run_id):
        current = real_load(run_id)
        if (origin == 'concurrent_advance' and not watchdog_loaded.is_set()
            and threading.current_thread().name.startswith('nico-final-report-watchdog-')
            and background._marker_lease(current)):
            watchdog_loaded.set()
            assert advance_finished.wait(5), 'request must finish before returning stale snapshot'
        if fault_at == 'read' and current.get('terminal') is True and not faults:
            faults.append(fault_at)
            fault_seen.set()
            raise sqlite3.OperationalError('synthetic isolated read outage')
        return current

    monkeypatch.setattr(isolation, '_terminate_state_process', terminate)
    monkeypatch.setattr(isolation, 'run_isolated_final_report', render)
    monkeypatch.setattr(coordinator, '_start_worker', start)
    monkeypatch.setattr(coordinator, '_stop_local_task', lambda lease: isolation._isolated_stop_local_task(coordinator, lease))
    monkeypatch.setattr(background, '_job_deadline_state', deadline)
    monkeypatch.setattr(store, 'save', save)
    monkeypatch.setattr(store, 'load', load)
    try:
        claimed = coordinator.advance(record, lambda _: None, context)
        assert started.wait(1)
        if origin in {'advance', 'concurrent_advance'}:
            if origin == 'concurrent_advance':
                assert watchdog_loaded.wait(1), 'watchdog must read before request expiry'
            try:
                with pytest.raises(sqlite3.OperationalError, match='synthetic isolated save outage'):
                    coordinator.advance(claimed, lambda _: None, context)
            finally:
                advance_finished.set()
        assert fault_seen.wait(1)
        if fault_at == 'cleanup':
            background.reset_final_report_publication_tasks_for_tests()
            for key in ['invoke_thread', 'watchdog_thread', 'heartbeat_thread']:
                states[0][key].join(timeout=2)
                assert not states[0][key].is_alive()
            assert not replacement.is_set() and len(launched) == 1
            with background._LOCAL_TASKS_LOCK:
                assert launched[0] not in background._LOCAL_TASKS
            assert background._PUBLICATION_SLOT.acquire(blocking=False)
            background._PUBLICATION_SLOT.release()
            return
        if fault_at == 'termination':
            assert not replacement.is_set() and len(launched) == 1
            permit_exit.set()
        assert replacement.wait(3), 'isolated supervisor abandoned retained recovery'
        for key in ['invoke_thread', 'watchdog_thread', 'heartbeat_thread']:
            states[0][key].join(timeout=2)
            assert not states[0][key].is_alive()
        current = store.load(context['run_id'])
        assert background._marker_lease(current) == launched[1]
        assert len(current['recovery_history']) == 1
        if origin == 'watchdog_local_before_save':
            expired_record = states[0]['recovery_record']
            assert expired_record['terminal'] is True
            assert expired_record['stage_results'][isolation.FINAL_REPORT_STAGE_ID]['reason'] == 'final_report_publication_deadline_exceeded'
        assert len(faults) == (2 if fault_at.endswith('fallback') else 0 if fault_at == 'termination' else 3 if fault_at == 'burst' else 1)
        assert current['identity'] == record['identity']
        for stage in record['completed_stages']:
            assert current['stage_results'][stage] == record['stage_results'][stage]
        assert current['human_review_required'] is True
        assert current['client_delivery_allowed'] is False
        assert coordinator._publish_result(lease_id=launched[0], run_id=context['run_id'],
                                           result=_valid_result(context)) == 'superseded'
        assert store.load(context['run_id']) == current
        # The recovered generation also expires: no third launch or history entry.
        isolation._publish_local_deadline_and_recover(
            coordinator, lease_id=launched[1], executor=lambda _: None, context=context,
            state={'worker_terminated': True}, render_started_epoch=1.0,
        )
        terminal = store.load(context['run_id'])
        assert terminal['terminal'] is True and terminal['status'] == 'blocked'
        assert len(terminal['recovery_history']) == 1 and len(launched) == 2
        with store._connection() as connection:
            jobs = connection.execute('SELECT status FROM nico_comprehensive_final_report_jobs WHERE run_id=?',
                                      (context['run_id'],)).fetchall()
        assert len(jobs) == 2 and all(row[0] in {'blocked', 'expired'} for row in jobs)
        with background._LOCAL_TASKS_LOCK:
            assert launched[0] not in background._LOCAL_TASKS
        assert background._PUBLICATION_SLOT.acquire(blocking=False)
        background._PUBLICATION_SLOT.release()
    finally:
        local_expiry.set()
        advance_finished.set()
        permit_exit.set()
        background.reset_final_report_publication_tasks_for_tests()
        for state in states:
            for key in ['invoke_thread', 'watchdog_thread', 'heartbeat_thread']:
                state[key].join(timeout=2)
