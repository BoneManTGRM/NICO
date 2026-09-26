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

_DROP_EXACT = frozenset({
    '-c', '-MD', '-MMD', '-MP', '-fsyntax-only',
    '-fno-extended-identifiers', '-fstack-reuse=none',
})
_DROP_PREFIX = ('-W',)


def _fallback_plan(context):
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
                           '-fcf-protection=full'}):
            kept.append(arg); continue
        raise ValueError('worker_clang_fallback_option_unsupported')
    stem = '/work/analysis/clang-fallback/u' + str(context['index'])
    return [*kept, '--analyze', '-Xanalyzer', '-analyzer-output=plist',
            '-fno-color-diagnostics', source, '-o', stem + '.plist'], dropped


def _request_limits(request):
    if not isinstance(request, dict) or not isinstance(request.get('schema'), str):
        raise ValueError('worker_clang_fallback_request_invalid')
    versions = {'nico.cpp-clang-fallback-request.v1': LIMITS,
                'nico.cpp-clang-fallback-request.v2': EXTENDED_LIMITS,
                'nico.cpp-clang-fallback-request.v4': LOW_CONTENTION_LIMITS}
    expected = versions.get(request.get('schema'))
    limits = request.get('limits')
    if (expected is None or not isinstance(limits, dict) or limits != expected
            or any(type(value) is not int for value in limits.values())):
        raise ValueError('worker_clang_fallback_request_invalid')
    return dict(expected)


def clang_fallback_request(primary_request, primary_proof, *, extended_budget=False, contention_aware=False):
    if (type(extended_budget) is not bool or type(contention_aware) is not bool
            or (contention_aware and not extended_budget)):
        raise ValueError('worker_clang_fallback_request_invalid')
    if (not isinstance(primary_request, dict)
            or primary_request.get('schema') not in {'nico.cpp-project-static-request.v1', 'nico.cpp-project-static-request.v2'}
            or not isinstance(primary_proof, dict)
            or primary_proof.get('native_evidence_sha256') is None):
        raise ValueError('worker_clang_fallback_primary_invalid')
    required = [row['context_id'] for row in primary_request.get('contexts', [])]
    if primary_proof.get('required_contexts') != required:
        raise ValueError('worker_clang_fallback_population_invalid')
    attempted = set(primary_proof.get('attempted_contexts') or [])
    analyzed = set(primary_proof.get('analyzed_contexts') or [])
    missing = [cid for cid in required if cid in attempted and cid not in analyzed]
    by_id = {row['context_id']: row for row in primary_request['contexts']}
    contexts = []
    for cid in missing:
        row = by_id[cid]; argv, dropped = _fallback_plan(row)
        contexts.append({'context_id': cid, 'index': row['index'], 'analysis_file': row['analysis_file'],
            'invocation': argv, 'dropped_arguments': dropped,
            'source_dependencies': dict(row['source_dependencies']),
            'generated_dependencies': dict(row['generated_dependencies'])})
    result = {'schema': ('nico.cpp-clang-fallback-request.v4' if contention_aware
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


def collect_clang_fallback(request):
    import resource
    limits = _request_limits(request)
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_clang_fallback_identity')
    fields = {'schema','tool_version','primary_request_sha256','cppcheck_evidence_sha256',
              'compiler_evidence_sha256','required_contexts','primary_analyzed_contexts','contexts','limits'}
    if 'compiler_environment_sha256' in request:
        fields.add('compiler_environment_sha256')
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
    start=time.monotonic(); deadline=start+limits['wall_seconds']
    version=_run([CLANG,'-dumpversion'],str(directory/'version'),min(deadline,start+5),environment)
    version_ok=(version['exit_code']==0 and not version['timed_out'] and not version['output_truncated']
                and base64.b64decode(version['output'],validate=True).strip()==VERSION.encode())

    def one(context):
        record={'context_id':context['context_id'],'invocation':context['invocation'],
                'dropped_arguments':context['dropped_arguments'],'execution':None,
                'plist':'','plist_sha256':None,'error':None}
        try:
            if not version_ok: raise ValueError('worker_clang_fallback_tool_version')
            if time.monotonic()>=deadline: raise ValueError('worker_clang_fallback_deadline')
            for path,sha in context['source_dependencies'].items(): _verify_input('/work/source',path,sha)
            for path,sha in context['generated_dependencies'].items(): _verify_input('/work/analysis/generated-baseline',path,sha,None,True)
            stem=str(directory/('u'+str(context['index'])))
            record['execution']=_run(context['invocation'],stem,min(deadline,time.monotonic()+limits['case_seconds']),environment)
            plist_path=Path(stem+'.plist')
            if plist_path.exists():
                raw=_regular_bytes(plist_path,PLIST_LIMIT)
                record['plist'],record['plist_sha256']=_encode_plist(raw)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            code=str(exc); record['error']=code if re.fullmatch(r'worker_clang_fallback_[a-z_]+',code) else 'worker_clang_fallback_unavailable'
        return record
    with ThreadPoolExecutor(max_workers=limits['parallel']) as pool:
        records=list(pool.map(one,request['contexts']))
    result={'schema':request['schema'].replace('-request.', '-evidence.'),'request_sha256':_digest(_canonical(request)),
            'analyst_uid':os.getuid(),'version':version,'records':records,'duration_ms':int((time.monotonic()-start)*1000)}
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


def validate_clang_fallback(raw, request, primary_request):
    from nico.assessment_cpp_full_project import _json
    limits = _request_limits(request)
    if not isinstance(raw,bytes) or not 0<len(raw)<=STREAM_LIMIT: raise ValueError('worker_clang_fallback_output_limit')
    evidence=_json(raw)
    if (not isinstance(evidence,dict) or set(evidence)!={'schema','request_sha256','analyst_uid','version','records','duration_ms'}
            or evidence['schema']!=request['schema'].replace('-request.', '-evidence.')
            or evidence['request_sha256']!=_digest(_canonical(request))
            or evidence['analyst_uid']!=1001 or type(evidence['analyst_uid']) is not int
            or type(evidence['duration_ms']) is not int or not 0<=evidence['duration_ms']<=(limits['wall_seconds']+3)*1000
            or not isinstance(evidence['records'],list) or len(evidence['records'])!=len(request['contexts'])):
        raise ValueError('worker_clang_fallback_evidence_invalid')
    okay,version=_execution(evidence['version'],8000)
    if not okay or version.strip()!=VERSION.encode(): raise ValueError('worker_clang_fallback_tool_version')
    native_sha=_digest(raw); primary_by_id={row['context_id']:row for row in primary_request['contexts']}
    analyzed=[]; findings=[]; limitations=[]; attempted=[]; duration=evidence['version']['duration_ms']
    for planned,row in zip(request['contexts'],evidence['records']):
        if (not isinstance(row,dict) or set(row)!={'context_id','invocation','dropped_arguments','execution','plist','plist_sha256','error'}
                or row['context_id']!=planned['context_id'] or row['invocation']!=planned['invocation']
                or row['dropped_arguments']!=planned['dropped_arguments']
                or row['error'] is not None and (not isinstance(row['error'],str) or re.fullmatch(r'worker_clang_fallback_[a-z_]+',row['error']) is None)):
            raise ValueError('worker_clang_fallback_record_invalid')
        context=primary_by_id[row['context_id']]
        if row['execution'] is None:
            if row['error'] is None or row['plist'] or row['plist_sha256'] is not None: raise ValueError('worker_clang_fallback_missing_execution')
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
        if not blocked: analyzed.append(row['context_id'])
    if duration>evidence['duration_ms']*limits['parallel']+1000: raise ValueError('worker_clang_fallback_duration_invalid')
    return {'required_contexts':[c['context_id'] for c in request['contexts']],'attempted_contexts':attempted,
        'analyzed_contexts':analyzed,'complete':len(analyzed)==len(request['contexts']),'findings':findings,
        'limitations':limitations,'native_evidence_sha256':native_sha,'static_analysis_executed':bool(attempted),'tool_version':VERSION}


def merge_static_analysis(primary, fallback):
    if not isinstance(primary,dict) or not isinstance(fallback,dict): raise ValueError('worker_clang_fallback_merge_invalid')
    required=primary['required_contexts']; primary_set=set(primary['analyzed_contexts']); fallback_set=set(fallback['analyzed_contexts'])
    if not fallback_set <= (set(required)-primary_set): raise ValueError('worker_clang_fallback_merge_invalid')
    merged=dict(primary); merged['analyzed_contexts']=[cid for cid in required if cid in primary_set or cid in fallback_set]
    merged['complete']=merged['analyzed_contexts']==required
    merged['findings']=[*primary['findings'],*fallback['findings']]; merged['limitations']=[*primary['limitations'],*fallback['limitations']]
    merged['clang_fallback']={'required_contexts':fallback['required_contexts'],'attempted_contexts':fallback['attempted_contexts'],
        'analyzed_contexts':fallback['analyzed_contexts'],'complete':fallback['complete'],
        'native_evidence_sha256':fallback['native_evidence_sha256'],'tool_version':fallback['tool_version']}
    merged['model_limits']=[*primary.get('model_limits',[]),
        'Cppcheck-incomplete contexts may receive independent Clang Static Analyzer coverage; primary tool limitations remain disclosed.']
    return merged


def run_clang_fallback():
    import sys
    try:
        raw=sys.stdin.buffer.read(REQUEST_LIMIT+1)
        if len(raw)>REQUEST_LIMIT: raise ValueError('worker_clang_fallback_request_limit')
        result=collect_clang_fallback(json.loads(raw))
    except Exception as exc:
        code=str(exc)
        if re.fullmatch(r'worker_clang_fallback_[a-z_]+',code) is None: code='worker_clang_fallback_unavailable'
        print(json.dumps({'schema':'nico.cpp-clang-fallback-failure.v1','error':code})); sys.exit(1)
    print(_canonical(result).decode())


PROGRAM=('import base64, hashlib, json, os, plistlib, re, stat, subprocess, time, zlib\n'
    'from pathlib import Path\nfrom concurrent.futures import ThreadPoolExecutor\n'
    +f'CLANG={CLANG!r}\nCLANGXX={CLANGXX!r}\nVERSION={VERSION!r}\nLIMITS={LIMITS!r}\nEXTENDED_LIMITS={EXTENDED_LIMITS!r}\nLOW_CONTENTION_LIMITS={LOW_CONTENTION_LIMITS!r}\n'
    +f'STREAM_LIMIT={STREAM_LIMIT}\nREQUEST_LIMIT={REQUEST_LIMIT}\nPLIST_LIMIT={PLIST_LIMIT}\nSTORED_PLIST_LIMIT={STORED_PLIST_LIMIT}\nGENERATED_FILE_LIMIT={GENERATED_FILE_LIMIT}\n'
    +f'_DROP_EXACT={_DROP_EXACT!r}\n_DROP_PREFIX={_DROP_PREFIX!r}\n'
    +'\n'.join(inspect.getsource(f) for f in (_canonical,_digest,_stable_bytes,_verify_input,_run,_regular_bytes,
        _fallback_plan,_encode_plist,_request_limits,collect_clang_fallback,run_clang_fallback))
    +'\nrun_clang_fallback()\n')
