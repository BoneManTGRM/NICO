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
    return {'schema':'nico.cpp-clang-fallback-evidence.v1','request_sha256':hashlib.sha256(_canonical(req)).hexdigest(),
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
