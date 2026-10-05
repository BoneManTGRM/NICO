"""Replay actual owned Clang17 observations and corrupt binding controls."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import pytest
from nico.assessment_cpp_clang_header_evidence import validate_clang_header_trace

ROOT=Path(__file__).parent/'fixtures/cpp/clang-header-observer-v15'
BINDINGS=json.loads((ROOT/'bindings.json').read_bytes())
def control(index):
    record=BINDINGS['records'][index];raw=(ROOT/record['fixture']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==record['sha256']
    value=json.loads(raw)
    locations=deepcopy(record['locations'])
    return raw,dict(source=value['source'],context_id=value['context_id'],locations=locations,standard=value['standard'])

@pytest.mark.parametrize('index',range(8))
def test_actual_owned_observer_trace_states_remain_truthful(index):
    raw,kwargs=control(index);proof=validate_clang_header_trace(raw,**kwargs)
    assert proof['normal_pass_completed'] is (index!=4)
    assert not proof['individual_checker_coverage_verified'] and not proof['line_branch_coverage_verified']
    if index==3:
        assert any(p.endswith('/body.h') for p in proof['syntax_body_callback_files'])
        assert not any(p.endswith('/main.cpp') for p in proof['syntax_body_callback_files'])
    if index==4:assert proof['diagnostic_errors_observed_at_emit'] and not proof['translation_unit_ended']
    if index==5:
        row=next(r for r in proof['bound_file_observations'] if r['path'].endswith('/pragma.h'))
        assert not row['initially_system'] and row['system_header_pragma_observed'] and row['ast_body_callbacks']==0
    if index==2:
        macro=next(r for r in proof['bound_file_observations'] if r['path'].endswith('/macro_only.h'))
        assert macro['ast_decl_nodes']==0 and macro['ast_body_callbacks']==0
    if index in (6,7):
        assert kwargs['source'] not in proof['parsed_ast_files']

def test_actual_multi_file_plist_preserves_default_checker_finding_with_observer():
    import plistlib
    documents=[plistlib.loads((ROOT/(control+'-cross-file.plist')).read_bytes()) for control in ('baseline','observer')]
    findings=[]
    for document in documents:
        assert len(document['diagnostics'])==1
        finding=document['diagnostics'][0]
        assert finding['check_name']=='core.NullDereference'
        assert document['files'][finding['location']['file']].endswith('/inline.h')
        assert {Path(p).name for p in document['files']}=={'main.cpp','inline.h'}
        findings.append({k:finding[k] for k in ('description','category','type','check_name','location')})
    assert findings[0]==findings[1]

@pytest.mark.parametrize('key,value',[('source','/work/source/wrong.cpp'),('context_id','a'*64),('standard','c++20'),('clang_version','18.0.0'),('translation_unit_started',False),('diagnostic_errors',0)])
def test_wrong_identity_or_malformed_stage_is_rejected(key,value):
    raw,kwargs=control(0);document=json.loads(raw);document[key]=value
    with pytest.raises(ValueError):validate_clang_header_trace(json.dumps(document).encode(),**kwargs)

@pytest.mark.parametrize('mutation',['duplicate_file','negative_count','boolean_count','false_body','unknown_owned_file','duplicate_key','overflow_limit'])
def test_corrupt_or_unbound_producer_observation_is_rejected(mutation):
    raw,kwargs=control(0);document=json.loads(raw)
    if mutation=='duplicate_file':document['files'].append(deepcopy(document['files'][0]))
    elif mutation=='negative_count':document['files'][0]['ast_decl_nodes']=-1
    elif mutation=='boolean_count':document['files'][0]['entered']=True
    elif mutation=='false_body':document['files'][0].update(ast_body_callbacks=1,ast_decl_nodes=0,ast_stmt_nodes=0)
    elif mutation=='unknown_owned_file':document['files'][0]['path']='/work/source/uncaptured.h'
    elif mutation=='duplicate_key':
        with pytest.raises(ValueError):validate_clang_header_trace(raw.replace(b'"schema":',b'"schema":"invalid","schema":',1),**kwargs)
        return
    else:document['files']*=4097
    with pytest.raises(ValueError):validate_clang_header_trace(json.dumps(document).encode(),**kwargs)

@pytest.mark.parametrize('flag',['diagnostic_errors','observation_overflow'])
def test_incomplete_native_observation_never_gains_completion(flag):
    raw,kwargs=control(0);document=json.loads(raw);document[flag]=True
    assert not validate_clang_header_trace(json.dumps(document).encode(),**kwargs)['normal_pass_completed']

@pytest.mark.parametrize('mutation',['unentered_ast','unentered_body','ast_before_tu'])
def test_impossible_physical_ast_observation_is_rejected(mutation):
    raw,kwargs=control(0);document=json.loads(raw)
    if mutation=='ast_before_tu':
        document.update(translation_unit_started=False,translation_unit_ended=False)
    else:
        row=next(r for r in document['files'] if r['ast_body_callbacks'])
        row['entered']=0
        if mutation=='unentered_ast':row['ast_body_callbacks']=0
    with pytest.raises(ValueError):validate_clang_header_trace(json.dumps(document).encode(),**kwargs)

def test_complete_include_only_translation_unit_does_not_require_main_ast_anchors():
    # Codec invariant; real include-only and empty native controls are retained separately.
    raw,kwargs=control(0);document=json.loads(raw)
    row=next(r for r in document['files'] if r['path']==kwargs['source'])
    row.update(ast_decl_nodes=0,ast_stmt_nodes=0,ast_body_callbacks=0)
    proof=validate_clang_header_trace(json.dumps(document).encode(),**kwargs)
    assert proof['normal_pass_completed']
    assert kwargs['source'] not in proof['parsed_ast_files']
