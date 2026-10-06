"""Reconstruct complete analyzer collection separately from target success.

The v1 supported failure is the generated #error already bound by the compiler
consumer. Both actual analyzer attempts and their no-parse dispositions remain
required. Missing outputs do not become successful analysis or header credit.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from nico.assessment_cpp_full_project import _json
from nico.assessment_cpp_project_compiler import _canonical, _digest
from nico.assessment_cpp_compiler_collection import collection_summary
from nico.assessment_cpp_project_static import validate_project_static, _decode_xml, _execution
from nico.assessment_cpp_clang_fallback import (
    clang_fallback_request, validate_clang_fallback, merge_static_analysis,
    _decode_plist, _execution as clang_execution,
)


def _require(value):
    if not value:
        raise ValueError('worker_project_static_collection_invalid')


def _primary_failure(row, failure):
    success, unused = _execution(row['execution'],93000)
    _require(success and row['error'] is None)
    xml = _decode_xml(row['xml'],row['xml_sha256'],row.get('xml_encoding','identity'))
    doc = ET.fromstring(xml)
    errors = doc.findall('errors/error')
    _require(len(errors)==2 and sorted(e.get('id') for e in errors)==
             ['checkersReport','preprocessorErrorDirective'])
    error = next(e for e in errors if e.get('id')=='preprocessorErrorDirective')
    checker = next(e for e in errors if e.get('id')=='checkersReport')
    _require(checker.get('severity')=='information'
        and checker.get('msg')=='Active checkers: There was critical errors (use --checkers-report=<filename> to see details)'
        and not checker.findall('location'))
    body = re.fullmatch(r'[ \t]*#[ \t]*error(?:[ \t]+(.*))?',failure['directive'])[1] or ''
    message = '#error' + (' '+body.strip() if body.strip() else '')
    locations = error.findall('location')
    _require(error.get('severity')=='error' and error.get('msg')==message
        and error.get('verbose',message)==message and error.get('file0')==failure['analysis_file']
        and len(locations)==1 and locations[0].attrib=={
            'file':failure['analysis_file'],'line':str(failure['line']),'column':str(failure['column'])})
    trace = _decode_xml(row['header_trace'],row['header_trace_sha256'],row['header_trace_encoding'])
    header = ET.fromstring(trace); cfg = header.find('configuration')
    _require(cfg is not None and header.get('file')==failure['analysis_file']
        and header.find('file_end').get('normal_return')=='true'
        and cfg.get('disposition')=='preprocess_error'
        and all(cfg.get(k)=='false' for k in ('checks_completed','completed','preprocessing_returned',
            'normal_pass_started','observation_overflow','token_logical_remap_observed'))
        and cfg.get('preprocessing_had_output')=='true')
    memberships = cfg.findall('token_membership')
    _require(len(memberships)==2 and all(not list(m) and m.get('captured')=='false'
        and m.get('invalid')=='false' and m.get('overflow')=='false' for m in memberships))
    return {'context_id':failure['context_id'],'classification':failure['classification'],
        'source_sha256':failure['source_sha256'],'path':failure['path'],
        'cppcheck_xml_sha256':row['xml_sha256'],'cppcheck_trace_sha256':row['header_trace_sha256']}


def _fallback_failure(row, failure):
    _require(row['error'] is None and row['execution'] is not None
        and row['execution']['exit_code']==1 and not row['execution']['timed_out']
        and not row['execution']['output_truncated']
        and row['plist']=='' and row['plist_sha256'] is None
        and row['header_trace'] and row['header_trace_sha256'])
    unused, output = clang_execution(row['execution'],123000)
    text = output.decode('utf-8','strict')
    _require('\0' not in text and '\r' not in text)
    body = re.fullmatch(r'[ \t]*#[ \t]*error(?:[ \t]+(.*))?',failure['directive'])[1] or ''
    expected = (failure['analysis_file']+':'+str(failure['line'])+':'+str(failure['column'])
                +': error: '+body.strip())
    diagnostic_seen = terminal_seen = 0
    for line in text.splitlines():
        if line==expected:
            diagnostic_seen+=1
        elif line=='1 error generated.':
            terminal_seen+=1
        elif line and not (re.fullmatch(r'[ \t]*[1-9][0-9]*[ \t]*\|.*',line)
                            or re.fullmatch(r'[ \t]*\|[ \t]*[\^~]+[ \t]*',line)):
            raise ValueError('worker_project_static_collection_diagnostic_invalid')
    _require(diagnostic_seen==1 and terminal_seen==1)
    trace = _json(_decode_plist(row['header_trace'],row['header_trace_sha256']))
    _require(trace['diagnostic_errors'] is True and trace['observation_overflow'] is False
        and trace['translation_unit_started'] is False and trace['translation_unit_ended'] is False
        and any(f['path']==failure['analysis_file'] and f['entered']>0 for f in trace['files'])
        and all(f[k]==0 for f in trace['files']
                for k in ('ast_decl_nodes','ast_stmt_nodes','ast_body_callbacks')))
    return {'clang_output_sha256':row['execution']['output_sha256'],
            'clang_trace_sha256':row['header_trace_sha256'],'clang_plist_present':False}


def validate_project_static_collection(primary_raw, request, compiler_collection, *, fallback_raw=None):
    """Consume a separately reconstructed compiler proof and actual native bytes.

    Callers rebuild the compiler proof from raw compiler bytes and the immutable
    request/snapshot before passing it here. The current static request binds
    its exact digest; receipt-controlled flags cannot select historical rules.
    """
    try:
        _require(request['schema']=='nico.cpp-project-static-request.v4'
            and compiler_collection['schema']=='nico.cpp-project-compiler-collection.v1'
            and compiler_collection['collection_complete'] is True
            and request['compiler_collection']==collection_summary(compiler_collection))
        primary = validate_project_static(primary_raw,request)
        native = _json(primary_raw)
        required = primary['required_contexts']
        _require(required==compiler_collection['compiler']['required_contexts']
            and primary['attempted_contexts']==required)
        failed = compiler_collection['failed_contexts']
        _require(failed==compiler_collection['unparsed_contexts']
            and failed==[f['context_id'] for f in compiler_collection['failures']])
        freq = clang_fallback_request(request,primary,extended_budget=True,
            contention_aware=True,multi_file_diagnostics=True)
        fallback = None; fallback_native = None
        if freq['contexts']:
            _require(isinstance(fallback_raw,bytes) and bool(fallback_raw))
            fallback = validate_clang_fallback(fallback_raw,freq,request)
            _require(fallback['attempted_contexts']==fallback['required_contexts'])
            fallback_native = _json(fallback_raw)
            analysis = merge_static_analysis(primary,fallback)
        else:
            _require(fallback_raw is None)
            analysis = primary
        expected_analyzed = [cid for cid in required if cid not in set(failed)]
        _require(analysis['analyzed_contexts']==expected_analyzed)
        headers = {h['context_id']:h for h in analysis['header_context_evidence']}
        _require(list(headers)==required)
        for cid in expected_analyzed:
            h = headers[cid]
            _require(h['normal_pass_completed'] is True and (
                h.get('native_execution_verified') is True if h.get('analysis_method')
                else h.get('physical_token_origin_verified') is True))
        primary_by_id = {r['context_id']:r for r in native['records']}
        fallback_by_id = {r['context_id']:r for r in (fallback_native or {}).get('records',[])}
        outcomes = []
        for failure in compiler_collection['failures']:
            cid = failure['context_id']
            _require(cid not in primary['analyzed_contexts'] and cid in fallback_by_id
                and cid not in (fallback or {})['analyzed_contexts']
                and headers[cid]['normal_pass_completed'] is False
                and not headers[cid]['parsed_token_files'] and not headers[cid]['normal_pass_token_files'])
            outcomes.append({**_primary_failure(primary_by_id[cid],failure),
                             **_fallback_failure(fallback_by_id[cid],failure)})
        return {'schema':'nico.cpp-project-static-collection.v1','collection_complete':True,
            'required_contexts':required,'attempted_contexts':primary['attempted_contexts'],
            'analyzed_contexts':analysis['analyzed_contexts'],'failed_contexts':list(failed),
            'unparsed_contexts':list(failed),'target_outcomes':outcomes,'analysis':analysis,
            'native_evidence_sha256':_digest(primary_raw),
            'fallback_evidence_sha256':_digest(fallback_raw) if fallback_raw is not None else None,
            'request_sha256':_digest(_canonical(request)),
            'compiler_collection_sha256':_digest(_canonical(compiler_collection))}
    except (KeyError,TypeError,IndexError,UnicodeError,ET.ParseError) as error:
        raise ValueError('worker_project_static_collection_invalid') from error
