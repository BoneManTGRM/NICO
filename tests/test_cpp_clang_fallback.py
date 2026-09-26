"""Independent Clang fallback for contexts the primary analyzer cannot complete."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
import plistlib
import pytest
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_project_static import request as static_request, native, execution

def api():
    assert importlib.util.find_spec('nico.assessment_cpp_clang_fallback')
    from nico import assessment_cpp_clang_fallback
    return assessment_cpp_clang_fallback

def primary_with_one_failure(tmp_path):
    from nico import assessment_cpp_project_static as static
    req=static_request(tmp_path); data=native(req)
    raw=b'<results version="2"><cppcheck version="2.17.1"/><errors><error id="syntaxError" severity="error" msg="syntax error"><location file="'+req['contexts'][0]['analysis_file'].encode()+b'" line="1" column="1"/></error><error id="checkersReport" severity="information" msg="Active checkers: There was critical errors (use --checkers-report=&lt;filename&gt; to see details)"/></errors></results>'
    row=data['records'][0]; row['xml']=base64.b64encode(raw).decode(); row['xml_sha256']=hashlib.sha256(raw).hexdigest()
    proof=static.validate_project_static(_canonical(data),req)
    assert not proof['complete'] and len(proof['analyzed_contexts'])==2
    return req,proof

def fallback_native(req,*,finding=False,fail=False):
    rows=[]
    for context in req['contexts']:
        files=[context['analysis_file']]; diagnostics=[]
        if finding:
            diagnostics=[{'path':[],'description':'Owned null dereference','category':'Logic error','type':'Dereference of null pointer',
                'check_name':'core.NullDereference','location':{'line':1,'col':2,'file':0}}]
        raw=plistlib.dumps({'clang_version':'Debian clang version 17.0.6','files':files,'diagnostics':diagnostics})
        rows.append({'context_id':context['context_id'],'invocation':context['invocation'],'dropped_arguments':context['dropped_arguments'],
            'execution':execution(exit_code=1 if fail else 0),'plist':base64.b64encode(__import__('zlib').compress(raw,9)).decode(),
            'plist_sha256':hashlib.sha256(raw).hexdigest(),'error':None})
    return {'schema':req['schema'].replace('-request.', '-evidence.'),'request_sha256':hashlib.sha256(_canonical(req)).hexdigest(),
        'analyst_uid':1001,'version':execution(b'17.0.6\n'),'records':rows,'duration_ms':5}

def test_fallback_plan_preserves_configuration_and_only_drops_known_gcc_only_or_output_flags(tmp_path):
    req=static_request(tmp_path); row=deepcopy(req['contexts'][0])
    row['invocation']=[row['invocation'][0],'-DVALUE=7','-I/work/source/include','-std=c++20','-pthread','-mavx2','-O0','-Wall',
        '-fno-extended-identifiers','-fstack-reuse=none','-c',row['analysis_file'],'-o','/work/analysis/compiler-baseline/u0.o',
        '-MD','-MF','/work/analysis/compiler-baseline/u0.d','-MT','nico_unit','-fsyntax-only']
    argv,dropped=api()._fallback_plan(row)
    assert argv[0].endswith('clang++') and '--analyze' in argv
    for value in ('-DVALUE=7','-I/work/source/include','-std=c++20','-pthread','-mavx2','-O0'): assert value in argv
    for value in ('-fno-extended-identifiers','-fstack-reuse=none','-Wall','-c','-MD'): assert value not in argv
    assert '-fno-extended-identifiers' in dropped and '-fstack-reuse=none' in dropped
    assert 'bitcoin' not in __import__('pathlib').Path(api().__file__).read_text().lower()

def test_fallback_request_contains_only_primary_attempted_incomplete_contexts(tmp_path):
    req,proof=primary_with_one_failure(tmp_path); fallback=api().clang_fallback_request(req,proof)
    assert len(fallback['contexts'])==1 and fallback['contexts'][0]['context_id']==req['contexts'][0]['context_id']
    assert isinstance(fallback['primary_analyzed_contexts'],list)
    assert fallback['cppcheck_evidence_sha256']==proof['native_evidence_sha256']

def test_fallback_can_complete_primary_parser_failure_and_retains_both_tools_truth(tmp_path):
    req,proof=primary_with_one_failure(tmp_path); fallback_req=api().clang_fallback_request(req,proof)
    fallback=api().validate_clang_fallback(_canonical(fallback_native(fallback_req,finding=True)),fallback_req,req)
    merged=api().merge_static_analysis(proof,fallback)
    assert fallback['complete'] and merged['complete']
    assert merged['analyzed_contexts']==[c['context_id'] for c in req['contexts']]
    assert any(x['rule_id']=='syntaxError' for x in merged['limitations'])
    clang=[f for f in merged['findings'] if f.get('analyzer')=='clang-static-analyzer']
    assert len(clang)==1 and clang[0]['classification']=='review_required_candidate'

def test_failed_fallback_never_converts_primary_failure_to_completed_coverage(tmp_path):
    req,proof=primary_with_one_failure(tmp_path); fr=api().clang_fallback_request(req,proof)
    fallback=api().validate_clang_fallback(_canonical(fallback_native(fr,fail=True)),fr,req)
    merged=api().merge_static_analysis(proof,fallback)
    assert not fallback['complete'] and not merged['complete']
    assert req['contexts'][0]['context_id'] not in merged['analyzed_contexts']
    assert any(x['rule_id']=='clang_native_execution_incomplete' for x in merged['limitations'])

def test_fallback_rejects_unbound_diagnostic_location(tmp_path):
    req,proof=primary_with_one_failure(tmp_path); fr=api().clang_fallback_request(req,proof); data=fallback_native(fr,finding=True)
    row=data['records'][0]; raw=plistlib.loads(__import__('zlib').decompress(base64.b64decode(row['plist']))); raw['files']=['/etc/passwd']
    encoded=plistlib.dumps(raw); row['plist']=base64.b64encode(__import__('zlib').compress(encoded,9)).decode(); row['plist_sha256']=hashlib.sha256(encoded).hexdigest()
    fallback=api().validate_clang_fallback(_canonical(data),fr,req)
    assert not fallback['complete'] and any(x['rule_id']=='clang_diagnostic_location_unbound' for x in fallback['limitations'])

def test_embedded_fallback_program_is_self_contained_and_pinned():
    compile(api().PROGRAM,'clang-fallback-program','exec')
    assert 'from nico' not in api().PROGRAM and 'import nico' not in api().PROGRAM
    assert api().VERSION=='17.0.6' and api().LIMITS=={'wall_seconds':180,'case_seconds':45,'parallel':4}
    assert '/usr/lib/llvm-17/bin/clang' in api().PROGRAM

def test_real_static_stage_runs_fallback_only_after_primary_incomplete(tmp_path):
    from nico import assessment_cpp_project_static as static
    from tests.test_cpp_project_static_stage import stage_inputs
    from tests.test_cpp_static_environment_integration import EnvironmentDocker,native_v2
    from xml.etree import ElementTree as ET
    class FallbackDocker(EnvironmentDocker):
        def __call__(self,argv,**kwargs):
            if static.PROGRAM in argv:
                self.calls.append((argv,kwargs)); request=json.loads(kwargs['input_bytes']); value=json.loads(native_v2(request,missing='stdint.h',rule='uninitvar'))
                row=value['records'][0]; raw=__import__('zlib').decompress(base64.b64decode(row['xml'])) if row.get('xml_encoding')=='zlib' else base64.b64decode(row['xml'])
                doc=ET.fromstring(raw); ET.SubElement(doc.find('errors'),'error',{'id':'syntaxError','severity':'error','msg':'syntax error'})
                changed=ET.tostring(doc); encoded,digest,encoding=static._encode_xml(changed,compact=True); row.update(xml=encoded,xml_sha256=digest,xml_encoding=encoding)
                return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':_canonical(value)}
            if api().PROGRAM in argv:
                self.calls.append((argv,kwargs)); request=json.loads(kwargs['input_bytes'])
                return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':_canonical(fallback_native(request,finding=True))}
            return super().__call__(argv,**kwargs)
    root,targets,database,snapshot,compiler=stage_inputs(tmp_path); docker=FallbackDocker(targets); artifacts={}
    def sink(key,raw):
        artifacts[key]=raw; sha=hashlib.sha256(raw).hexdigest(); return {'path':'artifacts/'+key+'-'+sha+'.json','sha256':sha,'bytes':len(raw)}
    result=static.run_project_static_stage(root,targets,'sha256:'+'a'*64,database,snapshot,compiler,compiler_environment=True,command=docker,retain_artifact=sink)
    assert result['complete'] and result['analysis']['complete']
    assert len(result['analysis']['clang_fallback']['required_contexts'])==1 and result['analysis']['clang_fallback']['complete']
    assert 'project-static-clang-fallback' in artifacts
    ids=[op['id'] for op in result['operations']]; assert ids.index('project-static-evidence')<ids.index('project-static-clang-fallback')
    assert any(f.get('analyzer')=='clang-static-analyzer' for f in result['analysis']['findings'])
    assert any(l.get('rule_id')=='syntaxError' for l in result['analysis']['limitations'])


def test_static_stage_retains_substantive_fallback_beyond_old_per_case_limit(tmp_path):
    """Owned native-response boundary, not a real long-running analyzer proof."""
    from nico import assessment_cpp_project_static as static
    from tests.test_cpp_project_static_stage import stage_inputs
    from tests.test_cpp_static_environment_integration import EnvironmentDocker,native_v2
    from xml.etree import ElementTree as ET
    class SlowFallbackDocker(EnvironmentDocker):
        def __call__(self,argv,**kwargs):
            if static.PROGRAM in argv:
                self.calls.append((argv,kwargs)); req=json.loads(kwargs['input_bytes'])
                value=json.loads(native_v2(req,missing='stdint.h',rule='uninitvar'))
                row=value['records'][0]
                raw=__import__('zlib').decompress(base64.b64decode(row['xml'])) if row.get('xml_encoding')=='zlib' else base64.b64decode(row['xml'])
                doc=ET.fromstring(raw); ET.SubElement(doc.find('errors'),'error',{'id':'syntaxError','severity':'error','msg':'syntax error'})
                enc,digest,encoding=static._encode_xml(ET.tostring(doc),compact=True)
                row.update(xml=enc,xml_sha256=digest,xml_encoding=encoding)
                return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':_canonical(value)}
            if api().PROGRAM in argv:
                self.calls.append((argv,kwargs)); req=json.loads(kwargs['input_bytes'])
                value=fallback_native(req,finding=True)
                value['records'][0]['execution']['duration_ms']=90000
                value['duration_ms']=90010
                return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':_canonical(value)}
            return super().__call__(argv,**kwargs)
    source,targets,database,snapshot,compiler=stage_inputs(tmp_path)
    docker=SlowFallbackDocker(targets); artifacts={}
    def sink(key,raw):
        artifacts[key]=raw; sha=hashlib.sha256(raw).hexdigest()
        return {'path':'artifacts/'+key+'-'+sha+'.json','sha256':sha,'bytes':len(raw)}
    result=static.run_project_static_stage(source,targets,'sha256:'+'a'*64,database,snapshot,compiler,
        compiler_environment=True,command=docker,retain_artifact=sink)
    assert result['complete'] is True, result['error']
    assert result['execution_budget_seconds']==1020 and result['wall_budget_seconds']==1030
    call=next(kwargs for argv,kwargs in docker.calls if api().PROGRAM in argv)
    assert call['timeout']>480 and call['timeout']<=490
    req=json.loads(call['input_bytes'])
    assert req['limits']=={'wall_seconds':480,'case_seconds':120,'parallel':2}
    assert req['schema']=='nico.cpp-clang-fallback-request.v4'
    assert len(result['analysis']['analyzed_contexts'])==len(result['analysis']['required_contexts'])
    assert result['cleanup_verified'] is True


@pytest.mark.parametrize('extended,seconds', [(False,45),(True,120)])
def test_fallback_budget_versions_bind_native_evidence_and_reject_overrun(tmp_path,extended,seconds):
    req,proof=primary_with_one_failure(tmp_path)
    fr=api().clang_fallback_request(req,proof,extended_budget=extended)
    data=fallback_native(fr,finding=True)
    data['records'][0]['execution']['duration_ms']=seconds*1000
    data['duration_ms']=seconds*1000+10
    result=api().validate_clang_fallback(_canonical(data),fr,req)
    assert result['complete'] is True
    data['records'][0]['execution']['duration_ms']=(seconds+4)*1000
    data['duration_ms']=(seconds+4)*1000+10
    with pytest.raises(ValueError,match='execution_invalid'):
        api().validate_clang_fallback(_canonical(data),fr,req)


@pytest.mark.parametrize('change', ['schema','limits','boolean','missing','hash','outcome'])
def test_extended_fallback_never_accepts_unbound_or_incomplete_success(tmp_path,change):
    req,proof=primary_with_one_failure(tmp_path)
    fr=api().clang_fallback_request(req,proof,extended_budget=True)
    data=fallback_native(fr)
    if change=='schema': data['schema']='nico.cpp-clang-fallback-evidence.v1'
    elif change=='limits': fr['limits']['wall_seconds']=481
    elif change=='boolean': fr['limits']['parallel']=True
    elif change=='missing': del fr['limits']['case_seconds']
    elif change=='hash': data['request_sha256']='0'*64
    else:
        data['records'][0]['execution'].update(exit_code=124,timed_out=True)
        result=api().validate_clang_fallback(_canonical(data),fr,req)
        assert result['complete'] is False and result['analyzed_contexts']==[]
        return
    with pytest.raises(ValueError):
        api().validate_clang_fallback(_canonical(data),fr,req)


def test_expanded_fallback_preserves_population_commands_and_primary_limits(tmp_path):
    req,proof=primary_with_one_failure(tmp_path)
    old=api().clang_fallback_request(req,proof)
    new=api().clang_fallback_request(req,proof,extended_budget=True)
    assert {k:v for k,v in old.items() if k not in {'schema','limits'}}=={
        k:v for k,v in new.items() if k not in {'schema','limits'}}
    assert api().LIMITS=={'wall_seconds':180,'case_seconds':45,'parallel':4}
    assert new['limits']=={'wall_seconds':480,'case_seconds':120,'parallel':4}
    for bad in [None,0,1,'true']:
        with pytest.raises(ValueError): api().clang_fallback_request(req,proof,extended_budget=bad)
    compile(api().PROGRAM,'owned-fallback-program','exec')
    assert 'EXTENDED_LIMITS' in api().PROGRAM


@pytest.mark.parametrize('schema', [[], {}, None, True, 2])
def test_fallback_schema_is_validated_before_lookup(schema):
    request = {'schema':schema, 'limits':{'wall_seconds':480,'case_seconds':120,'parallel':4}}
    with pytest.raises(ValueError, match='worker_clang_fallback_request_invalid'):
        api()._request_limits(request)


def test_shared_static_budget_reports_selected_fallback_limit_without_expanding_parent():
    from nico import assessment_cpp_project_static as static
    policy = static.STAGE_BUDGET
    assert policy['fallback_seconds'] == api().EXTENDED_LIMITS['wall_seconds']
    assert policy['schema'] == 'nico.cpp-static-combined-budget.v3'
    assert policy['shared_execution_seconds'] == static.STAGE_EXECUTION_SECONDS == 1020
    assert policy['controller_seconds'] == 300
    assert policy['limits_share_execution_envelope'] is True
    assert static.STAGE_WALL_SECONDS == 1030
