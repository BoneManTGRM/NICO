from copy import deepcopy
import json
import pytest
from nico import dependency_identity_evidence_v1 as dep
from nico.candidate_workspace_capture_v1 import capture_candidates
from nico.candidate_investigation_pipeline_v1 import investigate_register,display_investigation
from tests.test_dependency_identity_evidence_v1 import row,capture,SCOPE


def retained(root,locations=None):
    return capture([row()],packages={'':root,**(locations or {'node_modules/demo':{'version':'1.2.3'}})})


@pytest.mark.parametrize('roles',[[r] for r in dep.ROOT_ROLES]+[list(dep.ROOT_ROLES)])
def test_literal_root_roles_roundtrip_and_unknowns(roles):
    r=row();before=deepcopy(r);cap=retained({role:{'demo':'^1.0.0'} for role in roles})
    register={'findings':[r]};register['candidate_investigation']=investigate_register(register,cap,SCOPE)
    packet=display_investigation(register,SCOPE,trusted_capture=cap)['packets'][0]
    identity=packet['dependency_identity']
    assert identity['root_declaration']=={'artifact_schema':dep.ROOT_VERSION,'roles':roles}
    assert identity['installed_state']==identity['affectedness']==identity['reachability']=='unknown'
    assert not packet['completed'] and r==before
    assert register['candidate_investigation']['bounded_rule_analysis_completed']==0
    assert register['candidate_investigation']['human_review_required'] is True
    assert register['candidate_investigation']['client_delivery_allowed'] is False
    assert 'dependency_scope' not in identity and 'direct_dependency' not in identity
    assert '^1.0.0' not in json.dumps(identity)


@pytest.mark.parametrize('root',[None,[],{}, {'dependencies':[]},{'dependencies':{'demo':True}},
    {'dependencies':{'demo':''}},{'dependencies':{'demo':'x'*1025}}, {'dependencies':{'demo':'npm:other@1.2.3'}},
    {'dependencies':{'demo':' 1.2.3'}},{'dependencies':{'demo':'1.2.3\n'}}, {'dependencies':{'other':'1.2.3'}}])
def test_missing_malformed_or_nonmatching_roles_preserve_identity(root):
    cap=retained(root);identity=dep.qualify(row(),cap['observations']['package-lock.json'],SCOPE)
    assert identity and 'root_declaration' not in identity
    assert identity['installed_state']=='unknown'


@pytest.mark.parametrize('locations',[
 {'node_modules/parent/node_modules/demo':{'version':'1.2.3'}},
 {'node_modules/demo':{'version':'1.2.3'},'node_modules/parent/node_modules/demo':{'version':'2.0.0'}},
 {'node_modules/demo':{'version':'1.2.3','name':'other'}},
 {'node_modules/demo':{'version':'1.2.3','link':True}}])
def test_nested_duplicate_alias_link_get_no_roles(locations):
    cap=retained({'dependencies':{'demo':'1.2.3'}},locations)
    identity=dep.qualify(row(),cap['observations']['package-lock.json'],SCOPE)
    assert identity is None or 'root_declaration' not in identity


@pytest.mark.parametrize('roles',[[],['dependencies','dependencies'],['peerDependencies','dependencies'],['production'],[True],['dependencies']*5])
def test_malformed_retained_roles_not_authoritative(roles):
    cap=retained({'dependencies':{'demo':'1.2.3'}})
    cap['observations']['package-lock.json']['root_declarations']['declarations']['demo']=roles
    identity=dep.qualify(row(),cap['observations']['package-lock.json'],SCOPE)
    assert identity and 'root_declaration' not in identity


def test_projection_rejects_forged_packet_and_stale_capture():
    cap=retained({'dependencies':{'demo':'1.2.3'}});register={'findings':[row()]}
    register['candidate_investigation']=investigate_register(register,cap,SCOPE)
    original=deepcopy(register)
    register['candidate_investigation']['packets'][0]['dependency_identity']['root_declaration']['roles']=['devDependencies']
    assert 'dependency_identity' not in display_investigation(register,SCOPE,trusted_capture=cap)['packets'][0]
    for key in ('customer_id','commit_sha'):
        wrong={**SCOPE,key:'foreign'}
        assert not display_investigation(original,wrong,trusted_capture=cap)['available']
    assert register['findings']==original['findings']


def test_legacy_packet_and_optional_absence_unchanged():
    cap=capture([row()]);register={'findings':[row()]};register['candidate_investigation']=investigate_register(register,cap,SCOPE)
    identity=display_investigation(register,SCOPE,trusted_capture=cap)['packets'][0]['dependency_identity']
    assert identity and 'root_declaration' not in identity


def test_existing_capture_output_cap_charges_root_metadata(monkeypatch):
    from nico import candidate_workspace_capture_v1 as module
    monkeypatch.setattr(module,'OUTPUT_LIMIT',1)
    cap=retained({'dependencies':{'demo':'1.2.3'}})
    assert cap['observations']=={}


def test_role_receipts_share_existing_packet_budget():
    rows=[{**row(),'candidate_id':f'synthetic-{i}'} for i in range(800)]
    cap=retained({'dependencies':{'demo':'^1.0.0'}})
    register={'findings':rows}
    register['candidate_investigation']=investigate_register(register,cap,SCOPE,clock=lambda:0)
    packets=register['candidate_investigation']['packets']
    identities=[p['dependency_identity'] for p in packets if p.get('dependency_identity')]
    assert 0<len(identities)<len(rows)
    assert sum(len(json.dumps(x).encode()) for x in identities)<=262144
    assert all(x['root_declaration']['roles']==['dependencies'] for x in identities)
    view=display_investigation(register,SCOPE,trusted_capture=cap)
    assert len(view['packets'])==len(rows)
    assert all(not p['completed'] for p in view['packets'])
    assert sum(len(json.dumps(p['dependency_identity']).encode()) for p in view['packets'] if p.get('dependency_identity'))<=262144
