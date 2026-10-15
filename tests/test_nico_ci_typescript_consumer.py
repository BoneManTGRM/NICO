"""Owned transcripts only: canonical consumer must never execute project code."""
import copy
from datetime import datetime, timezone
import gzip
import json

import pytest
from test_nico_ci_typescript_github import api
from test_nico_ci_typescript_evidence import project, retained
from nico import nico_ci_typescript_consumer_v1 as consumer
from nico import scanner_evidence_pipeline_v1 as pipeline
from nico.worker_execution import WorkerWorkspace

NOW = datetime(2026, 10, 15, 11, tzinfo=timezone.utc)
SPEC = next(s for s in pipeline.TOOL_SPECS if s.name == 'typescript')


def setup_capture(api, monkeypatch):
    client, responses, archive, _ = api
    responses['/actions/workflows/node.js.yml/runs'] = copy.deepcopy(responses['/actions/workflows/9/runs'])
    responses['/actions/runs/123/artifacts'] = {'total_count': 1, 'artifacts': [copy.deepcopy(responses['/actions/artifacts/7'])]}
    monkeypatch.setattr(consumer.Capture, 'archive', lambda self, artifact_id: archive)
    return client, responses


def test_real_importer_acceptance_and_shared_budget(api, monkeypatch):
    client, _ = setup_capture(api, monkeypatch)
    result, archive = consumer.collect(client, 'b'*40, 300, now=NOW)
    assert result['status'] == 'completed' and result['metadata_authenticated'] is True
    assert archive == api[2]
    with pytest.raises(ValueError, match='provider_capture_budget'):
        consumer.collect(client, 'b'*40, 0, now=NOW)


@pytest.mark.parametrize('damage', ['historical','wrong_source','wrong_workflow','missing','duplicate','expired','oversize','incomplete_listing','failed','wrong_digest','anonymous'])
def test_consumer_negative_cases(api, monkeypatch, damage):
    client, responses = setup_capture(api, monkeypatch)
    if damage == 'historical': responses['/git/ref/heads/main']['object']['sha'] = 'c'*40
    elif damage == 'wrong_source': responses['/actions/workflows/node.js.yml/runs']['workflow_runs'][0]['head_sha'] = 'c'*40
    elif damage == 'wrong_workflow': responses['/actions/workflows/9']['path'] = 'untrusted.yml'
    elif damage == 'missing': responses['/actions/runs/123/artifacts'] = {'total_count':0,'artifacts':[]}
    elif damage == 'duplicate':
        listing = responses['/actions/runs/123/artifacts']; listing['artifacts'] *= 2; listing['total_count'] = 2
    elif damage == 'expired': responses['/actions/runs/123/artifacts']['artifacts'][0]['expired'] = True
    elif damage == 'oversize': responses['/actions/runs/123/artifacts']['artifacts'][0]['size_in_bytes'] = 3*consumer.MAX_BYTES+1
    elif damage == 'incomplete_listing': responses['/actions/runs/123/artifacts']['total_count'] = 101
    elif damage == 'failed': responses['/actions/workflows/node.js.yml/runs']['workflow_runs'][0]['status'] = 'in_progress'
    elif damage == 'wrong_digest': responses['/actions/artifacts/7']['digest'] = 'sha256:'+'0'*64
    elif damage == 'anonymous': client.auth_mode = 'anonymous'
    try:
        result, _ = consumer.collect(client, 'b'*40, 300, now=NOW)
    except ValueError:
        return
    assert result['status'] != 'completed'


def bomb(*args, **kwargs):
    raise AssertionError('project execution forbidden')


@pytest.mark.parametrize('clean', [True, False])
def test_canonical_disabled_policy_retention_and_ledger(api, monkeypatch, tmp_path, clean):
    client, _ = setup_capture(api, monkeypatch)
    real_collect = consumer.collect
    # Real importer establishes acceptance first; projection adds a separately
    # tested diagnostic fixture, never claiming this modified record is authentic.
    result, archive = real_collect(client, 'b'*40, 300, now=NOW)
    if not clean:
        result.update(clean=False, diagnostics=[{'code':2322,'category':'Error','message':'owned mismatch','file':'apps/web/sample.ts','line':1}])
    monkeypatch.setattr(consumer, '_capture_bounded', lambda *args, **kwargs: (result, archive))
    monkeypatch.setattr(consumer.authority, '_new_client', lambda: client)
    monkeypatch.setattr(pipeline, '_git_text', lambda workspace, *args: 'BoneManTGRM/NICO' if args[0]=='config' else 'b'*40)
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'false')
    workspace = WorkerWorkspace(tmp_path)
    payload = pipeline._run_typescript(SPEC, workspace, bomb, None)
    assert payload['status'] == 'completed'
    assert payload['clean'] is clean
    assert payload['score_override'] is False
    assert payload['execution_observed_for_this_report'] is False
    assert 'scanner_execution_receipt' not in payload
    assert payload['findings_count'] == (0 if clean else 1)
    raw = json.loads(gzip.decompress(bytes.fromhex(payload['_raw_artifact_blob']['gzip_hex'])))
    assert set(raw['members']) == {'manifest.json','typescript.json','typescript.log'}
    from nico.evidence_ledger import _scanner_artifact_entries
    entry, = _scanner_artifact_entries({'scanner_artifacts':{'tools':{'typescript':payload}}}, 'owned-report')
    assert entry['commit_sha'] == 'b'*40 and entry['verified_for_this_report'] is True
    assert entry['findings_count'] == (0 if clean else 1)


def test_non_nico_does_not_use_ci(api, monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, '_target_repository', lambda w: 'other/repository')
    monkeypatch.setattr(consumer, 'collect', bomb)
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'false')
    assert pipeline._run_typescript(SPEC, WorkerWorkspace(tmp_path), bomb, None)['status'] == 'unavailable'


class Response:
    def __init__(self, code, headers=None, chunks=()):
        self.status_code=code; self.headers=headers or {}; self.chunks=chunks
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size): return iter(self.chunks)


@pytest.mark.parametrize('location', ['http://owned.blob.core.windows.net/x','https://evil.example/x','https://user:pass@owned.blob.core.windows.net/x','https://owned.blob.core.windows.net:444/x'])
def test_invalid_redirect_never_receives_credentials(api, monkeypatch, location):
    calls=[]
    def get(url, **kwargs):
        calls.append((url,kwargs)); return Response(302, {'Location':location})
    monkeypatch.setattr(consumer.requests, 'get', get)
    with pytest.raises(ValueError, match='artifact_redirect_invalid'):
        consumer.Capture(api[0], 300).archive(7)
    assert len(calls) == 1


def test_download_strips_auth_caps_bytes_and_does_not_follow_redirects(api, monkeypatch):
    calls=[]
    def get(url, **kwargs):
        calls.append((url,kwargs))
        return Response(302, {'Location':'https://owned.blob.core.windows.net/x'}) if len(calls)==1 else Response(200, chunks=[b'a'*(3*consumer.MAX_BYTES),b'b'])
    monkeypatch.setattr(consumer.requests, 'get', get)
    with pytest.raises(ValueError, match='archive_budget_exceeded'):
        consumer.Capture(api[0], 300).archive(7)
    assert 'Authorization' not in calls[1][1]['headers']
    assert all(c[1]['allow_redirects'] is False for c in calls)


def test_retained_limits_counts_and_diagnostic_scope(api, monkeypatch, tmp_path):
    client, _ = setup_capture(api, monkeypatch)
    result, archive = consumer.collect(client, 'b'*40, 300, now=NOW)
    diagnostics = [
        {'code':2322,'category':'Error','file':'apps/web/a.ts','start':3,'length':1,'message':'first\n  second','related':[]},
        {'code':18003,'category':'Error','file':None,'start':None,'length':None,'message':'project diagnostic','related':[]},
        {'code':1234,'category':'Warning','file':None,'message':'warning','related':[]},
    ]
    result.update(clean=False, diagnostics=diagnostics)
    monkeypatch.setattr(consumer, '_capture_bounded', lambda *a: (result, archive))
    monkeypatch.setattr(pipeline, '_git_text', lambda *a: 'b'*40)
    payload = consumer.run(SPEC, WorkerWorkspace(tmp_path))
    assert [f['message'] for f in payload['findings']] == [d['message'] for d in diagnostics]
    assert [f['diagnostic_scope'] for f in payload['findings']] == ['file','project','project']
    from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact
    normalized = normalize_scanner_worker_artifact({'tools':{'typescript':payload}})
    assert normalized['static_finding_count'] == 3
    for key in ('configuration_limitations','effective_configuration','checked_project_scope'):
        assert normalized['tools']['typescript'][key] == result[key]
    from nico.scanner_artifact_scoring import _typescript_count
    assert _typescript_count(payload) == 3
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    payload['raw_artifact_retention_complete'] = True
    record, = compact_scanner_records({'scan_id':'owned','scanner_results':[payload]},commit_sha='b'*40)
    assert record['status'] == 'completed_with_findings' and record['finding_count'] == 3
    assert record['verified_complete'] is True
    for key in ('configuration_limitations','effective_configuration','checked_project_scope'):
        assert record[key] == result[key]
    assert record['configuration_limitations']['declaration_semantics_checked'] is False
    assert record['configuration_limitations']['javascript_semantics_checked'] is False
    assert record['current_run'] is False


def test_retention_decodes_encoded_stderr_before_redaction():
    import base64
    from nico.scanner_evidence_pipeline_v1 import redact_text
    secret = 'ghp_'+'A'*36
    assert secret not in redact_text(secret)
    encoded = base64.b64encode(secret.encode()).decode()
    projected = consumer._retention_projection({'native_stderr_base64':encoded,'native_stderr_sha256':'a'*64})
    assert secret not in str(projected) and encoded not in str(projected)
    assert projected['native_stderr_sha256'] == 'a'*64


def test_controller_process_is_bounded_and_does_not_receive_project_cwd(monkeypatch, tmp_path):
    import subprocess
    calls=[]
    def execute(args, **kwargs):
        calls.append((args,kwargs))
        assert args[:3] == (consumer.sys.executable,'-m','nico.nico_ci_typescript_consumer_v1')
        assert kwargs['cwd'] == consumer.authority.ROOT
        assert kwargs['timeout'] == 300 and kwargs['shell'] is False
        assert 'env' not in kwargs  # ordinary controller environment, no argv credentials
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])
    monkeypatch.setattr(consumer.subprocess, 'run', execute)
    with pytest.raises(subprocess.TimeoutExpired): consumer._capture_bounded('b'*40, 900)
    monkeypatch.setattr(pipeline, '_git_text', lambda *a: 'b'*40)
    payload = consumer.run(SPEC, WorkerWorkspace(tmp_path))
    assert payload['status'] == 'unavailable' and payload['verified_for_this_report'] is False


@pytest.mark.parametrize('incomplete', [False, True])
def test_authentic_owned_failure_through_consumer_and_retention(api, retained, monkeypatch, tmp_path, incomplete):
    from test_nico_ci_typescript_github import failed_check, replace_archive
    from test_nico_ci_typescript_evidence import revise
    def change(record, native):
        for value in (record,native):
            value.update(clean=False,diagnostics=[{'code':2322,'category':'Error','message':'first\n  explanation','file':None}],diagnostics_text='first\n  explanation')
        record['raw_exit_code']=1
        if incomplete:
            record.update(status='incomplete',capture_complete=False,reason='capture_incomplete',capture_truncated=True)
            native.clear()
    archive,_ = revise(retained, change)
    failed_check(api)
    api = replace_archive(api, archive)
    client,_ = setup_capture(api, monkeypatch)
    result, verified_archive = consumer.collect(client, 'b'*40, 300, now=NOW)
    assert result['metadata_authenticated'] is True
    monkeypatch.setattr(consumer,'_capture_bounded',lambda *a:(result,verified_archive))
    monkeypatch.setattr(pipeline,'_git_text',lambda *a:'b'*40)
    payload = consumer.run(SPEC,WorkerWorkspace(tmp_path))
    assert payload['status'] == ('unavailable' if incomplete else 'completed')
    assert payload['verified_for_this_report'] is (not incomplete)
    retained_raw=json.loads(gzip.decompress(bytes.fromhex(payload['_raw_artifact_blob']['gzip_hex'])))
    assert retained_raw['members']['typescript.json']['diagnostics'][0]['message']=='first\n  explanation'
    if not incomplete:
        from nico.scanner_artifact_scoring import _typescript_count
        assert _typescript_count(payload)==1
        assert payload['findings'][0]['diagnostic_scope']=='project'
    else:
        assert payload['ci_evidence']['retained_failure']['capture_truncated'] is True


@pytest.mark.parametrize('enabled',[False,True])
def test_canonical_entry_points_skip_owned_project_preparation(monkeypatch,tmp_path,enabled):
    from nico import v2_snapshot_scanner_authority as snapshot
    workspace=WorkerWorkspace(tmp_path); workspace.repo_dir.mkdir()
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS',str(enabled).lower())
    monkeypatch.setattr(pipeline,'_owned_nico_ci',lambda w:True)
    monkeypatch.setattr(pipeline,'_git_text',lambda *a:'b'*40)
    monkeypatch.setattr(pipeline,'prepare_project_commands',bomb)
    monkeypatch.setattr(snapshot,'_preparation',bomb)
    monkeypatch.setattr(pipeline,'node_inapplicability_result',lambda *a:None)
    monkeypatch.setattr(pipeline,'verify_source_checkout',lambda payload,*a:payload)
    monkeypatch.setattr(consumer,'run',lambda spec,w:pipeline._unavailable(spec,'owned no evidence',source='authenticated_nico_postbuild_ci'))
    result=pipeline.run_canonical_scanner_tools(workspace,(SPEC,),runner=bomb)
    assert result['tools']['typescript']['status']=='unavailable'
    result=snapshot.canonical_snapshot_tool_runner(SPEC,workspace,runner=bomb)
    assert result['status']=='unavailable'


def test_actual_controller_child_environment_and_timeout(monkeypatch,tmp_path):
    import subprocess
    import time
    package=tmp_path/'nico'; package.mkdir(); (package/'__init__.py').write_text('')
    child=package/'nico_ci_typescript_consumer_v1.py'
    child.write_text("import os,sys,json,pathlib\np=pathlib.Path(sys.argv[3])\n(p/'result.json').write_text(json.dumps({'owned_marker':os.environ['NICO_OWNED_TEST_MARKER']}))\n(p/'archive.zip').write_bytes(b'owned')\n")
    monkeypatch.setattr(consumer.authority,'ROOT',tmp_path)
    monkeypatch.setenv('NICO_OWNED_TEST_MARKER','owned-no-credential')
    result,archive=consumer._capture_bounded('b'*40,5)
    assert result=={'owned_marker':'owned-no-credential'} and archive==b'owned'
    child.write_text('import time\ntime.sleep(30)\n')
    started=time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired): consumer._capture_bounded('b'*40,0.2)
    assert time.monotonic()-started < 3
