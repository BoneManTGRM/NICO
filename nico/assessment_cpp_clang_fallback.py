"""Bounded Clang Static Analyzer fallback for Cppcheck-incomplete C/C++ contexts.

This is a second substantive analyzer, not a compiler-success substitute. It is
invoked only for contexts that the primary Cppcheck pass actually attempted but
could not complete. All source/revision/context bindings are inherited from the
validated primary request and its immutable evidence.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

from nico.assessment_cpp_project_compiler import _canonical, _digest, _verify_input, GENERATED_FILE_LIMIT
from nico.assessment_cpp_compiler_evidence import _run, _regular_bytes
from nico.assessment_cpp_generated_context import _stable_bytes
from nico.assessment_cpp_clang_header_evidence import (CLANG_HEADER_LIMIT,CLANG_HEADER_MANIFEST_SHA256,
    CLANG_HEADER_SOURCE_SHA256,CLANG_HEADER_SDK_SHA256,CLANG_HEADER_RUNTIME_SHA256,
    _clang_require,_clang_json,validate_clang_header_tool_receipt,validate_clang_header_trace)

CLANG = '/usr/lib/llvm-17/bin/clang'
CLANGXX = '/usr/lib/llvm-17/bin/clang++'
VERSION = '17.0.6'
LIMITS = {'wall_seconds': 180, 'case_seconds': 45, 'parallel': 4}
# Explicit v2 admission retains v1 evidence semantics and the parent stage cap.
EXTENDED_LIMITS = {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 4}
# v4 is scheduling-only; it does not admit the unpublished v3 timeout extension.
LOW_CONTENTION_LIMITS = {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
STREAM_LIMIT = 32 * 1024 * 1024
REQUEST_LIMIT = 8 * 1024 * 1024
PLIST_LIMIT = 4 * 1024 * 1024
STORED_PLIST_LIMIT = 4 * 1024 * 1024
HEADER_PLUGIN='/opt/nico-clang-header-observer.so'

_DROP_EXACT = frozenset({
    '-c', '-MD', '-MMD', '-MP', '-fsyntax-only',
    '-fno-extended-identifiers', '-fstack-reuse=none',
})
_DROP_PREFIX = ('-W',)


def _fallback_plan(context, *, header_provenance=False, multi_file_diagnostics=False):
    invocation = context.get('invocation')
    source = context.get('analysis_file')
    if (not isinstance(invocation, list) or not 2 <= len(invocation) <= 4096
            or invocation[0] not in {'/usr/local/bin/gcc', '/usr/local/bin/g++'}
            or not isinstance(source, str) or invocation.count(source) != 1):
        raise ValueError('worker_clang_fallback_invocation_invalid')
    compiler = CLANGXX if invocation[0].endswith('g++') else CLANG
    kept = [compiler, '-Wno-unknown-warning-option', '-Wno-unused-command-line-argument']
    dropped = []
    index = 1
    while index < len(invocation):
        arg = invocation[index]; index += 1
        if arg == source:
            continue
        if arg in {'-o', '-MF', '-MT', '-MQ'}:
            if index >= len(invocation) or invocation[index].startswith('-'):
                raise ValueError('worker_clang_fallback_output_invalid')
            dropped += [arg, invocation[index]]; index += 1; continue
        if arg in {'-I', '-isystem'}:
            if index >= len(invocation) or not invocation[index].startswith('/'):
                raise ValueError('worker_clang_fallback_include_invalid')
            kept += [arg, invocation[index]]; index += 1; continue
        if arg in _DROP_EXACT or arg.startswith(_DROP_PREFIX):
            dropped.append(arg); continue
        if (arg.startswith(('-D', '-U', '-I', '-std=', '-O', '-g', '-m', '-fmacro-prefix-map='))
                or arg in {'-pthread', '-fPIC', '-fPIE', '-fpic', '-fpie', '-fno-pie',
                           '-fno-exceptions', '-fno-rtti', '-fno-omit-frame-pointer',
                           '-fno-strict-aliasing', '-fwrapv', '-ftrapv',
                           '-fstack-protector-all', '-fstack-clash-protection',
                           '-fcf-protection=full', '-fvisibility=hidden', '-pedantic'}):
            kept.append(arg); continue
        raise ValueError('worker_clang_fallback_option_unsupported')
    stem = '/work/analysis/clang-fallback/u' + str(context['index'])
    observer=(['-Xclang','-load','-Xclang',HEADER_PLUGIN,
        '-Xanalyzer','-analyzer-checker=nico.HeaderEvidence'] if header_provenance else [])
    output_format='plist-multi-file' if header_provenance or multi_file_diagnostics else 'plist'
    return [*kept, '--analyze', *observer, '-Xanalyzer', '-analyzer-output='+output_format,
            '-fno-color-diagnostics', source, '-o', stem + '.plist'], dropped


def _request_limits(request):
    if not isinstance(request, dict) or not isinstance(request.get('schema'), str):
        raise ValueError('worker_clang_fallback_request_invalid')
    versions = {'nico.cpp-clang-fallback-request.v1': LIMITS,
                'nico.cpp-clang-fallback-request.v2': EXTENDED_LIMITS,
                'nico.cpp-clang-fallback-request.v4': LOW_CONTENTION_LIMITS}
    versions['nico.cpp-clang-fallback-request.v5']=LOW_CONTENTION_LIMITS
    versions['nico.cpp-clang-fallback-request.v6']=LOW_CONTENTION_LIMITS
    versions['nico.cpp-clang-fallback-request.v7']=LOW_CONTENTION_LIMITS
    expected = versions.get(request.get('schema'))
    limits = request.get('limits')
    if (expected is None or not isinstance(limits, dict) or limits != expected
            or any(type(value) is not int for value in limits.values())):
        raise ValueError('worker_clang_fallback_request_invalid')
    return dict(expected)


def clang_fallback_request(primary_request, primary_proof, *, extended_budget=False, contention_aware=False, multi_file_diagnostics=False):
    if (type(extended_budget) is not bool or type(contention_aware) is not bool
            or type(multi_file_diagnostics) is not bool
            or (contention_aware and not extended_budget)
            or (multi_file_diagnostics and not contention_aware)):
        raise ValueError('worker_clang_fallback_request_invalid')
    if (not isinstance(primary_request, dict)
            or primary_request.get('schema') not in {'nico.cpp-project-static-request.v1', 'nico.cpp-project-static-request.v2',
                                                    'nico.cpp-project-static-request.v3',
                                                    'nico.cpp-project-static-request.v4'}
            or not isinstance(primary_proof, dict)
            or primary_proof.get('native_evidence_sha256') is None):
        raise ValueError('worker_clang_fallback_primary_invalid')
    required = [row['context_id'] for row in primary_request.get('contexts', [])]
    if primary_proof.get('required_contexts') != required:
        raise ValueError('worker_clang_fallback_population_invalid')
    attempted = set(primary_proof.get('attempted_contexts') or [])
    analyzed = set(primary_proof.get('analyzed_contexts') or [])
    header_provenance=primary_request['schema'] in {'nico.cpp-project-static-request.v3','nico.cpp-project-static-request.v4'}
    current_headers=primary_request['schema']=='nico.cpp-project-static-request.v4'
    headers={row['context_id']:row for row in primary_proof.get('header_context_evidence',[])}
    missing = [cid for cid in required if cid in attempted and (
        cid not in analyzed or current_headers and not (
            headers.get(cid,{}).get('normal_pass_completed') is True
            and headers.get(cid,{}).get('physical_token_origin_verified') is True))]
    if header_provenance and not contention_aware:
        raise ValueError('worker_clang_fallback_header_policy_invalid')
    by_id = {row['context_id']: row for row in primary_request['contexts']}
    contexts = []
    for cid in missing:
        row = by_id[cid]; argv, dropped = _fallback_plan(row,header_provenance=header_provenance,multi_file_diagnostics=multi_file_diagnostics)
        contexts.append({'context_id': cid, 'index': row['index'], 'analysis_file': row['analysis_file'],
            'invocation': argv, 'dropped_arguments': dropped,
            'source_dependencies': dict(row['source_dependencies']),
            'generated_dependencies': dict(row['generated_dependencies'])})
    result = {'schema': ('nico.cpp-clang-fallback-request.v7' if current_headers else 'nico.cpp-clang-fallback-request.v5' if header_provenance else 'nico.cpp-clang-fallback-request.v6' if multi_file_diagnostics else 'nico.cpp-clang-fallback-request.v4' if contention_aware
                         else 'nico.cpp-clang-fallback-request.v2' if extended_budget
                         else 'nico.cpp-clang-fallback-request.v1'), 'tool_version': VERSION,
        'primary_request_sha256': _digest(_canonical(primary_request)),
        'cppcheck_evidence_sha256': primary_proof['native_evidence_sha256'],
        'compiler_evidence_sha256': primary_request['compiler_evidence_sha256'],
        'required_contexts': required, 'primary_analyzed_contexts': primary_proof['analyzed_contexts'],
        'contexts': contexts, 'limits': dict(LOW_CONTENTION_LIMITS if contention_aware
                                            else EXTENDED_LIMITS if extended_budget else LIMITS)}
    if 'compiler_environment' in primary_request:
        result['compiler_environment_sha256'] = primary_request['compiler_environment']['native_evidence_sha256']
    if header_provenance:
        result.update(header_tool_manifest_sha256=CLANG_HEADER_MANIFEST_SHA256,
            header_source_targets=dict(primary_request['targets']),
            header_generated_files=dict(primary_request['generated_files']))
    if len(_canonical(result)) > REQUEST_LIMIT:
        raise ValueError('worker_clang_fallback_request_limit')
    return result


def _encode_plist(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > PLIST_LIMIT:
        raise ValueError('worker_clang_fallback_plist_limit')
    stored = zlib.compress(raw, 9)
    if len(stored) > STORED_PLIST_LIMIT:
        raise ValueError('worker_clang_fallback_plist_limit')
    return base64.b64encode(stored).decode('ascii'), _digest(raw)


def _decode_plist(value, digest):
    if not isinstance(value, str) or not isinstance(digest, str):
        raise ValueError('worker_clang_fallback_plist_digest')
    try:
        stored = base64.b64decode(value, validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(stored, PLIST_LIMIT + 1)
    except (ValueError, TypeError, zlib.error) as exc:
        raise ValueError('worker_clang_fallback_plist_digest') from exc
    if (len(raw) > PLIST_LIMIT or inflater.unconsumed_tail or inflater.unused_data
            or not inflater.eof or _digest(raw) != digest):
        raise ValueError('worker_clang_fallback_plist_digest')
    return raw


def collect_clang_fallback(request, *, wall_budget_ms=None):
    import resource
    limits = _request_limits(request)
    if wall_budget_ms is not None and (type(wall_budget_ms) is not int
            or not 0 < wall_budget_ms <= limits['wall_seconds'] * 1000):
        raise ValueError('worker_clang_fallback_request_invalid')
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_clang_fallback_identity')
    fields = {'schema','tool_version','primary_request_sha256','cppcheck_evidence_sha256',
              'compiler_evidence_sha256','required_contexts','primary_analyzed_contexts','contexts','limits'}
    if 'compiler_environment_sha256' in request:
        fields.add('compiler_environment_sha256')
    header_provenance=request.get('schema') in {'nico.cpp-clang-fallback-request.v5','nico.cpp-clang-fallback-request.v7'}
    if header_provenance:
        fields|={'header_tool_manifest_sha256','header_source_targets','header_generated_files'}
    if (not isinstance(request, dict) or set(request) != fields
            or request.get('tool_version') != VERSION
            or not isinstance(request.get('contexts'), list) or len(request['contexts']) > 20000):
        raise ValueError('worker_clang_fallback_request_invalid')
    parent = Path('/work/analysis'); info = parent.lstat()
    if (parent.resolve(strict=True) != parent or info.st_uid != 1001 or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('worker_clang_fallback_private_directory_invalid')
    directory = parent / 'clang-fallback'; directory.mkdir(mode=0o700)
    resource.setrlimit(resource.RLIMIT_FSIZE, (PLIST_LIMIT, PLIST_LIMIT))
    environment = {'PATH':'/usr/lib/llvm-17/bin:/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8',
        'HOME':str(directory),'TMPDIR':str(directory),'LD_LIBRARY_PATH':'/usr/local/lib64:/usr/local/lib'}
    # A parent may allocate less than the maximum because all phases share
    # one envelope. Finish and serialize every record, including unstarted or
    # timed-out contexts, before that parent's timeout discards the response.
    start=time.monotonic(); deadline=start+(limits['wall_seconds'] if wall_budget_ms is None
        else wall_budget_ms / 1000)
    header_tool_raw=None
    if header_provenance:
        if request['header_tool_manifest_sha256']!=CLANG_HEADER_MANIFEST_SHA256:
            raise ValueError('worker_clang_fallback_header_tool_invalid')
        header_tool_raw=_regular_bytes('/opt/nico-clang-header-observer.json',65536)
        tool=validate_clang_header_tool_receipt(header_tool_raw)
        if _digest(_regular_bytes(HEADER_PLUGIN,4*1024*1024))!=tool['plugin_sha256']:
            raise ValueError('worker_clang_fallback_header_binary_invalid')
        for path,sha in request['header_source_targets'].items():_verify_input('/work/source',path,sha)
        for path,item in request['header_generated_files'].items():
            _verify_input('/work/analysis/generated-baseline',path,item['sha256'],item['bytes'],True)
    version=_run([CLANG,'-dumpversion'],str(directory/'version'),min(deadline,start+5),environment)
    version_ok=(version['exit_code']==0 and not version['timed_out'] and not version['output_truncated']
                and base64.b64decode(version['output'],validate=True).strip()==VERSION.encode())

    def one(context):
        record={'context_id':context['context_id'],'invocation':context['invocation'],
                'dropped_arguments':context['dropped_arguments'],'execution':None,
                'plist':'','plist_sha256':None,'error':None}
        if header_provenance:
            record.update(header_trace='',header_trace_sha256=None)
        try:
            if not version_ok: raise ValueError('worker_clang_fallback_tool_version')
            if time.monotonic()>=deadline: raise ValueError('worker_clang_fallback_deadline')
            for path,sha in context['source_dependencies'].items(): _verify_input('/work/source',path,sha)
            for path,sha in context['generated_dependencies'].items(): _verify_input('/work/analysis/generated-baseline',path,sha,None,True)
            stem=str(directory/('u'+str(context['index'])))
            native_environment=dict(environment)
            if header_provenance:
                native_environment.update(NICO_CLANG_HEADER_OUTPUT=stem+'.header.json',
                    NICO_CLANG_HEADER_CONTEXT=context['context_id'])
            # Input verification can consume the remaining shared allocation.
            # Preserve an unstarted record instead of spawning expired work.
            dispatch_start = time.monotonic()
            if dispatch_start >= deadline: raise ValueError('worker_clang_fallback_deadline')
            record['execution']=_run(context['invocation'],stem,min(deadline,dispatch_start+limits['case_seconds']),native_environment)
            plist_path=Path(stem+'.plist')
            if plist_path.exists():
                raw=_regular_bytes(plist_path,PLIST_LIMIT)
                record['plist'],record['plist_sha256']=_encode_plist(raw)
            if header_provenance:
                raw=_regular_bytes(stem+'.header.json',CLANG_HEADER_LIMIT)
                record['header_trace'],record['header_trace_sha256']=_encode_plist(raw)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            code=str(exc); record['error']=code if re.fullmatch(r'worker_clang_fallback_[a-z_]+',code) else 'worker_clang_fallback_unavailable'
        return record
    with ThreadPoolExecutor(max_workers=limits['parallel']) as pool:
        records=list(pool.map(one,request['contexts']))
    result={'schema':request['schema'].replace('-request.', '-evidence.'),'request_sha256':_digest(_canonical(request)),
            'analyst_uid':os.getuid(),'version':version,'records':records,'duration_ms':int((time.monotonic()-start)*1000)}
    if wall_budget_ms is not None:
        result['wall_budget_ms'] = wall_budget_ms
    if header_provenance:
        result.update(header_tool_receipt=base64.b64encode(header_tool_raw).decode(),
            header_tool_receipt_sha256=_digest(header_tool_raw))
    if len(_canonical(result))>STREAM_LIMIT: raise ValueError('worker_clang_fallback_output_limit')
    return result


def _execution(value, maximum):
    from nico.assessment_cpp_configuration import decode_stream
    if (not isinstance(value,dict) or set(value)!={'exit_code','timed_out','output_truncated','duration_ms','output','output_sha256'}
            or type(value['exit_code']) is not int or not -255<=value['exit_code']<=255
            or any(type(value[k]) is not bool for k in ('timed_out','output_truncated'))
            or type(value['duration_ms']) is not int or not 0<=value['duration_ms']<=maximum):
        raise ValueError('worker_clang_fallback_execution_invalid')
    raw=decode_stream(value['output'])
    if len(raw)>65536 or _digest(raw)!=value['output_sha256']: raise ValueError('worker_clang_fallback_execution_digest')
    return value['exit_code']==0 and not value['timed_out'] and not value['output_truncated'],raw


def _clang_standard(context):
    """Pinned17.0.6 LangStandards.def aliases; default language remains explicit."""
    values=[arg[5:] for arg in context['invocation'] if arg.startswith('-std=')]
    standard=values[-1] if values else ('gnu++17' if context['invocation'][0].endswith('g++') else 'gnu17')
    aliases={'c90':'c89','gnu90':'gnu89','c9x':'c99','gnu9x':'gnu99','c1x':'c11','gnu1x':'gnu11',
        'c18':'c17','gnu18':'gnu17','c++03':'c++98','gnu++03':'gnu++98','c++0x':'c++11','gnu++0x':'gnu++11',
        'c++1y':'c++14','gnu++1y':'gnu++14','c++1z':'c++17','gnu++1z':'gnu++17','c++2a':'c++20','gnu++2a':'gnu++20',
        'c++2b':'c++23','gnu++2b':'gnu++23','c++26':'c++2c','gnu++26':'gnu++2c',
        'iso9899:1990':'c89','iso9899:1999':'c99','iso9899:199x':'c99','iso9899:2011':'c11',
        'iso9899:201x':'c11','iso9899:2017':'c17','iso9899:2018':'c17'}
    return aliases.get(standard,standard)


def validate_clang_fallback(raw, request, primary_request, *, wall_budget_ms=None):
    from nico.assessment_cpp_full_project import _json
    limits = _request_limits(request)
    if not isinstance(raw,bytes) or not 0<len(raw)<=STREAM_LIMIT: raise ValueError('worker_clang_fallback_output_limit')
    evidence=_json(raw)
    if wall_budget_ms is not None and (type(wall_budget_ms) is not int
            or not 0 < wall_budget_ms <= limits['wall_seconds'] * 1000
            or evidence.get('wall_budget_ms') != wall_budget_ms):
        raise ValueError('worker_clang_fallback_evidence_invalid')
    header_provenance=request['schema'] in {'nico.cpp-clang-fallback-request.v5','nico.cpp-clang-fallback-request.v7'}
    if (primary_request.get('schema')=='nico.cpp-project-static-request.v4') != (
            request['schema']=='nico.cpp-clang-fallback-request.v7'):
        raise ValueError('worker_clang_fallback_header_policy_invalid')
    fields={'schema','request_sha256','analyst_uid','version','records','duration_ms'}
    allocated_ms = limits['wall_seconds'] * 1000
    if 'wall_budget_ms' in evidence:
        fields.add('wall_budget_ms')
        allocated_ms = evidence['wall_budget_ms']
        if type(allocated_ms) is not int or not 0 < allocated_ms <= limits['wall_seconds'] * 1000:
            raise ValueError('worker_clang_fallback_evidence_invalid')
    if header_provenance:fields|={'header_tool_receipt','header_tool_receipt_sha256'}
    if (not isinstance(evidence,dict) or set(evidence)!=fields
            or evidence['schema']!=request['schema'].replace('-request.', '-evidence.')
            or evidence['request_sha256']!=_digest(_canonical(request))
            or evidence['analyst_uid']!=1001 or type(evidence['analyst_uid']) is not int
            or type(evidence['duration_ms']) is not int or not 0<=evidence['duration_ms']<=allocated_ms+3000
            or not isinstance(evidence['records'],list) or len(evidence['records'])!=len(request['contexts'])):
        raise ValueError('worker_clang_fallback_evidence_invalid')
    okay,version=_execution(evidence['version'],8000)
    if not okay or version.strip()!=VERSION.encode(): raise ValueError('worker_clang_fallback_tool_version')
    if header_provenance:
        try:tool_raw=base64.b64decode(evidence['header_tool_receipt'],validate=True)
        except (ValueError,TypeError) as error:raise ValueError('worker_clang_fallback_header_tool_invalid') from error
        if _digest(tool_raw)!=evidence['header_tool_receipt_sha256']:
            raise ValueError('worker_clang_fallback_header_tool_invalid')
        validate_clang_header_tool_receipt(tool_raw)
        if (request['header_source_targets']!=primary_request['targets']
                or request['header_generated_files']!=primary_request['generated_files']
                or request['header_tool_manifest_sha256']!=CLANG_HEADER_MANIFEST_SHA256):
            raise ValueError('worker_clang_fallback_header_binding_invalid')
    native_sha=_digest(raw); primary_by_id={row['context_id']:row for row in primary_request['contexts']}
    analyzed=[]; findings=[]; limitations=[]; attempted=[]; headers=[]; duration=evidence['version']['duration_ms']
    for planned,row in zip(request['contexts'],evidence['records']):
        row_fields={'context_id','invocation','dropped_arguments','execution','plist','plist_sha256','error'}
        if header_provenance:row_fields|={'header_trace','header_trace_sha256'}
        if (not isinstance(row,dict) or set(row)!=row_fields
                or row['context_id']!=planned['context_id'] or row['invocation']!=planned['invocation']
                or row['dropped_arguments']!=planned['dropped_arguments']
                or row['error'] is not None and (not isinstance(row['error'],str) or re.fullmatch(r'worker_clang_fallback_[a-z_]+',row['error']) is None)):
            raise ValueError('worker_clang_fallback_record_invalid')
        context=primary_by_id[row['context_id']]
        header=None
        if header_provenance and row['header_trace']:
            trace=_decode_plist(row['header_trace'],row['header_trace_sha256'])
            if len(trace)>CLANG_HEADER_LIMIT:raise ValueError('worker_clang_fallback_header_limit')
            header_locations={'/work/source/'+p:('original',p,sha) for p,sha in primary_request['targets'].items()}
            header_locations.update({'/work/analysis/generated-baseline/'+p:('generated',p,item['sha256'])
                for p,item in primary_request['generated_files'].items()})
            header=validate_clang_header_trace(trace,source=context['analysis_file'],context_id=context['context_id'],
                locations=header_locations,standard=_clang_standard(context))
            header.update(native_execution_verified=False,header_tool_manifest_sha256=CLANG_HEADER_MANIFEST_SHA256,
                header_tool_receipt_sha256=evidence['header_tool_receipt_sha256'])
            headers.append(header)
        elif header_provenance and row['header_trace_sha256'] is not None:
            raise ValueError('worker_clang_fallback_header_missing')
        if row['execution'] is None:
            if row['error'] is None or row['plist'] or row['plist_sha256'] is not None or header: raise ValueError('worker_clang_fallback_missing_execution')
            limitations.append({'context_id':row['context_id'],'rule_id':row['error'],'analyzer':'clang-static-analyzer'}); continue
        success,_=_execution(row['execution'],(limits['case_seconds']+3)*1000); duration+=row['execution']['duration_ms']; attempted.append(row['context_id'])
        if not success or row['error']:
            limitations.append({'context_id':row['context_id'],'rule_id':row['error'] or 'clang_native_execution_incomplete','analyzer':'clang-static-analyzer'}); continue
        if not row['plist'] or row['plist_sha256'] is None:
            limitations.append({'context_id':row['context_id'],'rule_id':'clang_native_output_missing','analyzer':'clang-static-analyzer'}); continue
        try: document=plistlib.loads(_decode_plist(row['plist'],row['plist_sha256']))
        except Exception as exc: raise ValueError('worker_clang_fallback_plist_invalid') from exc
        if not isinstance(document,dict) or not isinstance(document.get('files'),list) or not isinstance(document.get('diagnostics'),list):
            raise ValueError('worker_clang_fallback_plist_invalid')
        locations={'/work/source/'+p:('original',p,sha) for p,sha in context['source_dependencies'].items()}
        locations.update({'/work/analysis/generated-baseline/'+p:('generated',p,sha) for p,sha in context['generated_dependencies'].items()})
        files=document['files']; blocked=False
        for diagnostic in document['diagnostics']:
            if not isinstance(diagnostic,dict) or not isinstance(diagnostic.get('location'),dict): raise ValueError('worker_clang_fallback_diagnostic_invalid')
            location=diagnostic['location']; index=location.get('file')
            if type(index) is not int or not 0<=index<len(files) or files[index] not in locations:
                limitations.append({'context_id':row['context_id'],'rule_id':'clang_diagnostic_location_unbound','analyzer':'clang-static-analyzer','message':str(diagnostic.get('description') or '')[:500]}); blocked=True; continue
            origin,path,sha=locations[files[index]]
            rule=str(diagnostic.get('check_name') or diagnostic.get('type') or 'clang-analyzer')[:200]
            message=str(diagnostic.get('description') or diagnostic.get('type') or '')[:2000]
            line=location.get('line'); column=location.get('col')
            if type(line) is not int or line<1 or type(column) is not int or column<1: raise ValueError('worker_clang_fallback_diagnostic_invalid')
            finding={'rule_id':rule,'path':path,'line':line,'column':column,
                'locations':[{'origin':origin,'path':path,'source_sha256':sha,'line':line,'column':column}],
                'message':message,'severity':'unknown','native_severity':'warning','cwe':None,'inconclusive':False,
                'classification':'review_required_candidate','specialist_review_completed':False,'origin':origin,
                'source_sha256':sha,'context_id':row['context_id'],'native_evidence_sha256':native_sha,'analyzer':'clang-static-analyzer'}
            finding['id']='cpp-clang-context-'+_digest(_canonical({k:v for k,v in finding.items() if k!='native_evidence_sha256'})); findings.append(finding)
        if not blocked:
            analyzed.append(row['context_id'])
            if header is not None:header['native_execution_verified']=True
            if header_provenance and (header is None or not header['normal_pass_completed']):
                limitations.append({'context_id':row['context_id'],'rule_id':'clang_header_observation_incomplete','analyzer':'clang-static-analyzer'})
    if duration>evidence['duration_ms']*limits['parallel']+1000: raise ValueError('worker_clang_fallback_duration_invalid')
    return {'required_contexts':[c['context_id'] for c in request['contexts']],'attempted_contexts':attempted,
        'analyzed_contexts':analyzed,'complete':len(analyzed)==len(request['contexts']),'findings':findings,
        'limitations':limitations,'native_evidence_sha256':native_sha,'static_analysis_executed':bool(attempted),'tool_version':VERSION,
        **({'header_context_evidence':headers,'header_tool_manifest_sha256':CLANG_HEADER_MANIFEST_SHA256} if header_provenance else {}),
        **({'header_completion_policy':'unit-and-header-completion-v1'} if request['schema']=='nico.cpp-clang-fallback-request.v7' else {})}


def merge_static_analysis(primary, fallback):
    if not isinstance(primary,dict) or not isinstance(fallback,dict): raise ValueError('worker_clang_fallback_merge_invalid')
    required=primary['required_contexts']; primary_set=set(primary['analyzed_contexts']); fallback_set=set(fallback['analyzed_contexts'])
    allowed=set(required)-primary_set
    if fallback.get('header_completion_policy')=='unit-and-header-completion-v1':
        headers={row['context_id']:row for row in primary.get('header_context_evidence',[])}
        allowed |= {cid for cid in primary_set if not (
            headers.get(cid,{}).get('normal_pass_completed') is True
            and headers.get(cid,{}).get('physical_token_origin_verified') is True)}
        expected=[cid for cid in required if cid in set(primary['attempted_contexts']) and cid in allowed]
        if fallback['required_contexts']!=expected:raise ValueError('worker_clang_fallback_merge_invalid')
    if not fallback_set <= allowed: raise ValueError('worker_clang_fallback_merge_invalid')
    merged=dict(primary); merged['analyzed_contexts']=[cid for cid in required if cid in primary_set or cid in fallback_set]
    merged['complete']=merged['analyzed_contexts']==required
    merged['findings']=[*primary['findings'],*fallback['findings']]; merged['limitations']=[*primary['limitations'],*fallback['limitations']]
    merged['clang_fallback']={'required_contexts':fallback['required_contexts'],'attempted_contexts':fallback['attempted_contexts'],
        'analyzed_contexts':fallback['analyzed_contexts'],'complete':fallback['complete'],
        'native_evidence_sha256':fallback['native_evidence_sha256'],'tool_version':fallback['tool_version']}
    if 'header_context_evidence' in primary:
        from copy import deepcopy
        original={row['context_id']:row for row in primary['header_context_evidence']}
        observed={row['context_id']:row for row in fallback.get('header_context_evidence',[])}
        selected=[];population=deepcopy(primary['header_population'])
        for cid in required:
            previous=original.get(cid)
            if (cid in primary_set and previous is not None
                    and previous.get('normal_pass_completed') is True
                    and previous.get('physical_token_origin_verified') is True):
                if previous is not None:selected.append(deepcopy(previous))
                continue
            row=observed.get(cid)
            if (cid in fallback_set and row is not None and row['normal_pass_completed']
                    and row['native_execution_verified']):
                value=deepcopy(row);value['primary_observation']=deepcopy(previous)
                selected.append(value)
                for key,members in [('included_contexts','include_observed_files'),('parsed_contexts','parsed_ast_files'),
                                    ('analyzed_contexts','syntax_body_callback_files')]:
                    for path in row[members]:
                        if path in population and cid not in population[path][key]:population[path][key].append(cid)
            elif previous is not None:selected.append(deepcopy(previous))
        complete=len(selected)==len(required) and all(
            cid in primary_set and original.get(cid,{}).get('normal_pass_completed') is True
                and original.get(cid,{}).get('physical_token_origin_verified') is True
            or cid in fallback_set and observed.get(cid,{}).get('normal_pass_completed') is True
                and observed.get(cid,{}).get('native_execution_verified') is True for cid in required)
        merged.update(header_context_evidence=selected,header_context_evidence_complete=complete,
            header_population=population,header_population_complete=complete and all(row['analyzed_contexts'] for row in population.values()),
            header_unvisited_files=sorted(path for path,row in population.items() if not row['included_contexts']))
    merged['model_limits']=[*primary.get('model_limits',[]),
        'Cppcheck-incomplete contexts may receive independent Clang Static Analyzer coverage; primary tool limitations remain disclosed.']
    return merged


def run_clang_fallback():
    import sys
    try:
        raw=sys.stdin.buffer.read(REQUEST_LIMIT+1)
        if len(raw)>REQUEST_LIMIT: raise ValueError('worker_clang_fallback_request_limit')
        if len(sys.argv) > 2 or len(sys.argv) == 2 and (
                not sys.argv[1].isascii() or not sys.argv[1].isdigit()
                or len(sys.argv[1]) > 6 or str(int(sys.argv[1])) != sys.argv[1]):
            raise ValueError('worker_clang_fallback_request_invalid')
        result=collect_clang_fallback(json.loads(raw),
            wall_budget_ms=int(sys.argv[1]) if len(sys.argv) == 2 else None)
    except Exception as exc:
        code=str(exc)
        if re.fullmatch(r'worker_clang_fallback_[a-z_]+',code) is None: code='worker_clang_fallback_unavailable'
        print(json.dumps({'schema':'nico.cpp-clang-fallback-failure.v1','error':code})); sys.exit(1)
    print(_canonical(result).decode())


PROGRAM=('import base64, hashlib, json, os, plistlib, re, stat, subprocess, time, zlib\n'
    'from pathlib import Path\nfrom concurrent.futures import ThreadPoolExecutor\n'
    +f'CLANG={CLANG!r}\nCLANGXX={CLANGXX!r}\nVERSION={VERSION!r}\nLIMITS={LIMITS!r}\nEXTENDED_LIMITS={EXTENDED_LIMITS!r}\nLOW_CONTENTION_LIMITS={LOW_CONTENTION_LIMITS!r}\n'
    +f'STREAM_LIMIT={STREAM_LIMIT}\nREQUEST_LIMIT={REQUEST_LIMIT}\nPLIST_LIMIT={PLIST_LIMIT}\nSTORED_PLIST_LIMIT={STORED_PLIST_LIMIT}\nGENERATED_FILE_LIMIT={GENERATED_FILE_LIMIT}\n'
    +f'HEADER_PLUGIN={HEADER_PLUGIN!r}\nCLANG_HEADER_LIMIT={CLANG_HEADER_LIMIT}\nCLANG_HEADER_MANIFEST_SHA256={CLANG_HEADER_MANIFEST_SHA256!r}\n'
    +f'CLANG_HEADER_SOURCE_SHA256={CLANG_HEADER_SOURCE_SHA256!r}\nCLANG_HEADER_SDK_SHA256={CLANG_HEADER_SDK_SHA256!r}\nCLANG_HEADER_RUNTIME_SHA256={CLANG_HEADER_RUNTIME_SHA256!r}\n'
    +f'_DROP_EXACT={_DROP_EXACT!r}\n_DROP_PREFIX={_DROP_PREFIX!r}\n'
    +'\n'.join(inspect.getsource(f) for f in (_canonical,_digest,_stable_bytes,_verify_input,_run,_regular_bytes,
        _clang_require,_clang_json,validate_clang_header_tool_receipt,
        _fallback_plan,_encode_plist,_request_limits,collect_clang_fallback,run_clang_fallback))
    +'\nrun_clang_fallback()\n')
