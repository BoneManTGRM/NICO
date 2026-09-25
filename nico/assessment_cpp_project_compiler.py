"""Context-complete syntax and header evidence from private generated snapshots.

The baseline build remains separate. This pass produces no object code, does
not run project binaries, and does not claim Cppcheck or production completion.
Legacy compiler programs and their accepted option vocabulary are unchanged.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import stat
import time
from concurrent.futures import ThreadPoolExecutor

from nico.assessment_cpp_compiler_evidence import _source_path, safe_compile_argv, _regular_bytes, _run
from nico.assessment_cpp_generated_context import _project_option, _stable_bytes
from nico.assessment_cpp_project_snapshot import PROJECT_HEADER_SUFFIXES, PROJECT_GENERATED_MAX_FILE_BYTES

GENERATED_FILE_LIMIT = PROJECT_GENERATED_MAX_FILE_BYTES

LIMITS = {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}
# Opt-in v2 gives the measured 475-context workload bounded headroom. The
# enclosing 1,800-second executor, per-context limit and concurrency do not grow.
EXTENDED_LIMITS = {'wall_seconds': 600, 'case_seconds': 90, 'parallel': 4}
STREAM_LIMIT = 48 * 1024 * 1024
REQUEST_LIMIT = 16 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _compiler_limits(request):
    schemas = {'nico.cpp-project-compiler-request.v1': LIMITS,
               'nico.cpp-project-compiler-request.v2': EXTENDED_LIMITS}
    expected = schemas.get(request.get('schema')) if isinstance(request, dict) else None
    supplied = request.get('limits') if isinstance(request, dict) else None
    if (expected is None or not isinstance(supplied, dict) or supplied != expected
            or any(type(value) is not int for value in supplied.values())):
        raise ValueError('worker_project_compiler_budget_invalid')
    return dict(expected)


def _compiler_evidence_schema(request):
    _compiler_limits(request)
    return ('nico.cpp-project-compiler-evidence.v2'
            if request['schema'] == 'nico.cpp-project-compiler-request.v2'
            else 'nico.cpp-project-compiler-evidence.v1')


def _extra_option(arg):
    """GCC 14 scalar options, not helper/plugin/response-file authorization."""
    if _project_option(arg) or arg in {
            '-ftrapv', '-fno-extended-identifiers', '-fcf-protection=full',
            '-fcf-protection=branch', '-fcf-protection=return', '-fcf-protection=none',
            '-Wbidi-chars=any', '-Wbidi-chars=unpaired',
            '-mavx', '-mavx2', '-msha', '-msse4', '-msse4.1'}:
        return True
    # This option rewrites macro strings, not filesystem access. Only bounded
    # original-source prefixes and a canonical relative replacement are allowed.
    if arg.startswith('-fmacro-prefix-map='):
        pair = arg[len('-fmacro-prefix-map='):].split('=')
        if len(pair) != 2:
            return False
        old, new = pair
        return (old == '/work/source' or _source_path(old)) and (
            new == '.' or (re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]{0,499}', new) is not None
                and all(p not in {'', '.', '..', '.git'} for p in new.split('/'))))
    return False


def _syntax_argv(context, generated_files):
    source = context['file']
    generated = context['origin'] == 'generated'
    analysis_source = '/work/analysis/generated-baseline/' + context['path'] if generated else source
    stem = '/work/analysis/compiler-baseline/u' + str(context['index'])
    original = context['arguments']
    reserved = '__NICO_PROJECT_COMPILER_'
    if (not isinstance(original, list) or any(not isinstance(a, str) or reserved in a for a in original)
            or generated and context['path'] not in generated_files):
        raise ValueError('worker_project_compiler_invocation_invalid')
    placeholder_source = '/work/source/' + reserved + 'SOURCE.cpp'
    normalized, replacements = list(original), {}
    index = 1
    while index < len(normalized):
        arg = normalized[index]
        if arg in {'-o', '-MF', '-MT', '-MQ'}:
            index += 2
            continue
        if arg == source:
            if generated:
                normalized[index] = placeholder_source
                replacements[placeholder_source] = analysis_source
        elif arg in {'-I', '-isystem', '-iquote', '-include', '-imacros'} or arg.startswith('-I'):
            combined = arg.startswith('-I') and arg != '-I'
            at = index if combined else index + 1
            if at >= len(normalized):
                raise ValueError('worker_project_compiler_include_invalid')
            value = arg[2:] if combined else normalized[at]
            if (not isinstance(value, str) or not value.startswith('/')
                    or re.fullmatch(r'[A-Za-z0-9_./+-]+', value) is None
                    or any(p in {'', '.', '..', '.git'} for p in value.split('/')[1:])):
                raise ValueError('worker_project_compiler_include_invalid')
            if value == '/work/build' or value.startswith('/work/build/'):
                relative = value[len('/work/build'):].lstrip('/')
                if arg in {'-include', '-imacros'} and relative not in generated_files:
                    raise ValueError('worker_project_compiler_include_not_captured')
                bound = '/work/analysis/generated-baseline' + ('/' + relative if relative else '')
            elif value == '/work/source' or _source_path(value) or any(
                    value == root or value.startswith(root + '/') for root in
                    ('/usr/include', '/usr/local/include', '/usr/lib/gcc', '/usr/local/lib/gcc')):
                bound = value
            else:
                raise ValueError('worker_project_compiler_include_not_captured')
            marker = '/work/source/' + reserved + 'INCLUDE_' + str(index)
            key = '-I' + marker if combined else marker
            normalized[at] = key
            replacements[key] = '-I' + bound if combined else bound
            index = at
        elif _extra_option(arg):
            marker = '-D' + reserved + 'OPTION_' + str(index)
            normalized[index] = marker
            replacements[marker] = arg
        index += 1
    result = safe_compile_argv(normalized, placeholder_source if generated else source, stem)
    result = [replacements.get(arg, arg) for arg in result]
    # The copy changes the physical path, not __FILE__'s original build identity.
    return [result[0], '-fmacro-prefix-map=/work/analysis/generated-baseline=/work/build',
            *result[1:], '-fsyntax-only'], analysis_source


def project_compiler_request(database, targets, snapshot, *, extended_budget=False):
    """Reconstruct the complete plan; a plan never confers execution coverage."""
    from nico.assessment_cpp_full_project import compilation_contexts
    from nico.assessment_cpp_project_snapshot import validate_project_snapshot
    if type(extended_budget) is not bool:
        raise ValueError('worker_project_compiler_budget_invalid')
    contexts = compilation_contexts(database, targets, '/work/build')
    validate_project_snapshot(snapshot, contexts)
    files = {p: {'sha256': v['sha256'], 'bytes': v['bytes']} for p, v in snapshot['files'].items()}
    plans = []
    for row in contexts['contexts']:
        argv, source = _syntax_argv(row, files)
        plans.append({**row, 'invocation': argv, 'analysis_file': source})
    result = {'schema': ('nico.cpp-project-compiler-request.v2' if extended_budget
                         else 'nico.cpp-project-compiler-request.v1'),
        'database_sha256': contexts['database_sha256'],
        'context_membership_sha256': contexts['context_membership_sha256'],
        'snapshot_population_sha256': snapshot['file_population_sha256'],
        'targets': dict(targets), 'generated_files': files,
        'generated_header_candidates': snapshot['header_candidates'],
        'contexts': plans, 'limits': dict(EXTENDED_LIMITS if extended_budget else LIMITS)}
    if len(_canonical(result)) > REQUEST_LIMIT:
        raise ValueError('worker_project_compiler_request_limit')
    return result


def _dependency_populations(raw, request):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 262144 or b'\0' in raw:
        raise ValueError('worker_project_compiler_dependencies_invalid')
    text = raw.decode('utf-8').replace('\\\n', ' ').strip()
    if not text.startswith('nico_unit:'):
        raise ValueError('worker_project_compiler_dependencies_invalid')
    paths = shlex.split(text[len('nico_unit:'):], comments=False, posix=True)
    if not paths or len(paths) > 20000:
        raise ValueError('worker_project_compiler_dependencies_invalid')
    originals, generated, system = {}, {}, set()
    for literal in paths:
        if (not literal.startswith('/') or literal.startswith('//') or ':' in literal
                or any(ord(c) < 32 for c in literal)):
            raise ValueError('worker_project_compiler_dependencies_invalid')
        path = posixpath.normpath(literal)
        if literal.startswith('/work/source/') and _source_path(path):
            relative = path[len('/work/source/'):]
            if relative not in request['targets']:
                raise ValueError('worker_project_compiler_dependency_unbound')
            originals[relative] = request['targets'][relative]
        elif (literal.startswith('/work/analysis/generated-baseline/')
                and path.startswith('/work/analysis/generated-baseline/')):
            relative = path[len('/work/analysis/generated-baseline/'):]
            if relative not in request['generated_files']:
                raise ValueError('worker_project_compiler_dependency_unbound')
            generated[relative] = request['generated_files'][relative]['sha256']
        elif literal.startswith('/usr/') and path.startswith('/usr/'):
            system.add(path)
        else:
            raise ValueError('worker_project_compiler_mutable_dependency')
    return originals, generated, sorted(system)


def _verify_input(root, relative, digest, size=None, generated=False):
    path = Path(root) / relative
    info = path.lstat()
    maximum = GENERATED_FILE_LIMIT if generated else 16 * 1024 * 1024
    raw = _stable_bytes(root, relative, maximum)
    if (info.st_uid != (1001 if generated else 0) or stat.S_IMODE(info.st_mode) & 0o222
            or (size is not None and len(raw) != size) or _digest(raw) != digest):
        raise ValueError('worker_project_compiler_input_mismatch')


def collect_project_compiler(request):
    """Trusted stdin only, after snapshot/controller validation, inside UID 1001."""
    import resource
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_project_compiler_identity')
    limits = _compiler_limits(request)
    if (not isinstance(request.get('contexts'), list)
            or not 1 <= len(request['contexts']) <= 20000):
        raise ValueError('worker_project_compiler_request_invalid')
    parent = Path('/work/analysis')
    info = parent.lstat()
    if (parent.resolve(strict=True) != parent or info.st_uid != 1001
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('worker_project_compiler_private_directory_invalid')
    directory = parent / 'compiler-baseline'
    directory.mkdir(mode=0o700)
    for path, item in request['generated_files'].items():
        _verify_input('/work/analysis/generated-baseline', path, item['sha256'], item['bytes'], True)
    for index, context in enumerate(request['contexts']):
        argv, source = _syntax_argv(context, request['generated_files'])
        if context['index'] != index or argv != context['invocation'] or source != context['analysis_file']:
            raise ValueError('worker_project_compiler_plan_mismatch')
    # No objects are generated; the cap covers compiler logs and dependency files.
    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
        'HOME': str(directory), 'TMPDIR': str(directory), 'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
    start = time.monotonic()
    deadline = start + limits['wall_seconds']
    def one(context):
        record = {'context_id': context['context_id'], 'invocation': context['invocation'],
            'execution': None, 'dependency_bytes': '', 'dependency_sha256': None,
            'source_dependencies': {}, 'generated_dependencies': {}, 'toolchain_dependencies': [], 'error': None}
        try:
            if time.monotonic() >= deadline:
                raise ValueError('worker_project_compiler_deadline')
            if context['origin'] == 'original':
                _verify_input('/work/source', context['path'], request['targets'][context['path']])
            stem = str(directory / ('u' + str(context['index'])))
            record['execution'] = _run(context['invocation'], stem,
                min(deadline, time.monotonic() + limits['case_seconds']), environment)
            execution = record['execution']
            if execution['exit_code'] != 0 or execution['timed_out'] or execution['output_truncated']:
                return record
            deps = _regular_bytes(stem + '.d', 262144)
            record['dependency_bytes'] = base64.b64encode(deps).decode('ascii')
            record['dependency_sha256'] = _digest(deps)
            originals, generated, system = _dependency_populations(deps, request)
            required = originals if context['origin'] == 'original' else generated
            if context['path'] not in required:
                raise ValueError('worker_project_compiler_source_dependency_missing')
            for path, sha in originals.items():
                _verify_input('/work/source', path, sha)
            for path, sha in generated.items():
                _verify_input('/work/analysis/generated-baseline', path, sha,
                              request['generated_files'][path]['bytes'], True)
            record.update(source_dependencies=originals, generated_dependencies=generated,
                          toolchain_dependencies=system)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            code = str(exc)
            record['error'] = code if re.fullmatch(r'worker_project_compiler_[a-z_]+', code) else 'worker_project_compiler_unavailable'
        return record
    with ThreadPoolExecutor(max_workers=limits['parallel']) as pool:
        records = list(pool.map(one, request['contexts']))
    result = {'schema': _compiler_evidence_schema(request), 'request_sha256': _digest(_canonical(request)),
        'analyst_uid': os.getuid(), 'records': records, 'duration_ms': int((time.monotonic()-start)*1000)}
    if len(_canonical(result)) > STREAM_LIMIT:
        raise ValueError('worker_project_compiler_output_limit')
    return result


def validate_project_compiler(raw, request):
    """Reconstruct actual checked contexts and visited headers from native bytes."""
    from nico.assessment_cpp_full_project import _json
    from nico.assessment_cpp_configuration import decode_stream
    if not isinstance(raw, bytes) or not 0 < len(raw) <= STREAM_LIMIT:
        raise ValueError('worker_project_compiler_output_limit')
    limits = _compiler_limits(request)
    evidence = _json(raw)
    if (not isinstance(evidence, dict) or set(evidence) != {'schema','request_sha256','analyst_uid','records','duration_ms'}
            or evidence['schema'] != _compiler_evidence_schema(request)
            or evidence['request_sha256'] != _digest(_canonical(request))
            or type(evidence['analyst_uid']) is not int or evidence['analyst_uid'] != 1001
            or type(evidence['duration_ms']) is not int or not 0 <= evidence['duration_ms'] <= (limits['wall_seconds'] + 3) * 1000
            or not isinstance(evidence['records'], list) or len(evidence['records']) != len(request['contexts'])):
        raise ValueError('worker_project_compiler_evidence_invalid')
    checked, attempted, original_headers, generated_headers = [], [], {}, {}
    durations = 0
    fields = {'context_id','invocation','execution','dependency_bytes','dependency_sha256',
              'source_dependencies','generated_dependencies','toolchain_dependencies','error'}
    for context, record in zip(request['contexts'], evidence['records']):
        if (not isinstance(record, dict) or set(record) != fields or record['context_id'] != context['context_id']
                or record['invocation'] != context['invocation']
                or record['error'] is not None and (not isinstance(record['error'], str)
                    or re.fullmatch(r'worker_project_compiler_[a-z_]+', record['error']) is None)):
            raise ValueError('worker_project_compiler_record_invalid')
        deps = decode_stream(record['dependency_bytes'])
        execution = record['execution']
        if execution is None:
            if record['error'] is None or deps or record['dependency_sha256'] is not None:
                raise ValueError('worker_project_compiler_missing_execution')
            if record['source_dependencies'] or record['generated_dependencies'] or record['toolchain_dependencies']:
                raise ValueError('worker_project_compiler_unattempted_coverage')
            continue
        if (not isinstance(execution, dict) or set(execution) != {'exit_code','timed_out','output_truncated','duration_ms','output','output_sha256'}
                or type(execution['exit_code']) is not int or not -255 <= execution['exit_code'] <= 255
                or any(type(execution[k]) is not bool for k in ('timed_out','output_truncated'))
                or type(execution['duration_ms']) is not int or not 0 <= execution['duration_ms'] <= 93000
                or _digest(decode_stream(execution['output'])) != execution['output_sha256']):
            raise ValueError('worker_project_compiler_execution_invalid')
        durations += execution['duration_ms']
        attempted.append(context['context_id'])
        if deps:
            if _digest(deps) != record['dependency_sha256']:
                raise ValueError('worker_project_compiler_dependency_digest')
            originals, generated, system = _dependency_populations(deps, request)
            # A collector can retain dependency bytes before a later byte-binding
            # check fails. Only successful records may contribute any coverage.
            if record['error'] is None and (record['source_dependencies'] != originals
                    or record['generated_dependencies'] != generated or record['toolchain_dependencies'] != system):
                raise ValueError('worker_project_compiler_dependency_population')
        if execution['exit_code'] != 0 or execution['timed_out'] or execution['output_truncated'] or record['error']:
            continue
        if not deps:
            raise ValueError('worker_project_compiler_dependency_missing')
        required = originals if context['origin'] == 'original' else generated
        if context['path'] not in required:
            raise ValueError('worker_project_compiler_source_dependency_missing')
        checked.append(context['context_id'])
        for path in originals:
            if path.lower().endswith(PROJECT_HEADER_SUFFIXES):
                original_headers.setdefault(path, []).append(context['context_id'])
        for path in generated:
            if path in request['generated_header_candidates']:
                generated_headers.setdefault(path, []).append(context['context_id'])
    if durations > evidence['duration_ms'] * limits['parallel'] + 1000:
        raise ValueError('worker_project_compiler_duration_invalid')
    required = [r['context_id'] for r in request['contexts']]
    return {'required_contexts': required, 'attempted_contexts': attempted, 'checked_contexts': checked,
        'complete': checked == required,
        'source_header_inclusions': {p: sorted(ids) for p, ids in sorted(original_headers.items())},
        'generated_header_inclusions': {p: sorted(ids) for p, ids in sorted(generated_headers.items())},
        'unvisited_generated_headers': sorted(set(request['generated_header_candidates']) - set(generated_headers)),
        'unvisited_source_headers': sorted(p for p in request['targets'] if p.lower().endswith(PROJECT_HEADER_SUFFIXES)
                                          and p not in original_headers),
        'native_evidence_sha256': _digest(raw), 'static_analysis_executed': False,
        'object_code_generated': False, 'production_qualified': False}


_PROJECT_COMPILER_STATE_TOKEN = object()


class _ValidatedProjectCompilerState:
    """Process-local proof that one exact compiler receipt was fully validated."""
    __slots__ = ('raw', 'request', 'proof', 'records')

    def __init__(self, token, raw, request, proof, records):
        if token is not _PROJECT_COMPILER_STATE_TOKEN:
            raise ValueError('worker_project_compiler_state_invalid')
        self.raw = raw
        self.request = request
        self.proof = proof
        self.records = records


def validated_project_compiler_state(raw, request):
    """Validate once, then retain only trusted process-local parsed state."""
    from nico.assessment_cpp_full_project import _json
    proof = validate_project_compiler(raw, request)
    evidence = _json(raw)
    return _ValidatedProjectCompilerState(
        _PROJECT_COMPILER_STATE_TOKEN, raw, request, proof, evidence['records'])


def reuse_validated_project_compiler(state, raw, request):
    """Reuse only the exact bytes/request objects validated in this process."""
    if (not isinstance(state, _ValidatedProjectCompilerState)
            or state.raw is not raw or state.request is not request):
        raise ValueError('worker_project_compiler_state_mismatch')
    return state.proof, state.records


def run_project_compiler():
    import sys
    try:
        raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
        if len(raw) > REQUEST_LIMIT:
            raise ValueError('worker_project_compiler_request_limit')
        result = collect_project_compiler(json.loads(raw))
    except Exception as exc:
        code = str(exc)
        if re.fullmatch(r'worker_project_compiler_[a-z_]+', code) is None:
            code = 'worker_project_compiler_unavailable'
        print(json.dumps({'schema':'nico.cpp-project-compiler-failure.v1','error':code}))
        sys.exit(1)
    print(_canonical(result).decode())


PROGRAM = ('import base64, hashlib, json, os, posixpath, re, shlex, stat, subprocess, time\n'
    'from pathlib import Path\nfrom concurrent.futures import ThreadPoolExecutor\n'
    + f'LIMITS={LIMITS!r}\nEXTENDED_LIMITS={EXTENDED_LIMITS!r}\nSTREAM_LIMIT={STREAM_LIMIT}\nREQUEST_LIMIT={REQUEST_LIMIT}\n'
    + f'GENERATED_FILE_LIMIT={GENERATED_FILE_LIMIT}\n'
    + '\n'.join(inspect.getsource(f) for f in (_canonical, _digest, _compiler_limits, _compiler_evidence_schema, _source_path, safe_compile_argv,
        _regular_bytes, _run, _project_option, _stable_bytes, _extra_option, _syntax_argv,
        _dependency_populations, _verify_input, collect_project_compiler, run_project_compiler))
    + '\nrun_project_compiler()\n')
