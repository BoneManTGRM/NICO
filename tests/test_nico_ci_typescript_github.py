"""Owned API transcripts; no network, credentials, build, or target execution."""
import base64
import copy
import hashlib
from datetime import datetime, timezone

import pytest
from test_nico_ci_typescript_evidence import ROOT, project, retained, revise, sha


@pytest.fixture
def api(retained,project):
    module,contents,archive,context=retained
    repository={'id':42,'full_name':module.REPOSITORY}
    run={'id':123,'run_attempt':2,'head_sha':'b'*40,'head_branch':'main','event':'push',
         'status':'completed','conclusion':'success','workflow_id':9,'path':module.WORKFLOW,
         'repository':repository,'head_repository':repository,
         'run_started_at':'2026-10-15T10:00:00Z','updated_at':'2026-10-15T10:10:00Z'}
    artifact={'id':7,'name':context.artifact_name,'digest':context.artifact_digest,'expired':False,
              'size_in_bytes':len(archive),'created_at':'2026-10-15T10:09:00Z',
              'workflow_run':{'id':123,'repository_id':42,'head_repository_id':42,'head_sha':'b'*40,'head_branch':'main'}}
    steps=[{'name':name,'status':'completed','conclusion':'success'} for name in
           ['Checkout repo','Build frontend','Retain post-build TypeScript evidence','Upload exact-run TypeScript evidence']]
    job={'name':'Frontend validation','run_id':123,'head_sha':'b'*40,'status':'completed','steps':steps}
    responses={'':repository,'/git/ref/heads/main':{'object':{'sha':'b'*40}},
        '/actions/runs/123':run,'/actions/runs/123/attempts/2':copy.deepcopy(run),
        '/actions/workflows/9':{'id':9,'path':module.WORKFLOW,'state':'active'},
        '/actions/workflows/9/runs':{'total_count':1,'workflow_runs':[copy.deepcopy(run)]},
        '/actions/runs/123/attempts/2/jobs':{'total_count':1,'jobs':[job]},
        '/actions/artifacts/7':artifact,'/git/commits/'+'b'*40:{'sha':'b'*40,'tree':{'sha':'c'*40}}}
    tree=[]
    for path,digest in context.source_inventory.items():
        raw=(project/path).read_bytes() if path.startswith('apps/web/') else (ROOT/path).read_bytes()
        assert sha(raw)==digest
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        tree.append({'path':path,'mode':'100644','type':'blob','sha':blob,'size':len(raw)})
        responses['/git/blobs/'+blob]={'sha':blob,'encoding':'base64','size':len(raw),'content':base64.b64encode(raw).decode()}
    responses['/git/trees/'+'c'*40]={'sha':'c'*40,'truncated':False,'tree':tree}
    class Client:
        auth_mode='github_app_installation'
        headers={'Authorization':'Bearer owned-fixture-not-a-secret'}
        def __init__(self): self.calls=[]
        def get_json(self,url,params=None):
            prefix='https://api.github.com/repos/'+module.REPOSITORY
            assert url.startswith(prefix)
            suffix=url[len(prefix):]; self.calls.append((suffix,params))
            return copy.deepcopy(responses[suffix]),None
    return Client(),responses,archive,context


def invoke(api):
    from nico.nico_ci_typescript_github_v1 import _import_with_client
    client,_,archive,_=api
    return _import_with_client(client,archive,target_sha='b'*40,run_id='123',run_attempt='2',artifact_id='7',
                               now=datetime(2026,10,15,11,tzinfo=timezone.utc))


def test_independently_authenticated_fixture_import(api):
    result=invoke(api)
    assert result['status']=='completed' and result['clean'] is True
    assert result['production_scanner_integrated'] is False
    assert result['build_outcome']=='success'
    assert len(api[0].calls)>10


def test_observed_run_attempt_timestamps_are_not_shared_identity(api):
    import json
    from nico import nico_ci_typescript_github_v1 as module
    observed=json.loads((ROOT/'tests/fixtures/nico_ci_typescript_run_attempt_timestamps.json').read_text())
    client,responses,archive,_=api
    # Replay real endpoint timestamps within the owned synthetic archive fixture.
    # This is not an authentication claim for the production archive.
    for path,key in [('/actions/runs/123','run'),('/actions/runs/123/attempts/2','attempt')]:
        for field in ('run_started_at','updated_at'):
            responses[path][field]=observed[key][field]
    responses['/actions/artifacts/7']['created_at']='2026-10-16T12:41:00Z'
    result=module._import_with_client(client,archive,target_sha='b'*40,run_id='123',
        run_attempt='2',artifact_id='7',now=datetime(2026,10,17,tzinfo=timezone.utc))
    assert result['status']=='completed', result
    assert result['metadata_authenticated'] is True and result['score_override'] is False


@pytest.mark.parametrize('updated',['2026-10-15T10:09:59Z','2026-10-15T10:10:01Z'])
def test_attempt_has_independent_update_timestamp(api,updated):
    api[1]['/actions/runs/123/attempts/2']['updated_at']=updated
    assert invoke(api)['status']=='completed'


@pytest.mark.parametrize('updated',[None,'invalid','2026-10-15T10:10:01',
    '2026-10-15T09:59:59Z','2026-10-15T11:00:01Z','2026-10-01T10:10:00Z'])
def test_invalid_attempt_timestamp_rejected(api,updated):
    api[1]['/actions/runs/123/attempts/2']['updated_at']=updated
    assert invoke(api)['status']=='incomplete'


@pytest.mark.parametrize('endpoint,reason',[
    ('/actions/runs/123','run_changed_during_capture'),
    ('/actions/runs/123/attempts/2','attempt_changed_during_capture')])
def test_same_endpoint_update_changes_during_capture_rejected(api,endpoint,reason):
    client=api[0]; original=client.get_json; reads=0
    def changing(url,params=None):
        nonlocal reads
        value,error=original(url,params)
        if url.endswith(endpoint):
            reads+=1
            if reads==2: value['updated_at']='2026-10-15T10:10:01Z'
        return value,error
    client.get_json=changing
    result=invoke(api)
    assert result['status']=='incomplete' and result['reason']==reason


@pytest.mark.parametrize('damage',['repository','main_sha','run_sha','workflow','workflow_revision','attempt','latest_run',
    'artifact_digest','artifact_repo','artifact_run','artifact_sha','artifact_name','artifact_expired',
    'stale_time','artifact_old_attempt','jobs_truncated','checkout_failure','tree_truncated','blob_corrupt','untrusted_client'])
def test_provider_substitutions_fail_closed(api,damage):
    client,responses,_,_=api
    run=responses['/actions/runs/123']; artifact=responses['/actions/artifacts/7']
    if damage=='repository': responses['']['full_name']='attacker/repo'
    elif damage=='main_sha': responses['/git/ref/heads/main']['object']['sha']='d'*40
    elif damage=='run_sha': run['head_sha']='d'*40
    elif damage=='workflow': responses['/actions/workflows/9']['path']='.github/workflows/other.yml'
    elif damage=='workflow_revision': run['path']+="@refs/heads/other"
    elif damage=='attempt': run['run_attempt']=3
    elif damage=='latest_run': responses['/actions/workflows/9/runs']['workflow_runs'][0]['id']=124
    elif damage=='artifact_digest': artifact['digest']='sha256:'+'0'*64
    elif damage=='artifact_repo': artifact['workflow_run']['repository_id']=43
    elif damage=='artifact_run': artifact['workflow_run']['id']=124
    elif damage=='artifact_sha': artifact['workflow_run']['head_sha']='d'*40
    elif damage=='artifact_name': artifact['name']='forged'
    elif damage=='artifact_expired': artifact['expired']=True
    elif damage=='stale_time': run['updated_at']='2026-10-01T10:10:00Z'
    elif damage=='artifact_old_attempt': artifact['created_at']='2026-10-15T09:59:59Z'
    elif damage=='jobs_truncated': responses['/actions/runs/123/attempts/2/jobs']['total_count']=101
    elif damage=='checkout_failure': responses['/actions/runs/123/attempts/2/jobs']['jobs'][0]['steps'][0]['conclusion']='failure'
    elif damage=='tree_truncated': responses['/git/trees/'+'c'*40]['truncated']=True
    elif damage=='blob_corrupt': next(v for k,v in responses.items() if k.startswith('/git/blobs/'))['content']='Zm9yZ2Vk'
    elif damage=='untrusted_client': client.auth_mode='anonymous'
    result=invoke(api)
    assert result['status']=='incomplete' and result['clean'] is False
    assert result['reason']


def replace_archive(api,archive):
    client,responses,_,context=api
    artifact=responses['/actions/artifacts/7']; artifact.update(digest='sha256:'+sha(archive),size_in_bytes=len(archive))
    return client,responses,archive,context


def failed_check(api):
    responses=api[1]
    for path in ['/actions/runs/123','/actions/runs/123/attempts/2']:
        responses[path]['conclusion']='failure'
    responses['/actions/runs/123/attempts/2/jobs']['jobs'][0]['steps'][2]['conclusion']='failure'


def test_completed_failure_preserves_diagnostics(api,retained):
    def change(record,native):
        for value in (record,native):
            value.update(clean=False,diagnostics=[{'code':2322,'category':'Error','message':'owned error'}],diagnostics_text='owned error')
        record['raw_exit_code']=1
    archive,_=revise(retained,change); failed_check(api)
    result=invoke(replace_archive(api,archive))
    assert result['status']=='completed' and result['clean'] is False
    assert result['diagnostics'][0]['code']==2322


def test_authenticated_incomplete_retains_failure_evidence(api,retained):
    def change(record,native):
        record.update(status='incomplete',clean=False,capture_complete=False,reason='capture_incomplete',
                      capture_truncated=True,diagnostics=[{'code':2322,'category':'Error','message':'owned partial diagnostic'}])
        native.clear()
    archive,_=revise(retained,change); failed_check(api)
    result=invoke(replace_archive(api,archive))
    assert result['status']=='incomplete' and result['clean'] is False
    assert result['metadata_authenticated'] is True
    assert result['retained_failure']['diagnostics'][0]['code']==2322
    assert result['retained_failure']['capture_truncated'] is True


@pytest.mark.parametrize('damage',['generated_missing','config_changed','diagnostic_changed','native_empty'])
def test_authenticated_artifact_still_requires_valid_captured_evidence(api,retained,damage):
    def change(record,native):
        if damage=='native_empty': native.clear(); return
        for value in (record,native):
            if damage=='generated_missing': value['generated_inputs']=[]
            elif damage=='config_changed': value['configuration_sha256']='0'*64
            else: value['diagnostics']=[{'code':2322,'category':'Error','message':'hidden error'}]
    archive,_=revise(retained,change)
    assert invoke(replace_archive(api,archive))['status']=='incomplete'


def test_untrusted_metadata_cannot_enter_public_api(monkeypatch):
    from nico import nico_ci_typescript_github_v1 as module
    monkeypatch.setattr(module,'_new_client',lambda: {'auth_mode':'server_token','status':'success'})
    result=module.import_current_nico_ci_evidence(b'owned',target_sha='b'*40,run_id='123',run_attempt='2',artifact_id='7')
    assert result['status']=='incomplete' and result['reason']=='authenticated_github_client_required'


@pytest.mark.parametrize('endpoint',['/git/ref/heads/main','/actions/runs/123','/actions/artifacts/7'])
def test_metadata_changes_during_capture_rejected(api,endpoint):
    client=api[0]; original=client.get_json; count=0
    def changing(url,params=None):
        nonlocal count
        data,error=original(url,params)
        if url.endswith(endpoint):
            count+=1
            if count==2:
                if endpoint.endswith('main'): data['object']['sha']='d'*40
                elif endpoint.endswith('123'): data['run_attempt']=3
                else: data['expired']=True
        return data,error
    client.get_json=changing
    assert invoke(api)['status']=='incomplete'


def test_valid_git_blob_with_unreviewed_workflow_rejected(api):
    responses=api[1]
    row=next(r for r in responses['/git/trees/'+'c'*40]['tree'] if r['path'].endswith('node.js.yml'))
    raw=b'name: forged workflow\n'; digest=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    row.update(sha=digest,size=len(raw))
    responses['/git/blobs/'+digest]={'sha':digest,'size':len(raw),'encoding':'base64','content':base64.b64encode(raw).decode()}
    assert invoke(api)['reason']=='workflow_or_exporter_not_reviewed'


def test_provider_denial_is_incomplete_without_leaking_error_text(api):
    client=api[0]
    client.get_json=lambda *args:(None,'403 secret-token-should-not-appear')
    result=invoke(api)
    assert result['reason']=='github_read_unavailable'
    assert 'secret-token' not in str(result)


def test_truncated_native_bytes_remain_authenticated_failure(api,retained):
    import json
    from test_nico_ci_typescript_evidence import pack
    def change(record,native):
        record.update(status='incomplete',clean=False,capture_complete=False,reason='capture_incomplete',capture_truncated=True)
    archive,_=revise(retained,change)
    import io,zipfile
    with zipfile.ZipFile(io.BytesIO(archive)) as z: contents={n:z.read(n) for n in z.namelist()}
    contents['typescript.log']=b'{"partial":'
    record=json.loads(contents['typescript.json']); record['native_stdout_sha256']=sha(contents['typescript.log'])
    contents['typescript.json']=json.dumps(record).encode()
    manifest=json.loads(contents['manifest.json']); manifest['files']={p:sha(contents[p]) for p in ('typescript.json','typescript.log')}
    contents['manifest.json']=json.dumps(manifest).encode(); failed_check(api)
    result=invoke(replace_archive(api,pack(contents)))
    assert result['status']=='incomplete' and result['metadata_authenticated'] is True
    assert result['retained_failure']['capture_truncated'] is True


def test_final_provider_response_cannot_overrun_deadline(api,monkeypatch):
    from nico import nico_ci_typescript_github_v1 as module
    elapsed=[0]; count=0; original=api[0].get_json
    monkeypatch.setattr(module.time,'monotonic',lambda:elapsed[0])
    def delayed(url,params=None):
        nonlocal count
        data,error=original(url,params)
        if url.endswith('/actions/artifacts/7'):
            count+=1
            if count==2: elapsed[0]=601
        return data,error
    api[0].get_json=delayed
    result=invoke(api)
    assert result['status']=='incomplete' and result['reason']=='provider_capture_budget'


def test_git_object_id_compatibility_is_explicitly_nonsecurity(api,monkeypatch):
    import subprocess
    from nico import nico_ci_typescript_github_v1 as module
    original=hashlib.sha1; observed=[]
    def git_compatibility(data,*,usedforsecurity=True):
        assert usedforsecurity is False
        raw=data.split(b'\0',1)[1]
        expected=subprocess.run(['git','hash-object','--stdin'],input=raw,capture_output=True,check=True).stdout.decode().strip()
        result=original(data,usedforsecurity=False)
        assert result.hexdigest()==expected
        observed.append(expected)
        return result
    monkeypatch.setattr(module.hashlib,'sha1',git_compatibility)
    assert invoke(api)['status']=='completed'
    assert observed


@pytest.mark.parametrize('damage',['metadata_length','decoded_length','git_id'])
def test_git_blob_protocol_mismatch_still_rejected(api,damage):
    responses=api[1]; tree=responses['/git/trees/'+'c'*40]['tree']
    row=next(r for r in tree if r['path']=='apps/web/app.ts')
    blob=responses['/git/blobs/'+row['sha']]
    if damage=='metadata_length': blob['size']+=1
    elif damage=='decoded_length': row['size']+=1; blob['size']+=1
    else:
        wrong='f'*40; row['sha']=wrong; blob['sha']=wrong; responses['/git/blobs/'+wrong]=blob
    result=invoke(api)
    assert result['status']=='incomplete' and result['clean'] is False
    assert result['reason'] in {'blob_metadata_mismatch','blob_content_mismatch'}


def test_valid_git_id_cannot_replace_retained_sha256_content_binding(api):
    responses=api[1]; tree=responses['/git/trees/'+'c'*40]['tree']
    row=next(r for r in tree if r['path']=='apps/web/app.ts')
    old=base64.b64decode(responses['/git/blobs/'+row['sha']]['content'])
    raw=old.replace(b'=1',b'=2'); assert raw!=old and len(raw)==len(old)
    digest=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw,usedforsecurity=False).hexdigest()
    row.update(sha=digest,size=len(raw))
    responses['/git/blobs/'+digest]={'sha':digest,'size':len(raw),'encoding':'base64','content':base64.b64encode(raw).decode()}
    result=invoke(api)
    assert result['status']=='incomplete' and result['clean'] is False
    assert result['reason']=='source_inventory_mismatch'


@pytest.mark.parametrize('damage', ['missing', 'modified', 'intact'])
def test_packaged_controller_workflow_remains_required_and_hash_bound(api, tmp_path, monkeypatch, damage):
    from nico import nico_ci_typescript_github_v1 as adapter
    for relative in adapter.TRUSTED_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    workflow = tmp_path / adapter.WORKFLOW
    if damage == 'missing':
        workflow.unlink()
    elif damage == 'modified':
        workflow.write_bytes(workflow.read_bytes() + b'\n# changed controller bytes\n')
    monkeypatch.setattr(adapter, 'ROOT', tmp_path)
    result = invoke(api)
    if damage == 'intact':
        assert result['status'] == 'completed'
        assert result['clean'] is True
    else:
        assert result['status'] == 'incomplete'
        assert result['clean'] is False
        assert result['score_override'] is False
        assert result['reason'] == ('provider_evidence_invalid' if damage == 'missing'
                                    else 'workflow_or_exporter_not_reviewed')
