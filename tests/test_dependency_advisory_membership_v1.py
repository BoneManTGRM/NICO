from copy import deepcopy
import json
import pytest
from nico import dependency_advisory_membership_v1 as advisory
from nico import dependency_identity_evidence_v1 as dep
from nico.candidate_investigation_pipeline_v1 import investigate_register, display_investigation
from nico.comprehensive_native_providers_v5 import _normalized_record
from tests.test_dependency_identity_evidence_v1 import capture as lock_capture, SCOPE
from nico.scanner_raw_artifact_storage_v1 import _artifact_id


def raw(**changes):
    return {'id':'GHSA-demo-1234','package':'demo','ecosystem':'npm','installed_version':'1.2.3',
            'dependency_path':'package-lock.json','scanner_context_schema':'nico.osv-scanner-context-patch.v1',
            'affected':[{'package':{'name':'demo','ecosystem':'npm'},'versions':['1.2.3','2.0.0']}],**changes}


def normalized(value):
    return _normalized_record(commit_sha=SCOPE['commit_sha'],scanner='osv-scanner',category='dependency',finding=value)


def result(findings, scope=None):
    binding={**(scope or SCOPE),'scan_id':'synthetic-scan','scanner_name':'osv-scanner'}
    value={**binding,'status':'completed','category':'dependency','timed_out':False,'output_limit_exceeded':False,
           'output_capture_complete':True,'returncode_valid':True,'verified_for_this_report':True,'findings':findings,'raw_artifact_retention_complete':True,
           'raw_artifact_durability':{'status':'persisted','original_compressed_bytes_preserved':True},
           'raw_artifact':{'storage_backend':'postgres','artifact_id':_artifact_id(binding),'sha256':'a'*64}}
    value['artifact_hash']=advisory.digest(value)
    return value


def prepared(value=None):
    value=raw() if value is None else value
    row=normalized(value)
    retained=lock_capture([row])
    observations,charged,attempts=advisory.capture([result([value])],SCOPE,_normalized_record,deadline=5,clock=lambda:0)
    retained['dependency_advisory_observations']=observations
    return row,retained


def test_pipeline_roundtrip_positive_only_and_no_side_effects():
    row,retained=prepared(); before=deepcopy(row)
    register={'findings':[row]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    packet=display_investigation(register,SCOPE,trusted_capture=retained)['packets'][0]
    proof=packet['dependency_advisory_membership']
    assert proof['status']=='explicitly_listed' and proof['advisory_id']=='GHSA-demo-1234'
    assert proof['installed_affectedness']==proof['reachability']=='unknown'
    assert proof['disposition_effect']=='none' and not packet['completed']
    assert row==before and register['candidate_investigation']['client_delivery_allowed'] is False
    assert 'versions' not in proof


@pytest.mark.parametrize('change',[
 {'affected':[{'package':{'name':'demo','ecosystem':'npm'},'versions':['1.2.30']}]},
 {'affected':[{'package':{'name':'other','ecosystem':'npm'},'versions':['1.2.3']}]},
 {'affected':[{'package':{'name':'demo','ecosystem':'PyPI'},'versions':['1.2.3']}]},
 {'affected':[{'package':{'name':'demo','ecosystem':'npm'},'ranges':[{'type':'SEMVER'}]}]},
 {'affected':[{'package':{'name':'demo','ecosystem':'npm'},'versions':['1.2.3',None]}]},
 {'affected':[{'package':{'name':'demo','ecosystem':'npm'},'versions':['1.2.3','1.2.3']}]},
 {'affected':[]}, {'withdrawn':'2026-01-01'}, {'scanner_context_schema':'legacy'},
 {'id':'bad\ntext'}, {'affected':[{'package':{'name':'demo','ecosystem':'npm'},'versions':['1.2.3']}]*2},
])
def test_no_negative_clearance_from_missing_nonmatching_or_unsupported(change):
    row,retained=prepared(raw(**change)); register={'findings':[row]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    assert 'dependency_advisory_membership' not in register['candidate_investigation']['packets'][0]
    assert row['human_review_required'] and register['candidate_investigation']['client_delivery_allowed'] is False


@pytest.mark.parametrize('field',list(SCOPE))
def test_scope_mismatch(field):
    row,retained=prepared(); scope={**SCOPE,field:'foreign'}
    assert 'dependency_advisory_membership' not in investigate_register({'findings':[row]},retained,scope)['packets'][0]


def test_result_integrity_and_retention_required():
    r=result([raw()]); r['findings'][0]['affected'][0]['versions'].append('3.0.0')
    assert advisory.capture([r],SCOPE,_normalized_record,deadline=5,clock=lambda:0)[0]=={}
    r=result([raw()]);r['raw_artifact_retention_complete']=False;r['artifact_hash']=advisory.digest({k:v for k,v in r.items() if k!='artifact_hash'})
    assert advisory.capture([r],SCOPE,_normalized_record,deadline=5,clock=lambda:0)[0]=={}


def test_conflicting_same_claim_and_truncated_population_fail_closed():
    second=raw(affected=[{'package':{'name':'demo','ecosystem':'npm'},'versions':['1.0.0']}])
    assert advisory.capture([result([raw(),second])],SCOPE,_normalized_record,deadline=5,clock=lambda:0)[0]=={}
    assert advisory.capture([result([raw()]*129)],SCOPE,_normalized_record,deadline=5,clock=lambda:0)[0]=={}
    assert advisory.capture([result([raw()]),result([raw()])],SCOPE,_normalized_record,deadline=5,clock=lambda:0)[0]=={}


def test_injected_packet_and_legacy_capture_do_not_qualify():
    row,retained=prepared();register={'findings':[row]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    register['candidate_investigation']['packets'][0]['dependency_advisory_membership']['advisory_id']='GHSA-forged'
    assert 'dependency_advisory_membership' not in display_investigation(register,SCOPE,trusted_capture=retained)['packets'][0]
    assert 'dependency_advisory_membership' not in display_investigation(register,SCOPE)['packets'][0]


def test_bounded_result_and_deadline():
    r=result([raw()]);r['large']='x'*(advisory.RESULT_LIMIT+1);r['artifact_hash']=advisory.digest({k:v for k,v in r.items() if k!='artifact_hash'})
    observations,charged,_=advisory.capture([r],SCOPE,_normalized_record,deadline=5,clock=lambda:0)
    assert not observations and charged<=advisory.RESULT_LIMIT
    assert advisory.capture([result([raw()])],SCOPE,_normalized_record,deadline=0,clock=lambda:0)[0]=={}


@pytest.mark.parametrize('large',['x'*16385, {'nested':[[[[[0]]]]]}, list(range(8193))],ids=['large_string','deep','large_nodes'])
def test_preflight_rejects_before_serialization(monkeypatch,large):
    if isinstance(large,dict):
        large=0
        for _ in range(33):large=[large]
    r=result([raw()]);r['extra']=large
    monkeypatch.setattr(json.JSONEncoder,'iterencode',lambda *a,**k:pytest.fail('encoding should not start'))
    assert advisory.verified_result(r,SCOPE)[0] is None


def test_deadline_during_preflight_rejects_before_encoding(monkeypatch):
    r=result([raw()]);r['extra']=list(range(500));ticks=iter([0,10])
    monkeypatch.setattr(json.JSONEncoder,'iterencode',lambda *a,**k:pytest.fail('encoding should not start'))
    assert advisory.verified_result(r,SCOPE,deadline=5,clock=lambda:next(ticks,10))[0] is None


def test_real_workspace_capture_consumes_only_local_git_and_retained_result(tmp_path):
    import subprocess, os
    from nico.candidate_workspace_capture_v1 import capture_workspace, INPUT_LIMIT, OUTPUT_LIMIT, encoded
    repo=tmp_path/'repo';repo.mkdir()
    (repo/'package-lock.json').write_text(json.dumps({'lockfileVersion':3,'packages':{'node_modules/demo':{'version':'1.2.3'}}}))
    def git(*args):
        return subprocess.check_output(['git','-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid',*args],cwd=repo,stderr=subprocess.DEVNULL).decode().strip()
    git('init','-q');git('add','package-lock.json');git('commit','-qm','synthetic')
    scope={**SCOPE,'commit_sha':git('rev-parse','HEAD')}
    retained=capture_workspace(repo,{**scope,'snapshot_commit_sha':scope['commit_sha']},scope['commit_sha'],[result([raw()],scope)],env=dict(os.environ))
    assert retained['total_input_bytes_charged']<=INPUT_LIMIT
    assert len(encoded(retained))<=OUTPUT_LIMIT
    row=_normalized_record(commit_sha=scope['commit_sha'],scanner='osv-scanner',category='dependency',finding=raw())
    register={'findings':[row]};register['candidate_investigation']=investigate_register(register,retained,scope)
    assert register['candidate_investigation']['packets'][0]['dependency_advisory_membership']['status']=='explicitly_listed'
    assert retained['advisory_input_bytes']>0


@pytest.mark.parametrize('field,value',[('timed_out',True),('output_limit_exceeded',True),('output_capture_complete',False),('returncode_valid',False),('verified_for_this_report',False)])
def test_contradictory_completed_result_rejected(field,value):
    r=result([raw()]);r[field]=value;r['artifact_hash']=advisory.digest({k:v for k,v in r.items() if k!='artifact_hash'})
    assert advisory.capture([r],SCOPE,_normalized_record,deadline=5,clock=lambda:0)[0]=={}


def test_malformed_finding_cannot_hide_conflicting_claim():
    assert advisory.capture([result([raw(),None])],SCOPE,_normalized_record,deadline=5,clock=lambda:0)[0]=={}


@pytest.mark.parametrize('field,value',[('selected_evidence_sha256','b'*64),('scanner_raw_sha256','invalid'),('scope',{}),('candidate_key','f'*64)])
def test_corrupted_retained_observation_is_not_promoted(field,value):
    row,retained=prepared();observation=next(iter(retained['dependency_advisory_observations'].values()));observation[field]=value
    record=investigate_register({'findings':[row]},retained,SCOPE)
    assert 'dependency_advisory_membership' not in record['packets'][0]


def test_combined_receipts_share_existing_output_budget():
    row,retained=prepared();rows=[{**row,'candidate_id':str(i)} for i in range(500)]
    result=investigate_register({'findings':rows},retained,SCOPE,clock=lambda:0)
    total=sum(len(json.dumps(p[k]).encode()) for p in result['packets'] for k in ('dependency_identity','dependency_advisory_membership') if k in p)
    assert 0<total<=262144
    assert result['bounded_rule_analysis_completed']==0
    assert len(result['packets'])==500
    assert [p['candidate_id'] for p in result['packets']]==[str(i) for i in range(500)]


def test_unknown_lock_identity_cannot_gain_advisory_proof():
    row,retained=prepared();retained['observations']={}
    result=investigate_register({'findings':[row]},retained,SCOPE)
    assert 'dependency_advisory_membership' not in result['packets'][0]
