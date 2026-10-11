"""Synthetic installed transport controls; native owned proof is separate."""
import base64,hashlib,json
from copy import deepcopy
import pytest
from nico import assessment_cpp_clang_fallback as fallback
from nico import assessment_cpp_project_static as static
from nico.assessment_cpp_project_compiler import _canonical
from nico.assessment_cpp_clang_header_evidence import (CLANG_HEADER_MANIFEST_SHA256,CLANG_HEADER_SOURCE_SHA256,
    CLANG_HEADER_SDK_SHA256,CLANG_HEADER_RUNTIME_SHA256)
from tests.test_cpp_header_transport import setup
from tests.test_cpp_clang_fallback import fallback_native

def fixture(tmp_path):
    request,output=setup(tmp_path);row=output['records'][0]
    xml=base64.b64decode(row['xml']).replace(b'</errors>',b'<error id="syntaxError" severity="error" msg="Owned synthetic parser failure"/></errors>')
    row.update(xml=base64.b64encode(xml).decode(),xml_sha256=hashlib.sha256(xml).hexdigest())
    primary=static.validate_project_static(_canonical(output),request)
    assert not primary['complete']
    req=fallback.clang_fallback_request(request,primary,extended_budget=True,contention_aware=True)
    assert req['schema']=='nico.cpp-clang-fallback-request.v5'
    evidence=fallback_native(req)
    tool=_canonical({'schema':'nico.clang-header-tool.v1','manifest_sha256':CLANG_HEADER_MANIFEST_SHA256,
        'source_sha256':CLANG_HEADER_SOURCE_SHA256,'sdk_lock_sha256':CLANG_HEADER_SDK_SHA256,
        'runtime_lock_sha256':CLANG_HEADER_RUNTIME_SHA256,'clang_version':'17.0.6',
        'plugin_sha256':'4258e8ca31a1009cd0ca663e8818cae4da729595e7f8dcb84bb41e63150f3da3',
        'compiler_version':'14.2.0','qualification_completed':False})
    evidence.update(header_tool_receipt=base64.b64encode(tool).decode(),header_tool_receipt_sha256=hashlib.sha256(tool).hexdigest())
    by_id={c['context_id']:c for c in request['contexts']}
    for row in evidence['records']:
        context=by_id[row['context_id']]
        trace={'schema':'nico.clang-header-observer.v1','clang_version':'17.0.6',
            'source':context['analysis_file'],'context_id':context['context_id'],
            'standard':fallback._clang_standard(context),'translation_unit_started':True,'translation_unit_ended':True,
            'diagnostic_errors':False,'observation_overflow':False,'files':[{'path':context['analysis_file'],
                'entered':1,'ast_decl_nodes':1,'ast_stmt_nodes':1,'ast_body_callbacks':1,
                'initially_system':False,'system_header_pragma_observed':False}]}
        row['header_trace'],row['header_trace_sha256']=fallback._encode_plist(_canonical(trace))
    return request,primary,req,evidence

def test_current_fallback_has_unchanged_budget_and_fixed_observer_only(tmp_path):
    primary,proof,request,evidence=fixture(tmp_path)
    assert request['limits']=={'wall_seconds':480,'case_seconds':120,'parallel':2}
    argv=request['contexts'][0]['invocation']
    assert argv.count(fallback.HEADER_PLUGIN)==1 and '-analyzer-checker=nico.HeaderEvidence' in argv
    assert '--analyze' in argv and '-plugin' not in argv and '-analyze-all' not in argv
    assert request['primary_request_sha256']==hashlib.sha256(_canonical(primary)).hexdigest()

def test_valid_complete_fallback_reconstructs_header_context_and_retains_primary_failure(tmp_path):
    request,primary,req,evidence=fixture(tmp_path)
    proof=fallback.validate_clang_fallback(_canonical(evidence),req,request)
    merged=fallback.merge_static_analysis(primary,proof)
    assert merged['complete'] and merged['header_context_evidence_complete']
    chosen=next(row for row in merged['header_context_evidence'] if row.get('analysis_method'))
    assert chosen['header_tool_manifest_sha256']==CLANG_HEADER_MANIFEST_SHA256
    assert chosen['primary_observation']==primary['header_context_evidence'][0]
    assert any(row['rule_id']=='syntaxError' for row in merged['limitations'])
    assert merged['header_population']==primary['header_population'] and not merged['header_population_complete']

@pytest.mark.parametrize('kind',['old_schema','missing_tool','wrong_tool_manifest','bad_tool_digest','bad_trace_digest',
    'wrong_trace_context','wrong_trace_source','wrong_trace_standard','unknown_trace_field'])
def test_missing_corrupt_wrong_or_downgraded_receipts_reject(kind,tmp_path):
    request,primary,req,evidence=fixture(tmp_path);row=evidence['records'][0]
    if kind=='old_schema':evidence['schema']='nico.cpp-clang-fallback-evidence.v4'
    elif kind=='missing_tool':evidence.pop('header_tool_receipt')
    elif kind=='bad_tool_digest':evidence['header_tool_receipt_sha256']='a'*64
    elif kind=='wrong_tool_manifest':
        tool=json.loads(base64.b64decode(evidence['header_tool_receipt']));tool['manifest_sha256']='a'*64;raw=_canonical(tool)
        evidence.update(header_tool_receipt=base64.b64encode(raw).decode(),header_tool_receipt_sha256=hashlib.sha256(raw).hexdigest())
    elif kind=='bad_trace_digest':row['header_trace_sha256']='a'*64
    else:
        trace=json.loads(fallback._decode_plist(row['header_trace'],row['header_trace_sha256']))
        if kind=='wrong_trace_context':trace['context_id']='a'*64
        elif kind=='wrong_trace_source':trace['source']='/work/source/unbound.cpp'
        elif kind=='wrong_trace_standard':trace['standard']='c++11'
        else:trace['invented_coverage']=True
        row['header_trace'],row['header_trace_sha256']=fallback._encode_plist(_canonical(trace))
    with pytest.raises(ValueError):fallback.validate_clang_fallback(_canonical(evidence),req,request)

@pytest.mark.parametrize('kind',['no_trace','no_end','native_failed','no_plist'])
def test_incomplete_native_or_header_proof_never_closes_header_gate(kind,tmp_path):
    request,primary,req,evidence=fixture(tmp_path);row=evidence['records'][0]
    if kind=='no_trace':row.update(header_trace='',header_trace_sha256=None)
    elif kind=='native_failed':row['execution']['exit_code']=1
    elif kind=='no_plist':row.update(plist='',plist_sha256=None)
    else:
        trace=json.loads(fallback._decode_plist(row['header_trace'],row['header_trace_sha256']));trace['translation_unit_ended']=False
        row['header_trace'],row['header_trace_sha256']=fallback._encode_plist(_canonical(trace))
    proof=fallback.validate_clang_fallback(_canonical(evidence),req,request)
    merged=fallback.merge_static_analysis(primary,proof)
    assert not merged['header_context_evidence_complete'] and not merged['header_population_complete']

def test_embedded_current_fallback_program_contains_all_tool_gates_without_application_imports():
    namespace={'__name__':'owned_codec_control'}
    exec(fallback.PROGRAM.rsplit('\nrun_clang_fallback()',1)[0],namespace)
    assert namespace['CLANG_HEADER_MANIFEST_SHA256']==CLANG_HEADER_MANIFEST_SHA256
    assert callable(namespace['validate_clang_header_tool_receipt'])
    assert 'from nico' not in fallback.PROGRAM and 'import nico' not in fallback.PROGRAM

@pytest.mark.parametrize('option,expected',[('c++03','c++98'),('gnu++2a','gnu++20'),('c++26','c++2c'),('gnu90','gnu89')])
def test_actual_pinned_language_aliases_preserve_standard_binding(option,expected):
    assert fallback._clang_standard({'invocation':['/usr/local/bin/g++','-std='+option]})==expected
