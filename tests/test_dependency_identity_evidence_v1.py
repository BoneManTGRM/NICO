from copy import deepcopy
import json
import pytest
from nico import dependency_identity_evidence_v1 as dep
from nico.candidate_workspace_capture_v1 import capture_candidates
from nico.candidate_investigation_pipeline_v1 import investigate_register, display_investigation
from nico.comprehensive_native_providers_v5 import _normalized_record
from tests.test_candidate_workspace_capture_v1 import memory
from tests.test_candidate_investigation_pipeline_v1 import SCOPE


def row(**extra):
    return _normalized_record(commit_sha=SCOPE['commit_sha'], scanner='osv-scanner', category='dependency',
        finding={'package':'demo', 'dependency_path':'package-lock.json', **extra})


def capture(rows, packages=None, data=None, **kwargs):
    data = data if data is not None else json.dumps({'lockfileVersion':3,'packages':packages or {'node_modules/demo':{'version':'1.2.3'}}}).encode()
    inventory, read, reads = memory({'package-lock.json':data})
    return capture_candidates(rows, SCOPE, inventory, read, **kwargs)


def test_real_normalization_capture_persistence_and_read_nonmutation():
    rows = [row(),row()]
    before=deepcopy(rows)
    retained=capture(rows)
    register={'findings':rows}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    view=display_investigation(register,SCOPE,trusted_capture=retained)
    assert view['available'] and len(view['packets'])==2
    assert [p['record_index'] for p in view['packets']]==[0,1]
    for p in view['packets']:
        receipt=p['dependency_identity']
        assert receipt['package']=='demo' and receipt['locked_version']=='1.2.3'
        assert receipt['scope']==SCOPE
        assert receipt['affectedness']==receipt['reachability']==receipt['installed_state']=='unknown'
        assert not p['completed']
    assert rows==before
    assert register['candidate_investigation']['bounded_rule_analysis_completed']==0
    assert register['candidate_investigation']['human_review_required'] is True
    assert register['candidate_investigation']['client_delivery_allowed'] is False


@pytest.mark.parametrize('packages',[
 {'node_modules/demo':{'version':'1.2.3'},'node_modules/other/node_modules/demo':{'version':'2.0.0'}},
 {'node_modules/demo':{'version':'1.2.3','link':True}},
 {'node_modules/demo':{'version':'file:../secret'}},
 {'node_modules/demo':{'version':'1.2.3','name':'other'}},
 {'../node_modules/demo':{'version':'1.2.3'}},
 {'node_modules/other':{'version':'1.2.3'}},
])
def test_ambiguous_unsupported_and_missing_do_not_qualify(packages):
    r=row(); retained=capture([r],packages)
    assert dep.qualify(r,retained['observations'].get('package-lock.json'),SCOPE) is None


@pytest.mark.parametrize('data',[b'{', b'\xff', b'{"lockfileVersion":3,"lockfileVersion":3,"packages":{}}',
 b'{"lockfileVersion":1,"packages":{}}', b' '*262145,
 json.dumps({'lockfileVersion':3,'packages':{'node_modules/p'+str(i):{'version':'1.0.0'} for i in range(4097)}}).encode()])
def test_parse_boundaries(data):
    r=row(); retained=capture([r],data=data)
    assert dep.qualify(r,retained['observations'].get('package-lock.json'),SCOPE) is None


@pytest.mark.parametrize('field',['run_id','repository','commit_sha','customer_id','project_id'])
def test_wrong_scope_fails(field):
    r=row(); retained=capture([r]); scope={**SCOPE,field:'wrong'}
    assert dep.qualify(r,retained['observations']['package-lock.json'],scope) is None
    assert 'dependency_identity' not in investigate_register({'findings':[r]},retained,scope)['packets'][0]


@pytest.mark.parametrize('changes',[{'installed_version':'2.0.0'}, {'package_name':'other'}, {'package':'../../bad'}, {'dependency_path':'../package-lock.json'}])
def test_scanner_conflict(changes):
    r=row(**changes); retained=capture([r])
    assert dep.qualify(r,retained['observations'].get('package-lock.json'),SCOPE) is None


def test_reencoding_and_stale_row_rejected():
    r=row(); retained=capture([r]); observation=retained['observations']['package-lock.json']
    observation['origin']='snapshot_decoded_text'
    assert dep.qualify(r,observation,SCOPE) is None
    retained=capture([r]); register={'findings':[r]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    r['dependency_identity_request']['package']='other'
    assert not display_investigation(register,SCOPE)['available']


def test_no_raw_payload_leak():
    r=row(); retained=capture([r],{'node_modules/demo':{'version':'1.2.3','resolved':'https://secret.invalid/token','integrity':'PRIVATE'}})
    receipt=dep.qualify(r,retained['observations']['package-lock.json'],SCOPE)
    assert receipt
    assert 'PRIVATE' not in json.dumps(retained) and 'secret.invalid' not in json.dumps(retained)


def test_shared_budget_stops_reads():
    r=row(); inventory,read,reads=memory({'package-lock.json':b'{}'})
    ticks=iter([0,6,6,6,6,6,6])
    result=capture_candidates([r],SCOPE,inventory,read,clock=lambda: next(ticks,6))
    assert not reads and not result['observations']


def test_injected_packet_requires_independent_capture():
    r=row(); retained=capture([r]); register={'findings':[r]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    assert 'dependency_identity' not in display_investigation(register,SCOPE)['packets'][0]
    register['candidate_investigation']['packets'][0]['dependency_identity']['source_sha256']='f'*64
    assert 'dependency_identity' not in display_investigation(register,SCOPE,trusted_capture=retained)['packets'][0]


def test_expired_investigation_never_qualifies():
    r=row(); retained=capture([r]); ticks=iter([0,3])
    result=investigate_register({'findings':[r]},retained,SCOPE,clock=lambda:next(ticks,3))
    assert result['packets'][0]['reason']=='investigation_budget_exhausted'
    assert 'dependency_identity' not in result['packets'][0]


def test_producer_rejects_wrong_blob_oid():
    assert dep.observe(b'{}',scope=SCOPE,path='package-lock.json',blob_oid='f'*40)['status']=='unavailable'

@pytest.mark.parametrize('extra',[{'ecosystem':'PyPI'},{'osv_scanned_ecosystem':'Maven'}])
def test_ecosystem_conflicts(extra):
    assert 'dependency_identity_request' not in row(**extra)


def test_false_node_modules_segment():
    r=row(); retained=capture([r],{'not_node_modules/demo':{'version':'1.2.3'}})
    assert dep.qualify(r,retained['observations'].get('package-lock.json'),SCOPE) is None


def test_canonical_dedupe_conflict_suppresses_identity_without_changing_population(monkeypatch):
    from nico import candidate_lineage_runtime_patch_v1 as runtime
    from nico.candidate_technical_triage_v1 import apply_candidate_technical_triage
    monkeypatch.setattr(runtime, 'apply_candidate_technical_triage', lambda register, **kw:
        apply_candidate_technical_triage(register, triage={'records': [], 'synthetic': True}, **kw))
    from nico.comprehensive_native_providers_v5 import build_canonical_scanner_finding_register
    findings=[{'package':p,'dependency_path':'package-lock.json','id':'CVE-test','message':'same'} for p in ('demo','other','demo')]
    result=build_canonical_scanner_finding_register({'scanner_results':[{'tool':'osv-scanner','category':'dependency','findings':findings}]},SCOPE['commit_sha'])
    # Installed identity wrapper expands the three original occurrences after dedupe.
    assert len(result['findings'])==3
    assert sum(r['occurrence_count'] for r in result['findings'])==3
    assert all('dependency_identity_request' not in r for r in result['findings'])


def test_actual_review_projection_with_sorted_candidates_uses_original_identity():
    from nico.comprehensive_review_work_v2 import review_work_projection
    from nico.candidate_investigation_pipeline_v1 import fingerprint
    rows=[{**row(),'candidate_id':'Z'},{**row(),'candidate_id':'A'}]
    retained=capture(rows)
    register={'candidate_record_count':2,'findings':rows,'review_workload_clusters':[{'cluster_id':'synthetic','candidate_ids':['Z','A']}]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    identity={**SCOPE,'evidence_ledger_id':'synthetic-ledger'}
    canonical={'identity':identity,'assessment':{'canonical_scanner_finding_register':register}}
    record={'identity':identity,'stage_results':{'final_comprehensive_report_generation':{'report_package':{'json':canonical}},
            'evidence_reconciliation_and_scoring':{'candidate_source_observations':retained}}}
    before=deepcopy(record)
    projected=review_work_projection(record)
    assistance=projected['review_assistance']
    queue=next(p for p in assistance['queue'] if p['candidate_id']=='A')
    assert queue['source_record_index']==1
    assert queue['source_candidate_input_sha256']==fingerprint(rows[1])
    source=assistance['source_investigation']['packets'][1]
    assert source['candidate_input_sha256']==queue['source_candidate_input_sha256']
    assert source['dependency_identity']['package']=='demo'
    assert not projected['client_delivery_allowed'] and record==before


def test_receipt_output_is_bounded_and_not_counted_as_resolution():
    rows=[{**row(),'candidate_id':str(i)} for i in range(1000)]
    retained=capture(rows)
    result=investigate_register({'findings':rows},retained,SCOPE,clock=lambda:0)
    size=sum(len(json.dumps(p['dependency_identity']).encode()) for p in result['packets'] if 'dependency_identity' in p)
    assert 0 < size <= 262144
    assert 0 < result['dependency_identity_collected_count'] < len(rows)
    assert result['bounded_rule_analysis_completed']==0


def test_distinct_request_cap_does_not_credit_unexamined_rows():
    rows=[{**row(package=f'p{i}'),'candidate_id':str(i)} for i in range(129)]
    packages={f'node_modules/p{i}':{'version':'1.0.0'} for i in range(129)}
    result=investigate_register({'findings':rows},capture(rows,packages),SCOPE,clock=lambda:0)
    assert result['dependency_identity_attempted_count']==128
    assert result['dependency_identity_collected_count']==128
    assert 'dependency_identity' not in result['packets'][-1]


@pytest.mark.parametrize('field',['run_id','customer_id','project_id'])
def test_explicit_foreign_candidate_scope(field):
    r=row(); retained=capture([r]); r[field]='foreign'
    assert dep.qualify(r,retained['observations']['package-lock.json'],SCOPE) is None

@pytest.mark.parametrize('corrupt',[None,{}, {'package':'demo'}, {'package':'demo','unsupported':True,'extra':'raw'}])
def test_malformed_inventory_cannot_hide_ambiguity(corrupt):
    r=row(); retained=capture([r]); observation=retained['observations']['package-lock.json']
    observation['entries'].append(corrupt)
    assert dep.qualify(r,observation,SCOPE) is None


def test_cache_cannot_reuse_receipt_for_foreign_row_tenant():
    r=row(); rows=[r,{**r,'customer_id':'foreign'}]
    result=investigate_register({'findings':rows},capture(rows),SCOPE)
    assert 'dependency_identity' in result['packets'][0]
    assert 'dependency_identity' not in result['packets'][1]
