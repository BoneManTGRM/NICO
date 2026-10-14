"""Deterministic synthetic reproduction against ce694923; no private source/PG.

Existing fixture clock advances model elapsed restoration, not a changed lease
policy. No sleep, actual renderer, replacement deadline or added heartbeat.
Four regression assertions fail on the published implementation;
two diagnostic checks pass while demonstrating lost ownership/finalization.
"""
from copy import deepcopy

import pytest

from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
from nico.review_pdf_preparation_service_v1 import CapturedSource
from tests.test_review_pdf_preparation_jobs_v1 import identity
from tests.test_review_pdf_preparation_service_v1 import artifact, seam


def test_red_expired_initial_restoration_must_not_spawn_worker(seam):
    service, jobs, source, _, worker, clock, status = seam
    calls = 0
    def capture(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            clock[0] += 31  # Existing claim 1000, lease expiry 1030, now 1031.
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    with pytest.raises(PreparationConflict, match='preparation_lease_not_owned'):
        service.run_once(identity())
    job = jobs.get(identity())
    assert job['deadline_epoch'] == 1900
    assert job['lease_until_epoch'] == 1030
    assert job['status'] != 'ready' and 'pdf_base64' not in job
    worker.assert_not_called()  # RED: published service calls worker once.


def test_red_worker_allowance_subtracts_initial_restoration_elapsed(seam):
    service, jobs, source, _, worker, clock, status = seam
    calls = 0
    def capture(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            clock[0] += 5  # Still inside unchanged 30-second lease.
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    observed = {}
    def render(*args, **kwargs):
        observed.update(allowance=kwargs['max_seconds'], now=clock[0],
                        deadline=jobs.get(identity())['deadline_epoch'])
        return artifact()
    worker.side_effect = render
    result = service.run_once(identity())
    assert result['status'] == 'ready' and result['client_delivery_allowed'] is False
    assert observed['deadline'] == 1900 and observed['now'] == 1005
    assert observed['allowance'] <= observed['deadline'] - observed['now']  # RED: 900 > 895.


def test_diagnostic_final_restoration_discards_successful_render_after_expiry(seam):
    service, jobs, source, _, worker, clock, status = seam
    calls = 0
    def capture(_):
        nonlocal calls
        calls += 1
        if calls == 2:
            clock[0] += 31
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    # Simulate a successful child's last genuine heartbeat at time 1000.
    def render(*args, **kwargs):
        kwargs['heartbeat']()
        return artifact()
    worker.side_effect = render
    with pytest.raises(PreparationConflict, match='preparation_lease_not_owned'):
        service.run_once(identity())
    worker.assert_called_once()
    assert calls == 2
    job = jobs.get(identity())
    assert job['lease_until_epoch'] == 1030 and clock[0] == 1031
    assert job['status'] == 'rendering' and 'pdf_base64' not in job
    assert job['client_delivery_allowed'] is False


def test_diagnostic_two_slow_restorations_exhaust_attempts_without_ready(seam):
    service, jobs, source, _, worker, clock, status = seam
    def capture(_):
        clock[0] += 31
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    for _ in range(2):
        with pytest.raises(PreparationConflict, match='preparation_lease_not_owned'):
            service.run_once(identity())
    assert worker.call_count == 0
    assert service.run_once(identity()) is None
    job = jobs.get(identity())
    assert job['status'] == 'budget_exhausted' and job['attempts'] == 2
    assert clock[0] < job['deadline_epoch'] == 1900
    assert 'pdf_base64' not in job and job['client_delivery_allowed'] is False


@pytest.mark.parametrize('trigger', ['cancel', 'deadline'])
def test_red_blocked_heartbeat_cannot_block_child_cleanup(seam, monkeypatch, trigger):
    """Real harmless child; bounded rendezvous, no actual rendering or database."""
    import subprocess
    import sys
    from threading import Event, Thread
    from types import SimpleNamespace
    from nico import review_pdf_preparation_worker_v1 as worker_module

    service, jobs, _, capacity, _, _, _ = seam
    heartbeat_entered, release_heartbeat = Event(), Event()
    cleanup_entered, allow_reap, spawned = Event(), Event(), Event()
    stop = Event()
    ticks = [1000.]
    children, errors = [], []
    actual_spawn, actual_terminate = subprocess.Popen, worker_module.terminate_process

    def spawn(_command, **kwargs):
        child = actual_spawn([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        children.append(child)
        spawned.set()
        return child

    def heartbeat(*args, **kwargs):
        heartbeat_entered.set()
        assert release_heartbeat.wait(3), 'test heartbeat must be released during cleanup'
        raise PreparationConflict('synthetic interrupted database operation')

    def terminate(child):
        cleanup_entered.set()
        assert allow_reap.wait(3), 'test reaping gate must be released during cleanup'
        return actual_terminate(child)

    monkeypatch.setattr(worker_module, 'subprocess', SimpleNamespace(Popen=spawn, DEVNULL=subprocess.DEVNULL))
    monkeypatch.setattr(worker_module, 'time', SimpleNamespace(monotonic=lambda: ticks[0]))
    monkeypatch.setattr(worker_module, 'terminate_process', terminate)
    monkeypatch.setattr(jobs, 'heartbeat', heartbeat)
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    monkeypatch.setattr(DeadlineGuard, 'HEARTBEAT_INTERVAL', .005)
    service.worker = worker_module.run_worker

    def run():
        try:
            service.run_once(identity(), stop=stop)
        except BaseException as error:
            errors.append(error)

    coordinator = Thread(target=run, daemon=True)
    coordinator.start()
    reached_cleanup = False
    try:
        assert heartbeat_entered.wait(2), 'worker must reach the blocked heartbeat'
        assert spawned.wait(1), 'child must already be running before advancing its clock'
        if trigger == 'cancel':
            stop.set()
        else:
            ticks[0] = 1901.  # Cross unchanged 900-second worker budget.
        reached_cleanup = cleanup_entered.wait(.5)
        # Capacity must stay owned while the real child has not been reaped.
        held = not capacity.acquire(blocking=False)
        if not held:
            capacity.release()
        assert held
        assert children and children[0].poll() is None
    finally:
        # Always unblock current code and reap the actual child, even on RED.
        release_heartbeat.set()
        allow_reap.set()
        coordinator.join(3)
        for child in children:
            if child.poll() is None:
                actual_terminate(child)
    assert not coordinator.is_alive()
    assert children[0].poll() is not None
    assert errors
    assert jobs.get(identity())['status'] != 'ready'
    assert capacity.acquire(timeout=1), 'capacity returns only after all operations finish'
    capacity.release()
    assert reached_cleanup, 'RED: blocked database heartbeat prevented physical deadline/cancel cleanup'


@pytest.mark.parametrize('stage', ['initial', 'final'])
def test_capture_can_span_lease_with_independent_owned_heartbeats(seam, monkeypatch, stage):
    from threading import Event
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    monkeypatch.setattr(DeadlineGuard, 'HEARTBEAT_INTERVAL', .002)
    service, jobs, source, _, _, clock, status = seam
    renewed = Event()
    heartbeat = jobs.heartbeat
    def renew(*args, **kwargs):
        result = heartbeat(*args, **kwargs)
        renewed.set()
        return result
    monkeypatch.setattr(jobs, 'heartbeat', renew)
    calls = 0
    def capture(_):
        nonlocal calls
        calls += 1
        if calls == (1 if stage == 'initial' else 2):
            for _ in range(2):
                renewed.clear()
                clock[0] += 20
                assert renewed.wait(1), 'heartbeat must progress independently of restoration'
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    job = service.run_once(identity())
    assert job['status'] == 'ready' and job['deadline_epoch'] == 1900
    assert clock[0] == 1040 and job['client_delivery_allowed'] is False


@pytest.mark.parametrize('stage', ['initial', 'final'])
def test_cancel_during_capture_quarantines_until_capture_exits(seam, stage):
    from threading import Event, Thread
    service, jobs, source, capacity, worker, _, status = seam
    entered, release, stop = Event(), Event(), Event()
    calls, errors = 0, []
    def capture(_):
        nonlocal calls
        calls += 1
        if calls == (1 if stage == 'initial' else 2):
            entered.set()
            assert release.wait(3)
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    def run():
        try: service.run_once(identity(), stop=stop)
        except BaseException as error: errors.append(error)
    thread = Thread(target=run, daemon=True); thread.start()
    try:
        assert entered.wait(1)
        stop.set(); thread.join(1)
        assert not thread.is_alive() and errors
        assert not capacity.acquire(blocking=False)
        assert jobs.get(identity())['status'] != 'ready'
    finally:
        release.set(); thread.join(1)
    assert capacity.acquire(timeout=1)
    capacity.release()
    assert worker.call_count == (0 if stage == 'initial' else 1)


@pytest.mark.parametrize('stage', ['initial', 'final'])
def test_reclaim_during_capture_preserves_successor(seam, stage):
    service, jobs, source, _, worker, clock, status = seam
    calls, successor = 0, []
    def capture(_):
        nonlocal calls
        calls += 1
        if calls == (1 if stage == 'initial' else 2):
            clock[0] += 31
            successor.append(jobs.claim(identity()))
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    with pytest.raises(PreparationConflict): service.run_once(identity())
    job = jobs.get(identity())
    assert job == successor[0] and job['status'] == 'rendering'
    assert 'pdf_base64' not in job
    assert worker.call_count == (0 if stage == 'initial' else 1)


def test_slow_publication_rolls_back_with_original_deadline(seam, monkeypatch):
    service, jobs, _, _, _, clock, _ = seam
    write = jobs._write
    def slow_write(connection, i, job):
        write(connection, i, job)
        if job['status'] == 'ready': clock[0] = 1901
    monkeypatch.setattr(jobs, '_write', slow_write)
    with pytest.raises(PreparationConflict): service.run_once(identity())
    job = jobs.get(identity())
    assert job['status'] != 'ready' and 'pdf_base64' not in job
    assert job['deadline_epoch'] == 1900


def test_initial_restoration_consuming_absolute_budget_never_spawns(seam):
    service, jobs, source, _, worker, clock, status = seam
    def capture(_):
        clock[0] = 1901
        return CapturedSource(deepcopy(status), 'fixed-source-storage')
    source.capture.side_effect = capture
    with pytest.raises(PreparationConflict): service.run_once(identity())
    worker.assert_not_called()
    assert jobs.get(identity())['status'] != 'ready'


def test_timed_out_serializer_keeps_directory_until_writer_physically_finishes(monkeypatch):
    from pathlib import Path
    from threading import Event, Thread
    from types import SimpleNamespace
    from nico import review_pdf_preparation_worker_v1 as worker_module
    entered, release = Event(), Event()
    ticks, paths, errors, state = [1000.], [], [], {}
    atomic = worker_module._atomic_json
    def slow_write(path, value):
        paths.append(path); entered.set()
        assert release.wait(3)
        atomic(path, value)
    monkeypatch.setattr(worker_module, '_atomic_json', slow_write)
    monkeypatch.setattr(worker_module, 'time', SimpleNamespace(monotonic=lambda: ticks[0]))
    from unittest.mock import Mock
    spawn = Mock(side_effect=AssertionError('must not spawn after serialization deadline'))
    monkeypatch.setattr(worker_module.subprocess, 'Popen', spawn)
    def run():
        try: worker_module.run_worker({}, identity(), stop=Event(), heartbeat=Mock(), state=state, max_seconds=900)
        except BaseException as error: errors.append(error)
    thread = Thread(target=run, daemon=True); thread.start()
    try:
        assert entered.wait(1)
        ticks[0] = 1901; thread.join(1)
        assert not thread.is_alive() and errors
        assert paths[0].parent.exists(), 'writer still owns its private directory'
        assert state['temporary_files_cleanup_confirmed'] is False
    finally:
        release.set(); thread.join(1)
    # Join the cleanup outcome with a bounded event-driven observation.
    import time
    deadline = time.monotonic()+1
    while paths[0].parent.exists() and time.monotonic()<deadline:
        Event().wait(.01)
    assert not paths[0].parent.exists()
    assert state['temporary_files_cleanup_confirmed'] is True
    spawn.assert_not_called()


def _delayed_commit_adapter(monkeypatch, jobs, state, entered, release, *, lost_ack=False):
    import json
    original = jobs.adapter._connect
    class Connection:
        def __init__(self): self.connection, self.delay = original(), False
        def __getattr__(self, key): return getattr(self.connection, key)
        def execute(self, sql, params=()):
            if sql.startswith('INSERT INTO nico_records'):
                self.delay = json.loads(params[-1])['status'] == state
            return self.connection.execute(sql, params)
        def commit(self):
            if self.delay:
                entered.set()
                assert release.wait(3)
            self.connection.commit()
            if self.delay and lost_ack:
                raise OSError('synthetic lost commit acknowledgement')
    monkeypatch.setattr(jobs.adapter, '_connect', Connection)


@pytest.mark.parametrize('trigger', ['timeout', 'cancel', 'lost_ack'])
def test_committed_publication_recovers_after_explicit_unknown_outcome(seam, monkeypatch, trigger):
    from threading import Event, Thread
    from nico import review_pdf_preparation_service_v1 as module
    from nico.review_pdf_preparation_deadline_v1 import CommitOutcomeUnknown, DeadlineGuard
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime
    service, jobs, _, capacity, worker, _, _ = seam
    entered, release, stop = Event(), Event(), Event()
    ticks, errors = [1000.], []
    monkeypatch.setattr(module, 'DeadlineGuard', lambda seconds, stop: DeadlineGuard(seconds, stop, clock=lambda: ticks[0]))
    _delayed_commit_adapter(monkeypatch, jobs, 'ready', entered, release, lost_ack=trigger=='lost_ack')
    def run():
        try: service.run_once(identity(), stop=stop)
        except BaseException as error: errors.append(error)
    thread = Thread(target=run, daemon=True); thread.start()
    try:
        assert entered.wait(1)
        if trigger == 'timeout': ticks[0] = 1901
        elif trigger == 'cancel': stop.set()
        else: release.set()
        thread.join(1)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], CommitOutcomeUnknown)
        if trigger != 'lost_ack':
            assert not capacity.acquire(blocking=False)
            assert jobs.get(identity())['status'] == 'rendering'
    finally:
        release.set(); thread.join(1)
    assert capacity.acquire(timeout=1)
    capacity.release()
    assert jobs.get(identity())['status'] == 'ready'
    # Recovery is read-only and still performs full source/draft/hash checks.
    runtime = PreparationRuntime(service)
    monkeypatch.setattr(runtime, '_job', lambda *args: (identity(), jobs.get(identity())))
    binding = dict(commit_sha=identity().commit_sha, canonical_truth_sha256=identity().canonical_truth_sha256)
    assert runtime.retrieve(identity().run_id, identity().language, identity().job_id, binding).body.startswith(b'%PDF')
    worker.assert_called_once()
    assert jobs.get(identity())['client_delivery_allowed'] is False


def test_delayed_admission_commit_is_unknown_and_recoverable_not_rolled_back(seam, monkeypatch):
    from dataclasses import replace
    from threading import Event, Thread
    from nico.review_pdf_preparation_deadline_v1 import CommitOutcomeUnknown, DeadlineGuard
    _, jobs, _, _, _, _, _ = seam
    i = replace(identity(), language='en')
    entered, release = Event(), Event()
    ticks, errors = [1000.], []
    guard = DeadlineGuard(20, Event(), clock=lambda: ticks[0])
    _delayed_commit_adapter(monkeypatch, jobs, 'queued', entered, release)
    def run():
        try: guard.call(jobs.enqueue, i, preparation_authorized=True, check=guard.check, commit_guard=guard)
        except BaseException as error: errors.append(error)
    thread = Thread(target=run, daemon=True); thread.start()
    try:
        assert entered.wait(1)
        ticks[0] = 1021; thread.join(1)
        assert not thread.is_alive() and isinstance(errors[0], CommitOutcomeUnknown)
        assert jobs.get(i) is None
    finally:
        release.set(); thread.join(1)
    import time
    end = time.monotonic()+1
    while not guard.idle() and time.monotonic()<end: Event().wait(.01)
    assert guard.idle()
    assert jobs.get(i)['status'] == 'queued'
    assert jobs.enqueue(i, preparation_authorized=True)['attempts'] == 0


def test_output_loading_consumes_original_worker_deadline(monkeypatch):
    from pathlib import Path
    from threading import Event
    from types import SimpleNamespace
    from unittest.mock import Mock
    from nico import review_pdf_preparation_worker_v1 as module
    ticks, state = [1000.], {}
    class Process:
        pid, returncode = 12345, 0
        def poll(self): return 0
    def spawn(command, **kwargs):
        module._atomic_json(Path(command[-1])/'output.json', artifact())
        return Process()
    read = Path.read_text
    def slow_read(path, *args, **kwargs):
        result = read(path, *args, **kwargs)
        if path.name == 'output.json': ticks[0] = 1901
        return result
    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(module, 'terminate_process', Mock(return_value=True))
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: ticks[0]))
    monkeypatch.setattr(Path, 'read_text', slow_read)
    with pytest.raises(RuntimeError, match='cancelled_or_expired'):
        module.run_worker({}, identity(), stop=Event(), heartbeat=Mock(), state=state, max_seconds=900)
    assert state['physical_worker_exit_confirmed'] is True
    assert state['temporary_files_cleanup_confirmed'] is True


def test_commit_registration_and_timeout_classification_are_atomic():
    from threading import Event, Thread
    from nico.review_pdf_preparation_deadline_v1 import CommitOutcomeUnknown, DeadlineGuard
    stop, checked, release, observer_started, observer_finished = (Event() for _ in range(5))
    guard, outcomes = DeadlineGuard(20, stop), []
    original_check = guard.check
    def paused_check():
        original_check()
        checked.set()
        assert release.wait(1)
    guard.check = paused_check
    commit = Thread(target=guard.begin_commit)
    def observe():
        observer_started.set()
        try: original_check()
        except BaseException as error: outcomes.append(error)
        finally: observer_finished.set()
    observer = Thread(target=observe)
    commit.start()
    try:
        assert checked.wait(1)
        stop.set(); observer.start()
        assert observer_started.wait(1)
        assert not observer_finished.wait(.05), 'timeout must wait for atomic commit registration'
    finally:
        release.set(); commit.join(1); observer.join(1)
    assert not commit.is_alive() and not observer.is_alive()
    assert len(outcomes) == 1 and isinstance(outcomes[0], CommitOutcomeUnknown)


def test_private_directory_retained_until_child_exit_is_confirmed():
    from pathlib import Path
    from threading import Event
    import time
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    from nico.review_pdf_preparation_worker_v1 import _owned_directory
    guard = DeadlineGuard(900, Event())
    state = {'physical_worker_exit_confirmed': False}
    with _owned_directory(guard, state) as name:
        root = Path(name)
        (root/'private.json').write_text('synthetic')
    try:
        assert root.exists() and not state['temporary_files_cleanup_confirmed']
        (root/'late-output.json').write_text('synthetic late child output')
        assert root.exists()
    finally:
        state['physical_worker_exit_confirmed'] = True
    deadline = time.monotonic()+1
    while not state['temporary_files_cleanup_confirmed'] and time.monotonic()<deadline:
        Event().wait(.01)
    assert state['temporary_files_cleanup_confirmed'] and not root.exists()


def test_scheduled_heartbeat_remains_outstanding_through_supervisor_shutdown(seam, monkeypatch):
    from threading import Event, Thread, current_thread
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    service, jobs, source, capacity, _, _, _ = seam
    scheduled, start_release, active, finish = (Event() for _ in range(4))
    errors = []
    original_start = Thread.start
    def delayed_start(thread):
        if current_thread().name == 'nico-review-lease' and thread.name == 'nico-review-bounded-call':
            scheduled.set()
            assert start_release.wait(2)
        return original_start(thread)
    def heartbeat(*args, **kwargs):
        active.set()
        assert finish.wait(2)
    def failed_capture(*args):
        assert scheduled.wait(1)
        raise ValueError('synthetic validation failure')
    monkeypatch.setattr(DeadlineGuard, 'HEARTBEAT_INTERVAL', .002)
    monkeypatch.setattr(Thread, 'start', delayed_start)
    monkeypatch.setattr(jobs, 'heartbeat', heartbeat)
    source.capture.side_effect = failed_capture
    def run():
        try: service.run_once(identity())
        except BaseException as error: errors.append(error)
    coordinator = Thread(target=run)
    coordinator.start()
    try:
        assert scheduled.wait(1)
        coordinator.join(1)
        assert not coordinator.is_alive() and isinstance(errors[0], ValueError)
        assert not capacity.acquire(blocking=False)
        start_release.set()
        assert active.wait(1)
        assert not capacity.acquire(timeout=.1), 'blocked heartbeat must retain capacity after supervisor exits'
    finally:
        start_release.set(); finish.set(); coordinator.join(1)
    assert capacity.acquire(timeout=1)
    capacity.release()


def test_pre_registration_heartbeat_cannot_race_immediate_capacity_release(seam, monkeypatch):
    from threading import Event, Thread, current_thread
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    service, jobs, source, capacity, _, _, _ = seam
    checked, proceed, active, finish, supervisor_exited = (Event() for _ in range(5))
    errors = []
    original_check, original_idle, original_supervise = DeadlineGuard.check, DeadlineGuard.idle, DeadlineGuard.supervise_lease
    paused = [False]
    def check(guard):
        original_check(guard)
        if current_thread().name == 'nico-review-lease' and not paused[0]:
            paused[0] = True; checked.set(); assert proceed.wait(2)
    def supervise(guard, heartbeat):
        done, thread = original_supervise(guard, heartbeat)
        def observe(): thread.join(); supervisor_exited.set()
        Thread(target=observe, daemon=True).start()
        return done, thread
    def idle(guard):
        snapshot = original_idle(guard)
        if guard.stop.is_set() and current_thread().name == 'synthetic-coordinator' and snapshot:
            # Force a scheduler switch after the unsafe first idle snapshot.
            proceed.set(); assert active.wait(1); assert supervisor_exited.wait(1)
        return snapshot
    def heartbeat(*args, **kwargs): active.set(); assert finish.wait(2)
    def capture(*args): assert checked.wait(1); raise ValueError('synthetic source failure')
    monkeypatch.setattr(DeadlineGuard, 'HEARTBEAT_INTERVAL', .002)
    monkeypatch.setattr(DeadlineGuard, 'check', check)
    monkeypatch.setattr(DeadlineGuard, 'idle', idle)
    monkeypatch.setattr(DeadlineGuard, 'supervise_lease', supervise)
    monkeypatch.setattr(jobs, 'heartbeat', heartbeat)
    source.capture.side_effect = capture
    def run():
        try: service.run_once(identity())
        except BaseException as error: errors.append(error)
    coordinator = Thread(target=run, name='synthetic-coordinator'); coordinator.start()
    try:
        assert checked.wait(1)
        coordinator.join(1)
        assert not coordinator.is_alive() and isinstance(errors[0], ValueError)
        proceed.set(); assert active.wait(1); assert supervisor_exited.wait(1)
        assert not capacity.acquire(timeout=.1), 'immediate release must observe supervisor exit before final idle snapshot'
    finally:
        proceed.set(); finish.set(); coordinator.join(1)
    assert capacity.acquire(timeout=1); capacity.release()
