"""Synthetic installed contract controls; actual owned traces live separately."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from nico import assessment_cpp_project_static as static
from nico.assessment_cpp_header_evidence import HEADER_SCHEMA, header_summary
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_header_evidence import sample
from tests.test_cpp_project_static import native
from tests.test_cpp_static_environment import fixture, evidence, observed, api


def setup(tmp_path):
    database,targets,snapshot,compiler,raw=fixture(tmp_path)
    env_request=api().environment_request(compiler,raw,'sha256:'+'a'*64)
    env_raw=evidence(env_request)
    for query in env_raw['queries'].values():
        data=base64.b64decode(query['predefines']['output'])+b'#define __cplusplus 202002L\n'
        query['predefines']=observed(data)
    model=api().validate_environment(_canonical(env_raw),env_request)
    request=static.project_static_request(database,targets,snapshot,raw,environment=model,header_provenance=True)
    output=native(request,'checkersReport')
    output['schema']='nico.cpp-project-static-evidence.v3'
    manifest=Path('scripts/cppcheck-header-evidence/manifest.json')
    value=json.loads(manifest.read_bytes())
    from nico.assessment_cpp_header_evidence import HEADER_TOOL_MANIFEST_SHA256,HEADER_APPLIER_SHA256
    tool=_canonical({'schema':'nico.cppcheck-header-tool.v1','manifest_sha256':HEADER_TOOL_MANIFEST_SHA256,
        'upstream_commit':value['upstream_commit'],'patch_sha256':value['patch_sha256'],'sources':value['sources'],
        'trace_schema':HEADER_SCHEMA,'application_script_sha256':HEADER_APPLIER_SHA256,
        'base_tool_version':'2.17.1','qualification_completed':False})
    output.update(header_tool_receipt=base64.b64encode(tool).decode(),header_tool_receipt_sha256=hashlib.sha256(tool).hexdigest())
    for context,row in zip(request['contexts'],output['records']):
        original,args=sample();document=ET.fromstring(original)
        document.set('file',context['analysis_file']);cfg=document.find('configuration')
        for child in list(cfg):cfg.remove(child)
        definitions={}
        for arg in context['invocation']:
            if arg.startswith('-D'):
                name,sep,value=arg[2:].partition('=');definitions[name]=value if sep else '1'
            if arg.startswith('-U'):definitions.pop(arg[2:],None)
        cfg.set('cfg',';'.join(name+'='+value for name,value in sorted(definitions.items())))
        effective=ET.SubElement(cfg,'effective',std='c++20')
        for name,value in sorted(definitions.items()):ET.SubElement(effective,'define',value=name+'='+value)
        for key,values in static._header_effective_inputs(context).items():
            for value in values:ET.SubElement(effective,key,value=value)
        for forced in static._header_effective_inputs(context)['forced_input']:
            ET.SubElement(cfg,'include',file=forced,parent='',kind='forced',entered='true')
        for stage in ('pre_simplification','normal_form_ast_validated'):
            tokens=ET.SubElement(cfg,'token_membership',stage=stage,captured='true',invalid='false',overflow='false')
            ET.SubElement(tokens,'token_file',file=context['analysis_file'])
        trace=ET.tostring(document)
        packed,digest,encoding=static._encode_xml(trace,compact=True)
        xml=base64.b64decode(row['xml']).replace(b'Owned diagnostic',b'Active checkers: 167/856 (use --checkers-report=&lt;filename&gt; to see details)')
        row.update(xml=base64.b64encode(xml).decode(),xml_sha256=hashlib.sha256(xml).hexdigest(),
            header_trace=packed,header_trace_sha256=digest,header_trace_encoding=encoding)
    return request,output


def test_header_worker_program_is_installed_without_application_imports():
    namespace={'__name__':'bounded_contract_control'}
    exec(static.PROGRAM.rsplit('\nrun_project_static()',1)[0],namespace)
    assert callable(namespace['validate_header_tool_receipt'])
    assert callable(namespace['_header_standard'])
    assert namespace['HEADER_SCHEMA']==HEADER_SCHEMA


def test_analyzer_macro_adaptation_preserves_original_ordered_compiler_arguments():
    original=['/usr/local/bin/g++','-DFIRST=1','-DMODE=1','-UMODE','-DOTHER=4','-DMODE=7','-UFIRST','source.cpp']
    saved=list(original)
    normalized=static._analyzer_macro_arguments(original)
    assert normalized==['/usr/local/bin/g++','-DOTHER=4','-DMODE=7','-UFIRST','source.cpp']
    assert original==saved


@pytest.mark.parametrize('flag',['-fPIC','-fpic','-fPIE','-fpie'])
def test_bound_compiler_predefines_replace_analyzer_pic_scalar_inference(flag):
    original=['/usr/local/bin/g++',flag,'source.cpp']
    assert static._analyzer_macro_arguments(original)==['/usr/local/bin/g++','source.cpp']
    assert original[1]==flag


def test_header_contract_preserves_contexts_and_unvisited_population(tmp_path):
    request,output=setup(tmp_path)
    proof=static.validate_project_static(_canonical(output),request)
    assert proof['complete'] and proof['header_context_evidence_complete']
    assert proof['header_population_complete'] is False
    assert len(proof['header_context_evidence'])==3
    assert proof['header_unvisited_files']
    assert not proof['analyzer_header_coverage_verified']
    assert header_summary(proof)['header_context_evidence_count']==3
    assert all('--std=c++20' in row['analyzer_invocation'] for row in request['contexts'])


def test_uppercase_header_inventory_is_retained_as_unvisited(tmp_path):
    request,output=setup(tmp_path)
    request['targets']['Owned.H']='0'*64
    output['request_sha256']=hashlib.sha256(_canonical(request)).hexdigest()
    proof=static.validate_project_static(_canonical(output),request)
    assert '/work/source/Owned.H' in proof['header_population']
    assert '/work/source/Owned.H' in proof['header_unvisited_files']


@pytest.mark.parametrize('locale,included,parsed,unvisited',[
    ('en','included=3/4','parsed token files=2/4','unvisited=1'),
    ('es-MX','incluidos=3/4','con tokens analizados=2/4','no visitados=1')])
def test_bilingual_report_preserves_different_header_states(locale,included,parsed,unvisited):
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    digest='a'*64
    population={name:dict(included_contexts=['c'] if present else [],parsed_contexts=['c'] if tokens else [],
        analyzed_contexts=['c'] if tokens else []) for name,present,tokens in [
            ('active.h',True,True),('generated.h',True,True),('macro_only.h',True,False),('unvisited.h',False,False)]}
    record={'commit_sha':'b'*40,'raw_artifact_retention_complete':True,'raw_artifact_sha256':digest,
        'current_run':True,'exact_commit_match':True,'execution_observed_for_this_report':True,
        'worker_provenance':{'profile':'cpp-configure-first-v2','receipt_sha256':digest,'identity':{'run_id':'run','revision':'b'*40}},
        'cpp_build_evidence':{'profile':'cpp-configure-first-v2','header_evidence':{'population':population,'population_complete':False}}}
    result=enrich_scanner_stage({'report_language':locale,'identity':{'run_id':'run','commit_sha':'b'*40},
        'scanner_execution_records':[record]},{'summary':'','evidence':[],'unavailable':[]})
    text=' '.join([result['summary'],*result['evidence'],*result['unavailable']])
    assert included in text and parsed in text and unvisited in text
    assert result['unavailable']


@pytest.mark.parametrize('fault',['missing','corrupt','digest','tool','standard','source','downgrade',
    'include_context','forced_context','undef_context','forced_unobserved'])
def test_header_transport_rejects_missing_corrupt_wrong_and_downgraded_evidence(tmp_path,fault):
    request,output=setup(tmp_path);row=output['records'][0]
    if fault=='missing':row.update(header_trace='',header_trace_sha256=None)
    if fault=='corrupt':row['header_trace']='bad'
    if fault=='digest':row['header_trace_sha256']='0'*64
    if fault=='tool':output['header_tool_receipt_sha256']='0'*64
    if fault in ('standard','source','include_context','forced_context','undef_context','forced_unobserved'):
        raw=static._decode_xml(row['header_trace'],row['header_trace_sha256'],row['header_trace_encoding'])
        doc=ET.fromstring(raw)
        if fault=='standard':doc.find('configuration/effective').set('std','c++26')
        elif fault=='source':doc.set('file','/work/source/unbound.cpp')
        elif fault=='include_context':ET.SubElement(doc.find('configuration/effective'),'include_path',value='/work/source/unbound/')
        elif fault=='forced_context':doc.find('configuration/effective/forced_input').set('value','/work/analysis/predefines/another-context.h')
        elif fault=='undef_context':ET.SubElement(doc.find('configuration/effective'),'undef',value='CTX')
        else:doc.find('configuration').remove(doc.find('configuration/include'))
        packed,digest,encoding=static._encode_xml(ET.tostring(doc),compact=True)
        row.update(header_trace=packed,header_trace_sha256=digest,header_trace_encoding=encoding)
    if fault=='downgrade':output['schema']='nico.cpp-project-static-evidence.v2'
    with pytest.raises(ValueError):static.validate_project_static(_canonical(output),request)
