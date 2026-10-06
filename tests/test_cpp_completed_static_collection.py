"""Owned receipt controls; native tool behavior is verified separately."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from nico import assessment_cpp_project_static as static
from nico import assessment_cpp_clang_fallback as clang
from nico import assessment_cpp_static_environment as env
from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_compiler_collection import owned
from tests.test_cpp_static_environment import evidence as environment_evidence, observed
from tests.test_cpp_project_static import native
from tests.test_cpp_header_evidence import sample
from tests.test_cpp_clang_header_transport import fixture as clang_fixture


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture(tmp_path, failing=True, include_inputs=False, directive=None):
    if directive is None:
        directive = b'#error owned rejection' if failing else b'int value(){return VALUE;}'
    compiler, creq, snapshot = owned(tmp_path, failing=failing,
        directive=directive)
    craw = _canonical(compiler)
    database = _canonical([{k:c[k] for k in ('directory','file','arguments')} for c in creq['contexts']])
    # Rebuilt database has the same literal canonical bytes as the owned input.
    assert digest(database) == creq['database_sha256']
    cproof = validate_project_compiler_collection(craw, creq, snapshot)
    ereq = env.environment_request(creq, craw, 'sha256:'+'a'*64,
        collect_completed_compiler_failures=True, snapshot=snapshot)
    eraw = environment_evidence(ereq)
    eraw.update(schema='nico.cpp-static-environment.v2')
    for query in eraw['queries'].values():
        query['predefines'] = observed(base64.b64decode(query['predefines']['output'])
                                       + b'#define __cplusplus 202002L\n')
    model = env.validate_environment(_canonical(eraw), ereq)
    request = static.project_static_request(database, creq['targets'], snapshot, craw,
        environment=model, header_provenance=True, collect_completed_compiler_failures=True)
    output = native(request, 'checkersReport')
    output['schema'] = 'nico.cpp-project-static-evidence.v4'
    # Existing synthetic control retains the exact pinned tool-receipt shape.
    from tests.test_cpp_header_transport import setup
    scratch = tmp_path/'tool-shapes'; scratch.mkdir()
    _, shape = setup(scratch)
    for key in ('header_tool_receipt','header_tool_receipt_sha256'):
        output[key] = shape[key]
    failed = set(cproof['failed_contexts'])
    failures = {row['context_id']: row for row in cproof['failures']}
    for context, row in zip(request['contexts'], output['records']):
        doc = ET.fromstring(sample()[0]); doc.set('file',context['analysis_file'])
        cfg = doc.find('configuration')
        for child in list(cfg): cfg.remove(child)
        definitions = {'VALUE':next(a[8:] for a in context['invocation'] if a.startswith('-DVALUE='))}
        cfg.set('cfg','VALUE='+definitions['VALUE'])
        eff = ET.SubElement(cfg,'effective',std='c++20')
        ET.SubElement(eff,'define',value='VALUE='+definitions['VALUE'])
        for key, values in static._header_effective_inputs(context).items():
            for value in values: ET.SubElement(eff,key,value=value)
        is_failed = context['context_id'] in failed
        if is_failed:
            cfg.attrib.update(disposition='preprocess_error', checks_completed='false', completed='false',
                preprocessing_returned='false',preprocessing_had_output='true',normal_pass_started='false')
        else:
            for forced in static._header_effective_inputs(context)['forced_input']:
                ET.SubElement(cfg,'include',file=forced,parent='',kind='forced',entered='true')
        for stage in ('pre_simplification','normal_form_ast_validated'):
            tokens = ET.SubElement(cfg,'token_membership',stage=stage,
                captured='false' if is_failed else 'true',invalid='false',overflow='false')
            if not is_failed: ET.SubElement(tokens,'token_file',file=context['analysis_file'])
        packed, sha, encoding = static._encode_xml(ET.tostring(doc),compact=True)
        if is_failed:
            # Pinned simplecpp emits its separator even when the body is empty.
            message = '#error ' + failures[context['context_id']]['directive'].partition('error')[2].strip()
            errors = ET.Element('results',version='2'); ET.SubElement(errors,'cppcheck',version='2.17.1')
            children = ET.SubElement(errors,'errors')
            error = ET.SubElement(children,'error',id='preprocessorErrorDirective',severity='error',
                msg=message,verbose=message,file0=context['analysis_file'])
            ET.SubElement(error,'location',file=context['analysis_file'],line='2',column='2')
            ET.SubElement(children,'error',id='checkersReport',severity='information',
                msg='Active checkers: There was critical errors (use --checkers-report=<filename> to see details)')
            xml = ET.tostring(errors)
        else:
            xml = base64.b64decode(row['xml']).replace(b'Owned diagnostic',
                b'Active checkers: 167/856 (use --checkers-report=&lt;filename&gt; to see details)')
        row.update(xml=base64.b64encode(xml).decode(),xml_sha256=digest(xml),
            header_trace=packed,header_trace_sha256=sha,header_trace_encoding=encoding)
    primary_raw = _canonical(output)
    primary = static.validate_project_static(primary_raw,request)
    freq = clang.clang_fallback_request(request,primary,extended_budget=True,
        contention_aware=True,multi_file_diagnostics=True)
    inputs = (database,creq['targets'],snapshot,craw)
    if not freq['contexts']:
        result = (request,cproof,primary_raw,None)
        return result+(inputs,) if include_inputs else result
    fscratch = tmp_path/'clang-tool-shapes'; fscratch.mkdir()
    _,_,_, fshape = clang_fixture(fscratch)
    fdata = {'schema': 'nico.cpp-clang-fallback-evidence.v5',
        'request_sha256':digest(_canonical(freq)),'analyst_uid':1001,'version':observed(b'17.0.6\n'),
        'duration_ms':5,'records':[],
        **{k:fshape[k] for k in ('header_tool_receipt','header_tool_receipt_sha256')}}
    for c in freq['contexts']:
        cid = c['context_id']; source = c['analysis_file']
        trace = {'schema':'nico.clang-header-observer.v1','clang_version':'17.0.6','source':source,
            'context_id':cid,'standard':'c++20','translation_unit_started':False,
            'translation_unit_ended':False,'diagnostic_errors':True,'observation_overflow':False,
            'files':[{'path':source,'entered':1,'ast_decl_nodes':0,'ast_stmt_nodes':0,'ast_body_callbacks':0,
                'initially_system':False,'system_header_pragma_observed':False}]}
        packed, sha = clang._encode_plist(_canonical(trace))
        directive_text = failures[cid]['directive']
        body = directive_text.partition('error')[2].strip()
        execution = observed((source+':2:2: error: '+body+'\n    2 | '+directive_text+'\n'
                              +'      |  ^\n1 error generated.\n').encode())
        execution['exit_code'] = 1
        fdata['records'].append({'context_id':cid,'invocation':c['invocation'],
            'dropped_arguments':c['dropped_arguments'],'execution':execution,'plist':'','plist_sha256':None,
            'header_trace':packed,'header_trace_sha256':sha,'error':None})
    result = (request,cproof,primary_raw,_canonical(fdata))
    return result+(inputs,) if include_inputs else result


def validate(request, compiler, primary, fallback):
    if importlib.util.find_spec('nico.assessment_cpp_static_collection') is None:
        # Original behavior: substantive no-parse target failure is incomplete.
        original = static.validate_project_static(primary,request)
        if fallback:
            freq = clang.clang_fallback_request(request,original,extended_budget=True,
                contention_aware=True,multi_file_diagnostics=True)
            original = clang.merge_static_analysis(original,clang.validate_clang_fallback(fallback,freq,request))
        return {'collection_complete':original['complete'],'analysis':original}
    from nico.assessment_cpp_static_collection import validate_project_static_collection
    return validate_project_static_collection(primary,request,compiler,fallback_raw=fallback)


def test_captured_target_directive_does_not_stop_independent_static_collection(tmp_path):
    req,cproof,raw,fraw = fixture(tmp_path)
    proof = validate(req,cproof,raw,fraw)
    assert proof['collection_complete'] is True, 'captured no-parse outcome stopped independent collection'
    assert proof['analysis']['complete'] is False
    assert proof['analysis']['header_context_evidence_complete'] is False
    assert proof['failed_contexts'] == proof['unparsed_contexts'] == cproof['failed_contexts']
    assert len(proof['analysis']['analyzed_contexts']) == 2
    assert not proof['analysis']['analyzer_header_coverage_verified']


def test_current_all_success_collection_preserves_legacy_completion(tmp_path):
    req,cproof,raw,fraw = fixture(tmp_path,failing=False)
    proof = validate(req,cproof,raw,fraw)
    assert proof['collection_complete'] is True and proof['analysis']['complete'] is True
    assert proof['failed_contexts'] == proof['unparsed_contexts'] == []


def test_bare_error_native_separator_is_collected_without_analysis_success(tmp_path):
    req, compiler, raw, fallback = fixture(tmp_path, directive=b'#error')
    proof = validate(req, compiler, raw, fallback)
    assert proof['collection_complete'] is True
    assert proof['failed_contexts'] == proof['unparsed_contexts'] == compiler['failed_contexts']
    assert len(proof['failed_contexts']) == 2
    assert proof['analysis']['complete'] is False
    assert proof['analysis']['header_context_evidence_complete'] is False
    assert proof['analysis']['analyzer_header_coverage_verified'] is False


@pytest.mark.parametrize('field, message', [
    ('msg', '#error'), ('msg', '#error  '), ('msg', '#error\t'),
    ('msg', '#error unexpected'), ('verbose', '#error'),
])
def test_bare_error_rejects_any_unbound_message_instead_of_stripping_it(tmp_path, field, message):
    req, compiler, raw, fallback = fixture(tmp_path, directive=b'#error')
    assert validate(req, compiler, raw, fallback)['collection_complete'] is True
    document = json.loads(raw)
    row = next(row for row in document['records'] if row['context_id'] in compiler['failed_contexts'])
    xml = ET.fromstring(base64.b64decode(row['xml']))
    xml.find("errors/error[@id='preprocessorErrorDirective']").set(field, message)
    changed = ET.tostring(xml)
    row.update(xml=base64.b64encode(changed).decode(), xml_sha256=digest(changed))
    with pytest.raises(ValueError):
        validate(req, compiler, _canonical(document), fallback)


@pytest.mark.parametrize('fault',['missing-fallback','missing-record','missing-trace','false-plist',
    'timeout','truncated','permission','exit-two','wrong-body','wrong-location','extra-error',
    'forged-primary-success','normal-pass','parsed-token','clang-ast','clang-started',
    'clang-overflow','compiler-proof','downgrade','corrupt-primary'])
def test_missing_corrupt_downgraded_or_false_success_collection_is_rejected(tmp_path,fault):
    req,cp,raw,fraw = fixture(tmp_path)
    primary=json.loads(raw); fallback=json.loads(fraw); row=primary['records'][2]; fr=fallback['records'][0]
    if fault=='missing-fallback': fraw=None
    elif fault=='missing-record':fallback['records'].pop()
    elif fault=='missing-trace':fr.update(header_trace='',header_trace_sha256=None)
    elif fault=='false-plist':fr['plist'],fr['plist_sha256']=clang._encode_plist(b'fake')
    elif fault in {'timeout','truncated'}:fr['execution']['timed_out' if fault=='timeout' else 'output_truncated']=True
    elif fault=='permission':fr['error']='worker_clang_fallback_unavailable'
    elif fault=='exit-two':fr['execution']['exit_code']=2
    elif fault in {'wrong-body','extra-error'}:
        data=base64.b64decode(fr['execution']['output'])
        data=data.replace(b'error: owned rejection',b'error: another error') if fault=='wrong-body' else data+b'error: missing file\n'
        fr['execution'].update(output=base64.b64encode(data).decode(),output_sha256=digest(data))
    elif fault in {'wrong-location','forged-primary-success'}:
        doc=ET.fromstring(base64.b64decode(row['xml']))
        if fault=='wrong-location':doc.find('errors/error/location').set('line','1')
        else:doc.find('errors').remove(doc.find('errors/error'))
        data=ET.tostring(doc);row.update(xml=base64.b64encode(data).decode(),xml_sha256=digest(data))
    elif fault in {'normal-pass','parsed-token'}:
        doc=ET.fromstring(static._decode_xml(row['header_trace'],row['header_trace_sha256'],row['header_trace_encoding']))
        if fault=='normal-pass':doc.find('configuration').set('normal_pass_started','true')
        else:ET.SubElement(doc.find('configuration/token_membership'),'token_file',file=req['contexts'][2]['analysis_file'])
        packed,sha,encoding=static._encode_xml(ET.tostring(doc),compact=True)
        row.update(header_trace=packed,header_trace_sha256=sha,header_trace_encoding=encoding)
    elif fault in {'clang-ast','clang-started','clang-overflow'}:
        doc=json.loads(clang._decode_plist(fr['header_trace'],fr['header_trace_sha256']))
        if fault=='clang-ast':doc['files'][0]['ast_decl_nodes']=1
        elif fault=='clang-started':doc['translation_unit_started']=True
        else:doc['observation_overflow']=True
        fr['header_trace'],fr['header_trace_sha256']=clang._encode_plist(_canonical(doc))
    elif fault=='compiler-proof':cp=deepcopy(cp);cp['failed_contexts']=[]
    elif fault=='downgrade':req=deepcopy(req);req['schema']='nico.cpp-project-static-request.v3';req.pop('compiler_collection')
    elif fault=='corrupt-primary':row['xml_sha256']='0'*64
    if fault!='missing-fallback':fraw=_canonical(fallback)
    with pytest.raises(ValueError):validate(req,cp,_canonical(primary),fraw)


@pytest.mark.parametrize('fault',[None,'cleanup','corrupt-environment','missing-fallback-trace'])
def test_installed_static_stage_preserves_failed_outcome_after_full_bounded_collection(tmp_path,fault):
    from tests.test_cpp_project_static_stage import StaticDocker
    req,cp,raw,fraw,(database,targets,snapshot,craw) = fixture(tmp_path,include_inputs=True)
    source=tmp_path/'source';source.mkdir();(source/'unit.cpp').write_bytes(b'int value(){return VALUE;}\n')
    class CurrentDocker(StaticDocker):
        def __call__(self,argv,**kwargs):
            if env.ENV_PROGRAM in argv:
                self.calls.append((argv,kwargs));er=json.loads(kwargs['input_bytes'])
                value=environment_evidence(er);value['schema']='nico.cpp-static-environment.v2'
                for query in value['queries'].values():
                    query['predefines']=observed(base64.b64decode(query['predefines']['output'])+b'#define __cplusplus 202002L\n')
                if fault=='corrupt-environment':value['request_sha256']='0'*64
                return dict(exit_code=0,timed_out=False,output_truncated=False,output=_canonical(value))
            if static.PROGRAM in argv:
                self.calls.append((argv,kwargs));assert json.loads(kwargs['input_bytes'])==req
                return dict(exit_code=0,timed_out=False,output_truncated=False,output=raw)
            if clang.PROGRAM in argv:
                self.calls.append((argv,kwargs));value=json.loads(fraw)
                assert digest(kwargs['input_bytes'])==value['request_sha256']
                if fault=='missing-fallback-trace':value['records'][0].update(header_trace='',header_trace_sha256=None)
                return dict(exit_code=0,timed_out=False,output_truncated=False,output=_canonical(value))
            return super().__call__(argv,**kwargs)
    artifacts={};docker=CurrentDocker(targets,fault)
    def sink(key,raw):
        artifacts[key]=raw
        return dict(path='artifacts/'+key+'-'+digest(raw)+'.json',sha256=digest(raw),bytes=len(raw))
    result=static.run_project_static_stage(source,targets,'sha256:'+'a'*64,database,snapshot,craw,
        compiler_environment=True,header_provenance=True,collect_completed_compiler_failures=True,
        retain_artifact=sink,command=docker)
    assert result['schema']=='nico.cpp-project-static-stage.v4'
    assert result['complete'] is False and result['status']=='UNPROVEN'
    assert result['execution_budget_seconds']==1020 and result['wall_budget_seconds']==1030
    assert result['cleanup_verified'] is (fault!='cleanup')
    if fault:
        assert result['collection_complete'] is False
    else:
        assert result['collection_complete'] is True,result['error']
        assert result['error']=='worker_project_static_stage_target_failure'
        assert result['static_collection']==validate(req,cp,raw,fraw)
        assert result['analysis']['complete'] is False and not result['analysis']['header_context_evidence_complete']
        assert set(artifacts)=={'project-static-environment','project-static-evidence','project-static-clang-fallback'}
        assert len(result['static_collection']['attempted_contexts'])==4
        assert result['static_collection']['failed_contexts']==cp['failed_contexts']
