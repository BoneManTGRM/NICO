"""Owned synthetic writers and installed Bandit; no external acquisition."""
import gzip
import json
import os
from pathlib import Path
import sys
import threading
import pytest
from nico import worker_execution as worker
from nico import scanner_evidence_pipeline_v1 as pipeline

@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    import socket
    monkeypatch.setattr(worker,'_CLEANUP_UNCERTAIN',threading.Event())
    def forbidden(*a,**k):raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket,'connect',forbidden)

@pytest.mark.parametrize('name,flag',[('bandit','-o'),('gitleaks','--report-path')])
@pytest.mark.parametrize('flood',[False,True])
def test_native_writer_is_redirected_and_bounded(tmp_path,name,flag,flood):
    executable=tmp_path/name
    destination = '-' if name == 'gitleaks' else '/dev/stdout'
    executable.write_text(f'#!{sys.executable}\nimport sys,os\np=sys.argv[sys.argv.index({flag!r})+1]\nassert p=={destination!r}\nwith (os.fdopen(os.dup(1),"wb",buffering=0) if p=="-" else open(p,"wb",buffering=0)) as f:\n'+
        (' while True:f.write(b"x"*65536)\n' if flood else ' f.write(b"[]")\n'))
    executable.chmod(0o700)
    raw=tmp_path/'report';log=tmp_path/'log'
    result=worker.run_command([str(executable),flag,str(raw)],cwd=tmp_path,stdout_path=log,
       limits=worker.WorkerLimits(timeout_seconds=3,max_capture_bytes=1024,native_report_flag=flag))
    assert result.args[-1]==destination and result.stdout_path==str(raw)
    assert raw.stat().st_size <= 1024 and not log.exists()
    assert result.output_limit_exceeded is flood
    assert result.returncode==(125 if flood else 0)
    assert raw.read_bytes()==(b'x'*1024 if flood else b'[]')


def test_actual_bandit_json_streamed_to_parent_file(tmp_path):
    binary=Path(sys.executable).parent/'bandit'
    assert binary.is_file(), 'existing installed Bandit required for this probe'
    repo=tmp_path/'repo';repo.mkdir();(repo/'app.py').write_text('assert True\n')
    raw=tmp_path/'report.json'
    result=worker.run_command([str(binary),'-r','.', '-f','json','-o',str(raw)],cwd=repo,
        limits=worker.WorkerLimits(timeout_seconds=15,native_report_flag='-o'))
    assert result.returncode==1 and not result.output_limit_exceeded
    payload=json.loads(raw.read_text())
    assert any(row['test_id']=='B101' for row in payload['results'])
    assert result.args[-1]=='/dev/stdout'

@pytest.mark.parametrize('size,limited',[(63,False),(64,False),(65,True),(1024*1024,True)])
def test_report_reads_and_raw_artifacts_are_bounded(tmp_path,monkeypatch,size,limited):
    monkeypatch.setattr(pipeline,'MAX_PARSE_BYTES',64)
    path=tmp_path/'raw';path.write_bytes(b'x'*size)
    blob=pipeline._raw_blob('synthetic',path,'txt')
    assert blob['capture_truncated'] is limited
    assert blob['source_bytes']==(None if limited else size)
    assert blob['source_bytes_lower_bound']==(65 if limited else size)
    assert gzip.decompress(bytes.fromhex(blob['gzip_hex']))==b'x'*min(size,64)
    if limited:
        with pytest.raises(ValueError,match='bounded read'):
            pipeline._read_text(path)
    value,reason=pipeline._read_json(path)
    assert value is None
    if limited:assert 'bounded parse limit' in reason


def test_valid_json_prefix_cannot_qualify_oversized_report(tmp_path,monkeypatch):
    monkeypatch.setattr(pipeline,'MAX_PARSE_BYTES',2)
    path=tmp_path/'raw';path.write_bytes(b'[] '+b'x'*100)
    assert pipeline._read_json(path)[0] is None
    blob=pipeline._raw_blob('synthetic',path,'json')
    monkeypatch.setattr(pipeline,'_scanner_version',lambda *a:'synthetic')
    monkeypatch.setattr('nico.scanner_execution_receipt_v1.native_coverage_observation',lambda *a:{})
    row=pipeline._tool_payload(pipeline.ScannerToolSpec('synthetic',('synthetic',),'static'),
        worker.WorkerCommandResult(('synthetic',),0,'[]',''),findings=[],capture_complete=True,
        reason='',raw_blob=blob,execution_source='synthetic',workspace=worker.WorkerWorkspace(tmp_path))
    assert row['status']=='failed' and not row['verified_for_this_report']
    assert not row['raw_artifact_capture_complete'] and not row['output_capture_complete']
    assert row['reason']=='native_report_read_limit_exceeded'

@pytest.mark.parametrize('binary,flag',[('other','-o'),('bandit','--report-path'),('gitleaks','--other')])
def test_native_redirect_rejects_unsupported_contract(tmp_path,binary,flag):
    with pytest.raises(ValueError,match='unsupported native'):
        worker.run_command([binary,flag,str(tmp_path/'raw')],cwd=tmp_path,
           limits=worker.WorkerLimits(native_report_flag=flag))

@pytest.mark.parametrize('limit',[-2,0,True,1.5])
def test_invalid_read_limit_fails_before_open(tmp_path,monkeypatch,limit):
    monkeypatch.setattr(pipeline,'MAX_PARSE_BYTES',limit)
    def forbidden(*a,**k):raise AssertionError('invalid cap opened report')
    monkeypatch.setattr(Path,'open',forbidden)
    with pytest.raises(ValueError,match='positive integer'):
        pipeline._read_report_bytes(tmp_path/'report')


def test_git_acquisition_preserves_local_result_and_stops_timeout(tmp_path):
    from nico import snapshot_scanner_worker as snapshot
    import subprocess
    result=snapshot._git(['git','init','--quiet',str(tmp_path/'repo')],cwd=tmp_path,env={},timeout=5)
    assert isinstance(result,subprocess.CompletedProcess) and result.returncode==0
    assert isinstance(result.stdout,str) and isinstance(result.stderr,str)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        snapshot._git([sys.executable,'-c',"import time;print('partial',flush=True);time.sleep(8)"],
                      cwd=tmp_path,env={},timeout=.1)
    assert caught.value.output==b'partial\n'


def test_git_output_limit_cannot_be_success_and_env_is_forwarded(tmp_path,monkeypatch):
    from nico import snapshot_scanner_worker as snapshot
    observed=[]
    def runner(command,**kwargs):
        observed.append(kwargs)
        return worker.WorkerCommandResult(tuple(command),125,'partial','',output_limit_exceeded=True,output_truncated=True)
    monkeypatch.setattr(snapshot,'run_command',runner)
    env={'GIT_TERMINAL_PROMPT':'0','GIT_ASKPASS':'synthetic-helper'}
    result=snapshot._git(['git','status'],cwd=tmp_path,env=env,timeout=3)
    assert result.returncode==125 and result.stdout=='partial' and 'bounded capture' in result.stderr
    assert observed[0]['extra_env']==env and observed[0]['limits'].timeout_seconds==3


def test_authoritative_bandit_json_path_uses_live_capture(tmp_path,monkeypatch):
    from nico import bandit_json_execution_v61 as bandit
    binary=Path(sys.executable).parent/'bandit'
    original=bandit.shutil.which
    monkeypatch.setattr(bandit.shutil,'which',lambda name: str(binary) if name=='bandit' else original(name))
    repo=tmp_path/'repo';repo.mkdir();(repo/'app.py').write_text('assert True\n')
    row=bandit.run_bandit_json(pipeline.ScannerToolSpec('bandit',('bandit',),'static'),
          worker.WorkerWorkspace(tmp_path),worker.run_command)
    assert row['status']=='completed' and row['output_capture_complete']
    assert row['execution_source']=='canonical_bandit_json_v62'
    assert any(finding['test_id']=='B101' for finding in row['findings'])
    assert (tmp_path/'scanner-raw'/'bandit.json').stat().st_size < 20*1024*1024

@pytest.mark.parametrize('code,timed_out,limited,observed,normalized',[
    (0,False,False,True,True),(1,False,False,True,False),
    (124,True,False,True,False),(125,False,True,True,False),
    (0,False,False,False,False),(0,True,False,True,False),
    (0,False,True,True,False),
])
def test_gitleaks_absent_report_normalization_is_qualified(tmp_path,monkeypatch,code,timed_out,limited,observed,normalized):
    monkeypatch.setattr(pipeline.shutil,'which',lambda name:'/tools/'+name)
    monkeypatch.setattr(pipeline,'_history_metadata',lambda _: {'full_history_verified':True})
    monkeypatch.setattr(pipeline,'_scanner_version',lambda *a:'8.30.1')
    (tmp_path/'repo').mkdir()
    def runner(args,**kwargs):
        return worker.WorkerCommandResult(tuple(args),code,'','',timed_out=timed_out,
                    output_limit_exceeded=limited,execution_observed=observed)
    row=pipeline._run_gitleaks(pipeline.ScannerToolSpec('gitleaks',('gitleaks',),'secret',scans_git_history=True),
                                worker.WorkerWorkspace(tmp_path),runner)
    assert row['empty_report_normalized'] is normalized
    assert row['verified_for_this_report'] is normalized
    if not normalized:assert row['status']!='completed'

@pytest.mark.parametrize('content,qualified',[(b'',False),(b'[]\n',True)])
def test_gitleaks_existing_capture_requires_valid_json(tmp_path,monkeypatch,content,qualified):
    monkeypatch.setattr(pipeline.shutil,'which',lambda name:'/tools/'+name)
    monkeypatch.setattr(pipeline,'_history_metadata',lambda _: {'full_history_verified':True})
    monkeypatch.setattr(pipeline,'_scanner_version',lambda *a:'8.30.1')
    (tmp_path/'repo').mkdir()
    def runner(args,**kwargs):
        (tmp_path/'scanner-raw'/'gitleaks.json').write_bytes(content)
        return worker.WorkerCommandResult(tuple(args),0,'','')
    row=pipeline._run_gitleaks(pipeline.ScannerToolSpec('gitleaks',('gitleaks',),'secret',scans_git_history=True),
                                worker.WorkerWorkspace(tmp_path),runner)
    assert row['empty_report_normalized'] is False
    assert row['verified_for_this_report'] is qualified
    if not qualified:assert row['status']!='completed'
