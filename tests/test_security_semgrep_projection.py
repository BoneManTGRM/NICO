"""Synthetic pinned-schema projection controls. No scanner execution."""
from copy import deepcopy
import json

import pytest
from scripts import security_semgrep_projection as s
from scripts import security_fresh_projection as p
from tests.test_security_fresh_projection import capture_root, complete, records, CANARY


def project(errors, version):
    return s.project(errors, version, frozenset({'owned/input.py','owned/other.py','owned/rules.yml'}))


def loc(path='owned/input.py',line=1):
    return {'path':path,'start':{'line':line,'col':1,'offset':0},'end':{'line':line,'col':4,'offset':3}}


def error():
    return {'code':3,'level':'warn','type':['PartialParsing',[loc()]],'message':CANARY}


@pytest.mark.parametrize('name',list(s.TYPES))
def test_all_exact_string_machine_types(name):
    result=project([{'code':2,'level':'error','type':name,'path':'owned/input.py'}],'1.170.0')
    assert result[0]['recognized_entries']==1 and result[0][s.TYPES[name]]==1
    assert result[1]['error']==1 and result[2]['grouped_entries']==1

@pytest.mark.parametrize('level,bucket',[('error','error'),('warn','warning'),('info','info'),('WARN','unknown'),('fatal','unknown'),(True,'unknown'),(None,'unknown')])
def test_severity_exact_schema_separate_from_gate(level,bucket):
    row=error();row['level']=level
    result=project([row],'1.170.0')
    assert result[1][bucket]==1
    assert result[2]['grouped_entries']==int(bucket not in ('unknown','missing'))


def test_missing_severity_distinct():
    row=error();del row['level']
    assert project([row],'1.170.0')[1]['missing']==1

@pytest.mark.parametrize('value',['PartialParsing','ParseError',[CANARY,[loc()]],['PartialParsing',False],['PartialParsing',[False]],True,None])
def test_unknown_or_malformed_type_never_hashed_or_grouped(value):
    row=error();row['type']=value
    result=project([row],'1.170.0')
    assert result[0]['unknown']==1 and result[0]['recognized_entries']==0
    assert result[2]['ungrouped_entries']==1 and len(result)==3
    assert CANARY not in json.dumps(result)


def test_pattern_yaml_selector_validated_but_not_identity():
    row={'type':['PatternParseError',['rules','1','pattern']],'level':'error','code':2,'rule_id':'owned-rule'}
    assert project([row],'1.170.0')[0]['configuration']==1
    row['type'][1]=[False]
    assert project([row],'1.170.0')[0]['unknown']==1


def test_repeated_selected_structure_not_semantic_deduplication():
    first=error();second=deepcopy(first);second['message']='different owned private message'
    result=project([first,second],'1.170.0')
    assert result[0]['parse']==2 and result[2]['group_count']==1
    assert result[3]['occurrences']==2 and result[2]['semantic_deduplication']is False
    third=deepcopy(first);third['type'][1][0]['start']['line']=2;third['type'][1][0]['end']['line']=2
    assert project([first,third],'1.170.0')[2]['group_count']==2

@pytest.mark.parametrize('mutation',['code','rule','path','range','severity','type'])
def test_each_selected_field_changes_group_identity(mutation):
    first=error();second=deepcopy(first)
    if mutation=='code':second['code']=4
    if mutation=='rule':second['rule_id']='owned-rule'
    if mutation=='path':second['path']='owned/other.py'
    if mutation=='range':second['type'][1][0]['end']['col']=5
    if mutation=='severity':second['level']='info'
    if mutation=='type':second['type']='Syntax error';second['path']='owned/input.py'
    assert project([first,second],'1.170.0')[2]['group_count']==2

@pytest.mark.parametrize('value',['/etc/passwd','../outside','owned/../outside','C:/outside','owned\\outside','owned//file','\x00',''])
def test_unsafe_paths_do_not_open_or_group(value):
    row=error();row['path']=value
    result=project([row],'1.170.0')
    assert result[0]['parse']==1 and result[2]['ungrouped_entries']==1


def test_dot_prefix_is_lexically_normalized_only():
    one=error();two=deepcopy(one);two['type'][1][0]['path']='./owned/input.py'
    assert project([one,two],'1.170.0')[2]['group_count']==1

@pytest.mark.parametrize('field,value',[('code',True),('code',-1),('code',256),('rule_id',False),('spans',False),('spans',[{}])])
def test_malformed_group_field_retains_category_and_ungrouped(field,value):
    row=error();row[field]=value
    result=project([row],'1.170.0')
    assert result[0]['parse']==1 and result[2]['ungrouped_entries']==1


def test_spans_location_and_offsets():
    row={'type':'InvalidRuleSchemaError','level':'error','code':2,'spans':[{'file':'owned/rules.yml','start':{'line':1,'col':1,'offset':-1},'end':{'line':1,'col':2,'offset':-1}}]}
    assert project([row],'1.170.0')[2]['grouped_entries']==1
    row['spans'][0]['start']['line']=True
    assert project([row],'1.170.0')[2]['ungrouped_entries']==1


def test_wrong_or_missing_version_never_claims_recognized_types():
    for version in (None,'1.169.0',True):
        result=project([error()],version)
        assert result[0]['unknown']==1 and result[2]['grouped_entries']==0
        assert result[1]['unknown']==1 and result[1]['warning']==0


def test_full_frame_26_duplicate_errors_and148_results(capture_root):
    value={'version':'1.170.0','results':[{'check_id':'owned-review'}]*148,'errors':[error()for _ in range(26)],'paths':{'scanned':['owned/input.py']*1991}}
    output=complete(capture_root,semgrep=value)
    assert p.validate_console(output) and CANARY.encode()not in output
    rows=records(output)
    assert next(r for r in rows if r.get('record')=='semgrep_categories')['parse']==26
    assert next(r for r in rows if r.get('record')=='semgrep_group')['occurrences']==26
    assert next(r for r in rows if r.get('record')=='semgrep_coverage')['scanned']==1991


def test_many_distinct_groups_fail_closed_not_truncated(capture_root):
    errors=[]
    for i in range(111):
        row=error();row['rule_id']='owned-rule-'+str(i);errors.append(row)
    with pytest.raises(p.Invalid,match='output_bounds'):
        complete(capture_root,semgrep={'version':'1.170.0','results':[],'errors':errors})


def test_group_transport_count_digest_order_crosschecks(capture_root):
    raw=complete(capture_root,semgrep={'version':'1.170.0','results':[],'errors':[error()]})
    for field,value in [('occurrences',True),('index',True),('category',CANARY),('severity','fatal'),('shape_sha256',CANARY)]:
        rows=records(raw)[:-1]
        next(r for r in rows if r.get('record')=='semgrep_group')[field]=value
        assert not p.validate_console(p.frame(rows))
    rows=records(raw)[:-1];next(r for r in rows if r.get('record')=='semgrep_groups')['grouped_entries']=0
    assert not p.validate_console(p.frame(rows))


def test_source_membership_missing_or_untracked_never_grouped():
    assert s.project([error()],'1.170.0',frozenset())[2]['grouped_entries']==0
    row=error();row['path']='owned/not-tracked.py'
    assert project([row],'1.170.0')[2]['grouped_entries']==0


def test_head_membership_excludes_untracked_and_symlink(capture_root):
    (capture_root/'owned/untracked.py').write_text('owned')
    assert 'owned/input.py' in p.tracked_paths(capture_root)
    assert 'owned/untracked.py' not in p.tracked_paths(capture_root)


def test_unknown_exit_code_stays_ungrouped():
    row=error();row['code']=6
    assert project([row],'1.170.0')[2]['grouped_entries']==0


def test_all_supported_span_ranges_affect_identity():
    first={'type':'Syntax error','level':'error','code':3,'spans':[{'file':'owned/input.py','start':{'line':1,'col':1},'end':{'line':1,'col':2}}]}
    for key in ('config_start','config_end','context_start','context_end'):
        second=deepcopy(first);second['spans'][0][key]={'line':2,'col':1}
        assert project([first,second],'1.170.0')[2]['group_count']==2
        second['spans'][0][key]=False
        assert project([second],'1.170.0')[2]['grouped_entries']==0


def test_category_recognition_reader_consistency(capture_root):
    raw=complete(capture_root,semgrep={'version':'1.170.0','results':[],'errors':[{'type':'Syntax error','code':3,'level':'warn'}]})
    rows=records(raw)[:-1]
    next(r for r in rows if r.get('record')=='semgrep_categories')['recognized_entries']=0
    assert not p.validate_console(p.frame(rows))

@pytest.mark.parametrize('name',['owned/not-tracked.py','../outside','/outside'])
def test_known_partial_parse_category_retained_when_unbound(name):
    row=error();row['type'][1][0]['path']=name
    result=project([row],'1.170.0')
    assert result[0]['parse']==1 and result[0]['recognized_entries']==1
    assert result[2]['ungrouped_entries']==1


def test_reader_version_mismatch_cannot_claim_pinned_classification(capture_root):
    raw=complete(capture_root,semgrep={'version':'1.170.0','results':[],'errors':[error()]})
    rows=records(raw)[:-1]
    next(r for r in rows if r.get('record')=='semgrep_version')['reported']='unavailable'
    assert not p.validate_console(p.frame(rows))
