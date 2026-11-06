"""Synthetic local processes only; every spawned group has a bounded fallback."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nico import worker_execution as worker

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX process groups')


@pytest.fixture(autouse=True)
def isolated_latch(monkeypatch):
    import threading
    monkeypatch.setattr(worker, '_CLEANUP_UNCERTAIN', threading.Event())


@pytest.mark.parametrize('parent_exit,ignore_term,inherit', [
    (None, False, False), (None, True, False), (0, True, False),
    (7, False, False), (0, True, True),
])
def test_active_descendants_stopped(tmp_path, parent_exit, ignore_term, inherit):
    beat = tmp_path/'beat'
    group = tmp_path/'group'
    child = tmp_path/'child.py'
    child.write_text(
        'import signal,time\nfrom pathlib import Path\n'
        + ('signal.signal(signal.SIGTERM,signal.SIG_IGN)\n' if ignore_term else '')
        + f'p=Path({str(beat)!r});end=time.monotonic()+8;n=0\n'
        + 'while time.monotonic()<end:\n n+=1\n if n%10000==0:p.write_text(str(n))\n')
    parent = tmp_path/'parent.py'
    parent.write_text(
        'import os,sys,time,subprocess\nfrom pathlib import Path\n'
        + f'Path({str(group)!r}).write_text(str(os.getpid()))\n'
        + f'subprocess.Popen([sys.executable,{str(child)!r}]'
        + (')\n' if inherit else ',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n')
        + f'while not Path({str(beat)!r}).exists():time.sleep(.01)\n'
        + ('time.sleep(8)\n' if parent_exit is None else f'sys.exit({parent_exit})\n'))
    try:
        started = time.monotonic()
        result = worker.run_command([sys.executable, str(parent)], cwd=tmp_path,
                                    limits=worker.WorkerLimits(timeout_seconds=.3))
        assert time.monotonic()-started < 5
        assert result.timed_out == (parent_exit is None or inherit)
        assert result.returncode == (124 if result.timed_out else parent_exit)
        pgid = int(group.read_text())
        assert not worker._live_group(pgid)  # Zombies are not live work.
        before = beat.read_text(); time.sleep(.05)
        assert beat.read_text() == before
    finally:
        if group.exists():
            try: os.killpg(int(group.read_text()), signal.SIGKILL)
            except ProcessLookupError: pass


@pytest.mark.parametrize('file_output', [False, True])
def test_timeout_output_and_term_zero_status(tmp_path, file_output):
    code = "import signal,sys,time;signal.signal(signal.SIGTERM,lambda *_:sys.exit(0));print('é-output',flush=True);print('err-✓',file=sys.stderr,flush=True);time.sleep(8)"
    result = worker.run_command([sys.executable, '-c', code], cwd=tmp_path,
        limits=worker.WorkerLimits(timeout_seconds=.3),
        stdout_path=tmp_path/'out' if file_output else None)
    assert result.returncode == 124 and result.timed_out
    assert result.stdout == 'é-output\n' and result.stderr == 'err-✓\n'
    assert result.stdout_bytes == len(result.stdout.encode())
    assert result.stderr_bytes == len(result.stderr.encode())
    assert not result.output_truncated


def test_invalid_normal_output_is_strict_and_group_cleaned(tmp_path):
    group=tmp_path/'group'
    code=("import os,sys,subprocess;from pathlib import Path;"
          f"Path({str(group)!r}).write_text(str(os.getpid()));"
          "subprocess.Popen([sys.executable,'-c','import time;time.sleep(8)'],"
          "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);os.write(1,b'\\xff')")
    try:
        with pytest.raises(UnicodeDecodeError):
            worker.run_command([sys.executable,'-c',code],cwd=tmp_path)
        assert not worker._live_group(int(group.read_text()))
        assert not worker._CLEANUP_UNCERTAIN.is_set()
    finally:
        if group.exists():
            try:os.killpg(int(group.read_text()),signal.SIGKILL)
            except ProcessLookupError:pass


@pytest.mark.parametrize('file_output',[False,True])
def test_invalid_timeout_output_keeps_replacement(tmp_path,file_output):
    result=worker.run_command([sys.executable,'-c',
        "import os,time;os.write(1,b'\\xff'+b'x'*100);os.write(2,b'\\xfe');time.sleep(8)"],
        cwd=tmp_path,limits=worker.WorkerLimits(timeout_seconds=.3,max_output_chars=40),
        stdout_path=tmp_path/'out' if file_output else None)
    assert result.returncode==124 and result.timed_out and result.output_truncated
    assert result.stdout.startswith('�') and result.stderr=='�'
    assert result.stdout_bytes==(101 if file_output else 103)


def test_normal_newlines_and_file_preview_compatibility(tmp_path):
    result=worker.run_command([sys.executable,'-c',"import os;os.write(1,b'a\\r\\nb\\rc')"],cwd=tmp_path)
    assert result.stdout=='a\nb\nc'
    result=worker.run_command([sys.executable,'-c',"import os;os.write(1,b'\\xff')"],cwd=tmp_path,stdout_path=tmp_path/'out')
    assert result.returncode==0 and result.stdout=='�' and result.stdout_bytes==1


@pytest.mark.parametrize('group', [0, 1, os.getpgrp()])
def test_never_signal_unsafe_group(monkeypatch,group):
    class Fake: pid = group
    def forbidden(*args): raise AssertionError('signal attempted')
    monkeypatch.setattr(os,'killpg',forbidden)
    with pytest.raises(worker.WorkerCleanupError,match='unsafe'):
        worker._cleanup_group(Fake(),group)


def test_cleanup_uncertainty_blocks_future_launch_even_if_caught(tmp_path,monkeypatch):
    original = worker._cleanup_group
    def uncertain(process, group):
        original(process,group)  # no real process leaks from the test
        raise worker.WorkerCleanupError('synthetic uncertainty')
    monkeypatch.setattr(worker,'_cleanup_group',uncertain)
    with pytest.raises(worker.WorkerCleanupError):
        worker.run_command([sys.executable,'-c','print(1)'],cwd=tmp_path)
    def forbidden(*args,**kwargs): raise AssertionError('next scanner launched')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    with pytest.raises(worker.WorkerCleanupError,match='prior'):
        worker.run_command([sys.executable,'-c','print(2)'],cwd=tmp_path)


@pytest.mark.parametrize('failure',[KeyboardInterrupt, RuntimeError])
def test_exception_cleanup_preserves_exception(tmp_path,monkeypatch,failure):
    original = worker._BoundedCapture.pump
    processes=[]
    original_popen = subprocess.Popen
    def track(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process
    def interrupted(self,*args,**kwargs):
        raise failure('synthetic cancellation')
    monkeypatch.setattr(subprocess,'Popen',track)
    monkeypatch.setattr(worker._BoundedCapture,'pump',interrupted)
    with pytest.raises(failure):
        worker.run_command([sys.executable,'-c','import time;time.sleep(8)'],cwd=tmp_path)
    assert processes[0].poll() is not None
    assert not worker._live_group(processes[0].pid)
    assert not worker._CLEANUP_UNCERTAIN.is_set()


def test_scanner_sequence_aborts_on_cleanup_uncertainty(tmp_path,monkeypatch):
    from nico import scanner_tool_runners as scanners
    (tmp_path/'repo').mkdir()
    invoked=[]
    def failed(spec,*args,**kwargs):
        invoked.append(spec.name)
        raise worker.WorkerCleanupError('unconfirmed cleanup')
    monkeypatch.setattr(scanners,'run_scanner_tool',failed)
    specs=(scanners.ScannerToolSpec('first',('first',),'static'),
           scanners.ScannerToolSpec('second',('second',),'static'))
    with pytest.raises(worker.WorkerCleanupError):
        scanners.run_scanner_tools(worker.WorkerWorkspace(tmp_path),specs)
    assert invoked==['first']
    assert not issubclass(worker.WorkerCleanupError,Exception)
    ordinary_failure_caught=False
    with pytest.raises(worker.WorkerCleanupError):
        try:
            raise worker.WorkerCleanupError('must cross per-tool Exception handlers')
        except Exception:
            ordinary_failure_caught=True
    assert not ordinary_failure_caught


def test_drain_failure_latches_without_unbounded_communicate(tmp_path,monkeypatch):
    original_cleanup=worker._cleanup_group
    cleaned=[]
    def cleanup(*args):
        original_cleanup(*args)
        cleaned.append(True)
    original_pump=worker._BoundedCapture.pump
    original_active=worker._BoundedCapture.active
    def pump(self, timeout):
        assert 0 <= timeout <= .05
        if cleaned:
            raise OSError('synthetic drain failure')
        return original_pump(self, timeout)
    monkeypatch.setattr(worker,'_cleanup_group',cleanup)
    monkeypatch.setattr(worker._BoundedCapture,'active',lambda self: bool(cleaned) or original_active(self))
    monkeypatch.setattr(worker._BoundedCapture,'pump',pump)
    def forbidden(*args,**kwargs):raise AssertionError('unbounded communicate used')
    monkeypatch.setattr(subprocess.Popen,'communicate',forbidden)
    with pytest.raises(worker.WorkerCleanupError,match='drain'):
        worker.run_command([sys.executable,'-c','print(1)'],cwd=tmp_path)
    assert cleaned and worker._CLEANUP_UNCERTAIN.is_set()


def test_kill_failure_is_bounded_and_latched(tmp_path,monkeypatch):
    original=worker._cleanup_group
    def uncertain(process,group):
        original(process,group)
        raise PermissionError('synthetic signal denial after actual cleanup')
    monkeypatch.setattr(worker,'_cleanup_group',uncertain)
    with pytest.raises(worker.WorkerCleanupError):
        worker.run_command([sys.executable,'-c','print(1)'],cwd=tmp_path)
    assert worker._CLEANUP_UNCERTAIN.is_set()


def test_zombie_only_group_is_not_live(tmp_path,monkeypatch):
    # Confirm actual descendant tests use the Linux zombie-aware check, not killpg(0).
    if not Path('/proc/self/stat').exists(): pytest.skip('Linux process inventory')
    class Entry:
        name='1234'
        path=str(tmp_path)
    (tmp_path/'stat').write_text('1234 (synthetic) Z 1 1234 1234 0')
    class Entries:
        def __enter__(self):return iter([Entry()])
        def __exit__(self,*args):pass
    monkeypatch.setattr(os,'scandir',lambda _:Entries())
    monkeypatch.setattr(os,'killpg',lambda group, sig: None)  # group exists; inspect zombie state
    assert not worker._live_group(1234)


def test_snapshot_cleanup_abort_is_durable_and_not_resumed(monkeypatch):
    from copy import deepcopy
    from nico import snapshot_scanner_worker as snapshot
    from nico import scanner_raw_artifact_storage_v1 as artifacts
    from nico import scanner_recovery
    from nico.storage import MemoryAdapter
    store=MemoryAdapter(); scan_id='scan_snapshot_synthetic_cleanup'
    def no_list(*args,**kwargs):raise AssertionError('historical scanner payload scan')
    monkeypatch.setattr(store,'list',no_list)
    payload=dict(run_id='comprun_synthetic_cleanup',repository='owner/repo',
                 snapshot_commit_sha='a'*40,snapshot_id='snapshot_synthetic',
                 customer_id='synthetic_customer',project_id='synthetic_project',
                 authorized=True,authorized_by='synthetic',authorization_scope='synthetic only')
    job={**payload,'scan_id':scan_id,'status':'queued'}
    store.put('scanner_runs',scan_id,job)
    monkeypatch.setattr(snapshot,'STORE',store)
    monkeypatch.setattr(snapshot.base,'SCAN_JOBS',{scan_id:deepcopy(job)})
    specs=tuple(snapshot.tool_runners.ScannerToolSpec(name,(name,),'static') for name in ('first','uncertain','never'))
    monkeypatch.setattr(snapshot,'_requested_specs',lambda _:specs)
    monkeypatch.setattr(snapshot,'_requested_tool_names',lambda _:['first','uncertain','never'])
    def checkout(repo,sha,root,env):
        target=root/'repo';target.mkdir();return target,sha,[]
    monkeypatch.setattr(snapshot,'clone_repository_at_snapshot',checkout)
    monkeypatch.setattr(snapshot.base,'repository_size_observation',lambda _: {'source_bytes':0})
    monkeypatch.setattr(artifacts,'persist_scanner_result',lambda result,**_:result)
    called=[]
    prior={'tool':'first','status':'completed','findings':[{'synthetic':True}]}
    def tool(spec,*args,**kwargs):
        called.append(spec.name)
        if spec.name=='uncertain':raise worker.WorkerCleanupError('synthetic uncertainty')
        return deepcopy(prior)
    monkeypatch.setattr(snapshot.tool_runners,'run_scanner_tool',tool)
    snapshot._run_snapshot_scan(scan_id,payload)
    final=store.get('scanner_runs',scan_id)
    assert final['status']=='blocked' and final['terminal'] and not final['retryable']
    assert final['cleanup_unconfirmed'] and final['scanner_results']==[prior]
    assert final['completed_at'] and not final['client_delivery_allowed']
    assert called==['first','uncertain']
    # Simulate lost process memory/stale worker invocation; durable record wins.
    snapshot.base.SCAN_JOBS[scan_id]=deepcopy(job)
    snapshot._run_snapshot_scan(scan_id,payload)
    assert called==['first','uncertain']
    result=snapshot.start_snapshot_scan(payload)
    assert result['code']=='worker_cleanup_unconfirmed' and result['scan_id']==scan_id
    control=store.get('audit_log',snapshot._cleanup_control_id(payload))
    assert control['blocked_scan_id']==scan_id and 'scanner_results' not in control
    assert snapshot._cleanup_control({**payload,'customer_id':'other_tenant'}) is None
    assert snapshot._cleanup_control({**payload,'project_id':'other_project'}) is None
    assert snapshot._cleanup_control({**payload,'run_id':'other_run'}) is None
    assert snapshot._cleanup_control({**payload,'repository':'other/repo'}) is None
    assert snapshot._cleanup_control({**payload,'snapshot_commit_sha':'b'*40}) is None
    # A fresh snapshot ID cannot evade a block for the same assessed commit/run.
    assert snapshot._cleanup_control({**payload,'snapshot_id':'new_snapshot'}) is not None
    observed=[];original_get=store.get
    def bounded_get(table,key):
        observed.append((table,key));return original_get(table,key)
    monkeypatch.setattr(store,'get',bounded_get)
    result=snapshot.start_snapshot_scan(payload)
    assert observed==[('audit_log',snapshot._cleanup_control_id(payload))]
    monkeypatch.setattr(store,'get',original_get)
    def forbidden(**kwargs):raise AssertionError('recovery launched a worker')
    result=scanner_recovery.resume_interrupted_scanner_run(scan_id,actor='synthetic',store=store,thread_factory=forbidden)
    assert result['status']=='blocked' and result['automatic_resume'] is False
    from nico.snapshot_scanner_resilience_patch import _resume_snapshot_scanner_run
    result=_resume_snapshot_scanner_run(scan_id,actor='synthetic',store=store,thread_factory=forbidden)
    assert result['status']=='blocked' and result['automatic_resume'] is False
    assert store.get('scanner_runs',scan_id)==final


def test_cleanup_control_wrong_identity_fails_closed(monkeypatch):
    from nico import snapshot_scanner_worker as snapshot
    from nico.storage import MemoryAdapter
    store=MemoryAdapter();monkeypatch.setattr(snapshot,'STORE',store)
    payload={'run_id':'synthetic','repository':'owner/repo','snapshot_commit_sha':'a'*40}
    store.put('audit_log',snapshot._cleanup_control_id(payload),{
        'record_kind':'scanner_cleanup_control.v1','cleanup_unconfirmed':True,
        'cleanup_identity':{**snapshot._cleanup_control_identity(payload),'customer_id':'other'}})
    with pytest.raises(worker.WorkerCleanupError,match='admission blocked'):
        snapshot._cleanup_control(payload)


def test_completed_group_absence_does_not_require_unrelated_proc_inventory(tmp_path, monkeypatch):
    # A real owned child is reaped by communicate; the kernel can prove its
    # process group no longer exists without reading unrelated process records.
    def inaccessible_inventory(path):
        raise PermissionError('synthetic unrelated process inventory denial')
    monkeypatch.setattr(os, 'scandir', inaccessible_inventory)
    result = worker.run_command([sys.executable, '-c', 'print("done")'], cwd=tmp_path)
    assert result.returncode == 0 and result.stdout == 'done\n'
    assert not worker._CLEANUP_UNCERTAIN.is_set()


def test_existing_group_still_requires_readable_inventory(monkeypatch):
    calls = []
    def present(group, sig):
        calls.append((group, sig))
    def inaccessible_inventory(path):
        raise PermissionError('synthetic inventory denial')
    monkeypatch.setattr(os, 'killpg', present)
    monkeypatch.setattr(os, 'scandir', inaccessible_inventory)
    with pytest.raises(PermissionError):
        worker._live_group(987654)
    assert calls == [(987654, 0)]


@pytest.mark.parametrize('error', [PermissionError, OSError])
def test_group_probe_uncertainty_is_not_absence(monkeypatch, error):
    def uncertain(*args):
        raise error('synthetic group probe uncertainty')
    monkeypatch.setattr(os, 'killpg', uncertain)
    with pytest.raises(error):
        worker._live_group(987654)


def test_group_probe_permission_failure_latches_and_blocks_next_command(tmp_path, monkeypatch):
    # The real direct child has already completed; injecting uncertainty must
    # still fail closed rather than interpreting EPERM as group absence.
    def denied(group, sig):
        assert sig == 0
        raise PermissionError('synthetic group probe denial')
    monkeypatch.setattr(os, 'killpg', denied)
    with pytest.raises(worker.WorkerCleanupError) as failure:
        worker.run_command([sys.executable, '-c', 'pass'], cwd=tmp_path)
    assert isinstance(failure.value.__cause__, PermissionError)
    assert worker._CLEANUP_UNCERTAIN.is_set()
    def forbidden(*args, **kwargs):
        raise AssertionError('next command launched')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    with pytest.raises(worker.WorkerCleanupError, match='prior'):
        worker.run_command([sys.executable, '-c', 'pass'], cwd=tmp_path)
