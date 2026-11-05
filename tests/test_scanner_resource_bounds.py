"""Generated local inputs only; no network, retained artifacts or external storage."""
import os
import sys
import time
import threading
import pytest
from nico import worker_execution as worker

@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    monkeypatch.setattr(worker, '_CLEANUP_UNCERTAIN', threading.Event())
    import socket
    def forbidden(*args, **kwargs): raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)

@pytest.mark.parametrize('file_output', [False, True])
@pytest.mark.parametrize('fd', [1, 2])
def test_flood_is_bounded_and_never_success(tmp_path, file_output, fd):
    group=tmp_path/'group'
    code=("import os,signal;from pathlib import Path;"
          f"Path({str(group)!r}).write_text(str(os.getpid()));"
          "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
          f"\nwhile True:os.write({fd},b'x'*65536)")
    start=time.monotonic()
    result=worker.run_command([sys.executable,'-c',code],cwd=tmp_path,
        limits=worker.WorkerLimits(timeout_seconds=5,max_capture_bytes=4096,max_output_chars=8192),
        stdout_path=tmp_path/'out' if file_output else None)
    assert time.monotonic()-start < 4
    assert result.returncode==125 and not result.ok and not result.timed_out
    assert result.output_limit_exceeded and result.output_truncated
    assert len(result.stdout.encode())+len(result.stderr.encode()) <= 4096
    if file_output: assert (tmp_path/'out').stat().st_size <= 4096
    assert not worker._live_group(int(group.read_text()))

@pytest.mark.parametrize('size,exceeded', [(1023,False),(1024,False),(1025,True)])
def test_exact_aggregate_byte_boundary(tmp_path,size,exceeded):
    result=worker.run_command([sys.executable,'-c',f"import os;os.write(1,b'x'*512);os.write(2,b'y'*{size-512})"],
       cwd=tmp_path,limits=worker.WorkerLimits(max_capture_bytes=1024))
    assert result.output_limit_exceeded is exceeded
    assert result.returncode==(125 if exceeded else 0)
    assert len(result.stdout)+len(result.stderr)==min(size,1024)


def test_shared_deadline_nested_commands_and_no_late_launch(tmp_path,monkeypatch):
    with worker.scanner_suite_deadline(time.monotonic()+.25):
        first=worker.run_command([sys.executable,'-c',"print('first')"],cwd=tmp_path)
        assert first.ok
        second=worker.run_command([sys.executable,'-c',"import time;print('partial',flush=True);time.sleep(8)"],cwd=tmp_path)
        assert second.timed_out and second.returncode==124 and second.stdout=='partial\n'
        def forbidden(*args,**kwargs):raise AssertionError('late launch')
        with monkeypatch.context() as m:
            m.setattr(worker.subprocess,'Popen',forbidden)
            with worker.scanner_suite_deadline(time.monotonic()+100):
                third=worker.run_command([sys.executable,'-c','print(3)'],cwd=tmp_path)
        assert third.timed_out and third.stdout==''
    assert worker.suite_time_remaining()==float('inf')


def test_snapshot_deadline_keeps_prior_results_and_accounts_unlaunched(monkeypatch):
    from copy import deepcopy
    from nico import snapshot_scanner_worker as snapshot
    from nico import scanner_raw_artifact_storage_v1 as artifacts
    from nico import candidate_workspace_capture_v1 as capture
    from nico.storage import MemoryAdapter
    store=MemoryAdapter();sid='scan_synthetic_budget'
    payload=dict(run_id='run_synthetic_budget',repository='owner/repo',snapshot_commit_sha='a'*40,
                 snapshot_id='snapshot_synthetic',customer_id='customer',project_id='project')
    job={**payload,'scan_id':sid,'status':'queued'};store.put('scanner_runs',sid,job)
    monkeypatch.setattr(snapshot,'STORE',store)
    monkeypatch.setattr(snapshot.base,'SCAN_JOBS',{sid:deepcopy(job)})
    monkeypatch.setattr(snapshot.base,'TOTAL_SCAN_TIMEOUT_SECONDS',.05)
    specs=tuple(snapshot.tool_runners.ScannerToolSpec(n,(n,),'static') for n in ['first','slow','never'])
    monkeypatch.setattr(snapshot,'_requested_specs',lambda _:specs)
    monkeypatch.setattr(snapshot,'_requested_tool_names',lambda _:['first','slow','never'])
    def checkout(repo,sha,root,env):
        p=root/'repo';p.mkdir();return p,sha,[]
    monkeypatch.setattr(snapshot,'clone_repository_at_snapshot',checkout)
    monkeypatch.setattr(snapshot.base,'repository_size_observation',lambda _: {'source_bytes':0})
    monkeypatch.setattr(artifacts,'persist_scanner_result',lambda result,**_:result)
    monkeypatch.setattr(capture,'capture_workspace',lambda *a,**k:{'synthetic':True})
    called=[]
    def tool(spec,*args,**kwargs):
        called.append(spec.name)
        if spec.name=='slow':time.sleep(.07)
        return {'tool':spec.name,'status':'completed','execution_state':'completed',
                'verified':True,'verified_complete':True,'failure_reason':'',
                'findings':[{'synthetic':spec.name}]}
    monkeypatch.setattr(snapshot.tool_runners,'run_scanner_tool',tool)
    snapshot._run_snapshot_scan(sid,payload)
    final=store.get('scanner_runs',sid);rows=final['scanner_results']
    assert called==['first','slow']
    assert rows[0]['status']=='completed' and rows[0]['findings']
    assert rows[1]['status']=='timeout' and rows[1]['findings'] and not rows[1]['verified_for_this_report']
    assert not rows[1]['verified'] and not rows[1]['verified_complete']
    assert rows[1]['execution_state']=='timeout' and rows[1]['failure_reason']=='scanner_suite_deadline_exhausted'
    assert rows[2]['execution_observed_for_this_report'] is False
    assert rows[2]['status']=='unavailable' and rows[2]['execution_observed'] is False
    assert rows[2]['commit_sha']=='a'*40 and rows[2]['findings']==[]
    assert final['tools_run']==['first'] and final['timed_out_tools']==['slow']
    assert final['scanner_suite_budget_seconds']==.05


def test_setup_expiry_does_not_spawn(tmp_path,monkeypatch):
    from pathlib import Path
    original=Path.open
    def slow_open(path,*args,**kwargs):
        handle=original(path,*args,**kwargs)
        if path.name=='out': time.sleep(.03)
        return handle
    monkeypatch.setattr(Path,'open',slow_open)
    def forbidden(*args,**kwargs): raise AssertionError('expired setup launched process')
    monkeypatch.setattr(worker.subprocess,'Popen',forbidden)
    with worker.scanner_suite_deadline(time.monotonic()+.01):
        result=worker.run_command(['synthetic'],cwd=tmp_path,stdout_path=tmp_path/'out')
    assert result.timed_out and not result.execution_observed


def test_partial_file_and_canonical_payload_never_claim_complete(tmp_path,monkeypatch):
    from nico import scanner_tool_runners as runners
    from nico import scanner_evidence_pipeline_v1 as pipeline
    path=tmp_path/'raw';path.write_text('[]')
    result=worker.WorkerCommandResult(('synthetic',),125,'[]','',stdout_path=str(path),
                                    output_truncated=True,output_limit_exceeded=True)
    text,complete,reason=runners._complete_stdout(result)
    assert text=='[]' and not complete and 'byte_limit' in reason
    monkeypatch.setattr(pipeline,'_scanner_version',lambda *a:'synthetic')
    monkeypatch.setattr('nico.scanner_execution_receipt_v1.native_coverage_observation',lambda *a:{})
    spec=runners.ScannerToolSpec('synthetic',('synthetic',),'static')
    def payload(command_result):
        return pipeline._tool_payload(spec,command_result,findings=[{'synthetic':True}],
           capture_complete=True,reason='',raw_blob={},execution_source='synthetic',
           workspace=worker.WorkerWorkspace(tmp_path))
    row=payload(result)
    assert row['status']=='failed' and not row['output_capture_complete'] and row['output_limit_exceeded']
    assert row['findings']==[{'synthetic':True}] and not row['verified_for_this_report']
    no_launch=worker.WorkerCommandResult(('synthetic',),124,'','',timed_out=True,execution_observed=False)
    row=payload(no_launch)
    assert row['status']=='unavailable' and not row['execution_observed_for_this_report']
    assert not row['output_capture_complete'] and row['scanner_execution_receipt'] is None


def test_canonical_no_launch_does_not_issue_invocation_receipt(tmp_path,monkeypatch):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico import scanner_execution_receipt_v1 as receipts
    monkeypatch.setattr(receipts,'input_snapshot',lambda *a,**k:[])
    def forbidden(*a,**k):raise AssertionError('unexecuted invocation receipt')
    monkeypatch.setattr(receipts,'invocation_receipt',forbidden)
    def runner(args,**kwargs):
        return worker.WorkerCommandResult(tuple(args),124,'','',timed_out=True,execution_observed=False)
    result=pipeline._run(runner,('synthetic',),cwd=tmp_path,limits=worker.WorkerLimits(),stdout_path=tmp_path/'out')
    assert result.scanner_execution_receipt is None and not result.execution_observed


def test_capture_setup_failure_closes_selector_and_cleans_child(tmp_path,monkeypatch):
    selectors=[];processes=[]
    original_selector=worker.selectors.DefaultSelector
    original_popen=worker.subprocess.Popen
    def selector():
        result=original_selector();selectors.append(result);return result
    def popen(*a,**k):
        result=original_popen(*a,**k);processes.append(result);return result
    def fail(*a,**k):raise OSError('synthetic capture setup failure')
    monkeypatch.setattr(worker.selectors,'DefaultSelector',selector)
    monkeypatch.setattr(worker.subprocess,'Popen',popen)
    monkeypatch.setattr(worker.os,'set_blocking',fail)
    with pytest.raises(OSError,match='synthetic capture'):
        worker.run_command([sys.executable,'-c','import time;time.sleep(8)'],cwd=tmp_path)
    assert selectors[0].get_map() is None
    assert processes[0].poll() is not None and not worker._live_group(processes[0].pid)
    assert not worker._CLEANUP_UNCERTAIN.is_set()
