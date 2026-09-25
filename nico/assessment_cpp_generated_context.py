"""Opt-in immutable snapshots of declared generated headers.

Only assessed-code output is copied. No dependency installer, download, project
command, or new privilege is introduced. A captured header is not a Git blob:
its original build path, captured bytes, and compiler visits stay separate from
original-source coverage. Version-1/2 execution programs remain byte-identical.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import tempfile
import time

from nico.assessment_cpp_compiler_evidence import (
    _source_path, _regular_bytes, _run, parse_dependencies,
    safe_compile_argv as _legacy_compile_argv,
)

MAX_GENERATED_FILES = 128
MAX_GENERATED_FILE_BYTES = 65536
MAX_GENERATED_BYTES = 262144
MODE = 'isolated-recompile-v2-generated-context'


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('worker_generated_duplicate_member')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('worker_generated_nonfinite')))


def validate_header_paths(paths):
    if (not isinstance(paths, list) or not 1 <= len(paths) <= MAX_GENERATED_FILES
            or any(not isinstance(p, str) or len(p) > 500
                or re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]*\.(?:h|hh|hpp|hxx|inc)', p) is None
                or any(part in {'', '.', '..', '.git'} for part in p.split('/')) for p in paths)
            or paths != sorted(set(paths))
            or any(p.startswith(other + '/') for p in paths for other in paths if p != other)):
        raise ValueError('worker_generated_header_population_invalid')
    return list(paths)


def build_directory(group):
    if group not in ('baseline', 'address', 'undefined'):
        raise ValueError('worker_generated_configuration_invalid')
    return '/work/build' if group == 'baseline' else '/work/' + group


def valid_build_directory(value, root):
    """Accept canonical CMake subdirectories, never an arbitrary execution cwd.

    Source and include operands still have to be absolute and independently
    validated. Compiler replay always runs in the private analyst directory.
    """
    if not isinstance(value, str) or not isinstance(root, str):
        return False
    if value == root:
        return True
    if not value.startswith(root + '/'):
        return False
    relative = value[len(root) + 1:]
    return (0 < len(relative) <= 500
        and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]*', relative) is not None
        and all(part not in {'', '.', '..', '.git'} for part in relative.split('/')))


def snapshot_directory(group):
    build_directory(group)
    return '/work/analysis/generated-' + group


def _stable_bytes(root, relative, maximum):
    """Read through owned descriptors; reject links, special files and changes."""
    parts = Path(root).parts
    if not Path(root).is_absolute():
        raise ValueError('worker_generated_root_invalid')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in (*parts[1:], *relative.split('/')[:-1]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(relative.split('/')[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as handle:
            before = os.fstat(handle.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not 0 <= before.st_size <= maximum):
                raise ValueError('worker_generated_type_or_size_invalid')
            raw = handle.read(maximum + 1)
            after = os.fstat(handle.fileno())
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink')
        if len(raw) != before.st_size or any(getattr(before, k) != getattr(after, k) for k in keys):
            raise ValueError('worker_generated_input_changed')
        return raw
    finally:
        os.close(fd)


def capture_headers(build_root, destination, paths):
    """Publish one all-or-nothing byte snapshot; never write the build directory.

    A second exact read detects observed concurrent changes. This is a snapshot
    of captured bytes, not a claim that the producer is trusted or was quiescent.
    Compilers/analyzers must use the private copy, never the mutable original.
    """
    paths = validate_header_paths(paths)
    build_root, destination = Path(build_root), Path(destination)
    parent = destination.parent
    info = parent.lstat()
    if (parent.absolute() != parent.resolve(strict=True) or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
            or destination.exists() or destination.is_symlink()):
        raise ValueError('worker_generated_destination_invalid')
    staging = Path(tempfile.mkdtemp(prefix='.generated-', dir=parent))
    files = {}
    try:
        total = 0
        for relative in paths:
            raw = _stable_bytes(build_root, relative, min(MAX_GENERATED_FILE_BYTES, MAX_GENERATED_BYTES - total))
            total += len(raw)
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open('xb') as handle:
                handle.write(raw)
            target.chmod(0o444)
            files[relative] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                               'base64': base64.b64encode(raw).decode('ascii')}
        for relative in paths:
            raw = _stable_bytes(build_root, relative, MAX_GENERATED_FILE_BYTES)
            if raw != base64.b64decode(files[relative]['base64'], validate=True):
                raise ValueError('worker_generated_input_changed')
        for directory in sorted((p for p in staging.rglob('*') if p.is_dir()), reverse=True):
            directory.chmod(0o555)
        staging.chmod(0o555)
        os.rename(staging, destination)
        return files
    finally:
        if staging.exists():
            # Staging is analyst-owned/private and only this routine writes it.
            staging.chmod(0o700)
            for directory in staging.rglob('*'):
                if directory.is_dir(): directory.chmod(0o700)
            shutil.rmtree(staging)


def collect_snapshot(request):
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_generated_analyst_identity')
    if not isinstance(request, dict) or set(request) != {'configuration', 'headers'}:
        raise ValueError('worker_generated_request_invalid')
    group = request['configuration']
    files = capture_headers(Path(build_directory(group)), Path(snapshot_directory(group)), request['headers'])
    return {'schema': 'nico.cpp-generated-context.v1', 'configuration': group,
        'analyst_uid': os.getuid(), 'files': files,
        'captured_bytes': sum(item['bytes'] for item in files.values())}


def validate_snapshot(value, group, paths, *, decoder=None):
    paths = validate_header_paths(paths)
    build_directory(group)
    if (not isinstance(value, dict) or set(value) != {'schema', 'configuration', 'analyst_uid', 'files', 'captured_bytes'}
            or value['schema'] != 'nico.cpp-generated-context.v1' or value['configuration'] != group
            or type(value['analyst_uid']) is not int or value['analyst_uid'] != 1001
            or not isinstance(value['files'], dict) or sorted(value['files']) != paths
            or type(value['captured_bytes']) is not int):
        raise ValueError('worker_generated_snapshot_invalid')
    total = 0
    for item in value['files'].values():
        if (not isinstance(item, dict) or set(item) != {'sha256', 'bytes', 'base64'}
                or not isinstance(item['base64'], str) or len(item['base64']) > 4 * ((MAX_GENERATED_FILE_BYTES + 2) // 3)
                or type(item['bytes']) is not int or not 0 <= item['bytes'] <= MAX_GENERATED_FILE_BYTES
                or not isinstance(item['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is None):
            raise ValueError('worker_generated_snapshot_invalid')
        raw = decoder(item['base64']) if decoder else base64.b64decode(item['base64'], validate=True)
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('worker_generated_snapshot_digest_mismatch')
        total += len(raw)
    if total != value['captured_bytes'] or total > MAX_GENERATED_BYTES:
        raise ValueError('worker_generated_snapshot_size_invalid')
    return value


def _include_context(value, flag, group, headers):
    if (not isinstance(value, str) or not value.startswith('/')
            or re.fullmatch(r'[A-Za-z0-9_./+-]+', value) is None
            or any(p in {'', '.', '..'} for p in value.split('/')[1:])):
        raise ValueError('worker_generated_include_invalid')
    if value == '/work/source' or _source_path(value):
        return value
    # These are inside the pinned read-only image, never target-owned mounts.
    if any(value == root or value.startswith(root + '/') for root in
           ('/usr/include', '/usr/local/include', '/usr/lib/gcc', '/usr/local/lib/gcc')):
        return value
    root = build_directory(group)
    if value == root or value.startswith(root + '/'):
        relative = value[len(root):].lstrip('/')
        file_option = flag in {'-include', '-imacros'}
        allowed = relative in headers if file_option else any(
            not relative or path.startswith(relative + '/') for path in headers)
        if allowed:
            return snapshot_directory(group) + ('/' + relative if relative else '')
    raise ValueError('worker_generated_include_not_captured')


def safe_generated_compile_argv(argv, source, stem, group, headers):
    """Apply the existing compiler allowlist; remap only known include operands.

    Include placeholders let the unchanged v2 allowlist check all other flags.
    They are removed before execution and cannot be supplied by target input.
    No compiler helper/plugin/response option is newly allowed.
    """
    headers = validate_header_paths(headers)
    build_directory(group)
    if (not isinstance(argv, list) or any(not isinstance(v, str) for v in argv)
            or re.fullmatch(r'/work/analysis/compiler-' + re.escape(group) + r'/u[0-9]+', stem) is None):
        raise ValueError('worker_generated_invocation_invalid')
    normalized = list(argv)
    substitutions = {}
    index = 1
    while index < len(normalized):
        flag = normalized[index]
        operand_index, combined = None, False
        if flag in {'-I', '-isystem', '-iquote', '-include', '-imacros'}:
            if index + 1 >= len(normalized):
                raise ValueError('worker_generated_include_invalid')
            operand_index = index + 1
            value = normalized[operand_index]
        elif flag.startswith('-I'):
            operand_index, combined, value = index, True, flag[2:]
            flag = '-I'
        if operand_index is not None:
            bound = _include_context(value, flag, group, headers)
            marker = '/work/source/__nico_bound_include_' + str(index)
            if marker in argv or '-I' + marker in argv:
                raise ValueError('worker_generated_reserved_include')
            key = '-I' + marker if combined else marker
            substitutions[key] = '-I' + bound if combined else bound
            normalized[operand_index] = key
            index = operand_index + 1
        else:
            index += 1
    safe = _legacy_compile_argv(normalized, source, stem)
    return [substitutions.get(arg, arg) for arg in safe]


def derive_database(raw, units, group, headers):
    rows = _strict_json(raw)
    if not isinstance(rows, list) or len(rows) != len(units) or not rows:
        raise ValueError('worker_generated_database_invalid')
    if any(not isinstance(row, dict) or not isinstance(row.get('file'), str) for row in rows):
        raise ValueError('worker_generated_database_invalid')
    rows = sorted(rows, key=lambda row: row['file'])
    result = []
    for index, (unit, row) in enumerate(zip(units, rows)):
        if row.get('directory') != build_directory(group) or row['file'] != '/work/source/' + unit:
            raise ValueError('worker_generated_database_binding_invalid')
        args = row.get('arguments')
        if args is None and isinstance(row.get('command'), str): args = shlex.split(row['command'])
        args = safe_generated_compile_argv(args, row['file'], '/work/analysis/compiler-' + group + '/u' + str(index), group, headers)
        result.append({'directory': '/work/analysis', 'file': row['file'], 'arguments': args})
    return json.dumps(result, sort_keys=True, separators=(',', ':')).encode()


def derive_nested_database(raw, units, group, headers):
    rows = _strict_json(raw)
    if not isinstance(rows, list) or len(rows) != len(units) or not rows:
        raise ValueError('worker_generated_database_invalid')
    if any(not isinstance(row, dict) or not isinstance(row.get('file'), str) for row in rows):
        raise ValueError('worker_generated_database_invalid')
    rows = sorted(rows, key=lambda row: row['file'])
    result = []
    for index, (unit, row) in enumerate(zip(units, rows)):
        if not valid_build_directory(row.get('directory'), build_directory(group)) or row['file'] != '/work/source/' + unit:
            raise ValueError('worker_generated_database_binding_invalid')
        args = row.get('arguments')
        if args is None and isinstance(row.get('command'), str): args = shlex.split(row['command'])
        args = safe_generated_compile_argv(args, row['file'], '/work/analysis/compiler-' + group + '/u' + str(index), group, headers)
        result.append({'directory': '/work/analysis', 'file': row['file'], 'arguments': args})
    return json.dumps(result, sort_keys=True, separators=(',', ':')).encode()



def _project_option(arg):
    """Reviewed GCC 14 option forms with no file, plugin or subprocess operand.

    These retain requested compile semantics; accepting a flag is not proof
    that the resulting binary implements or benefits from a mitigation.
    """
    return arg in {
        '-fstack-protector', '-fstack-protector-all', '-fstack-protector-strong',
        '-fstack-protector-explicit', '-fstack-clash-protection',
        '-fvisibility=default', '-fvisibility=hidden', '-fvisibility=internal',
        '-fvisibility=protected', '-fvisibility-inlines-hidden',
        '-fstack-reuse=all', '-fstack-reuse=named_vars', '-fstack-reuse=none',
    } or re.fullmatch(r'-W(?:no-)?error=[A-Za-z][A-Za-z0-9_-]{0,99}', arg) is not None


def derive_project_database(raw, units, group, headers):
    """Preserve reviewed options through the unchanged source/include allowlist.

    Internal placeholders keep each flag in its original position. They cannot
    be provided by source input and are removed before any tool invocation.
    Operand errors still go through the old parser; nothing is silently dropped.
    """
    rows = _strict_json(raw)
    if not isinstance(rows, list) or len(rows) != len(units) or not rows:
        raise ValueError('worker_generated_database_invalid')
    replacements = {}
    prefix = '-D__NICO_PROJECT_OPTION_'
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('worker_generated_database_invalid')
        argv = row.get('arguments')
        if argv is None and isinstance(row.get('command'), str):
            argv = shlex.split(row['command'])
        if (not isinstance(argv, list) or not argv or len(argv) > 4096
                or any(not isinstance(arg, str) or prefix in arg for arg in argv)):
            raise ValueError('worker_generated_project_invocation_invalid')
        args = list(argv)
        for index in range(1, len(args)):
            if _project_option(args[index]):
                marker = prefix + str(row_index) + '_' + str(index) + '=1'
                replacements[marker] = args[index]
                args[index] = marker
        row['arguments'] = args
    normalized = derive_nested_database(
        json.dumps(rows, sort_keys=True, separators=(',', ':')).encode(), units, group, headers)
    result = _strict_json(normalized)
    for row in result:
        row['arguments'] = [replacements.get(arg, arg) for arg in row['arguments']]
    return json.dumps(result, sort_keys=True, separators=(',', ':')).encode()


def configured_database_parser(config):
    """Select an explicit supported dialect; preserve legacy program meanings."""
    mode = config.get('cmake_layout')
    if mode == 'nested-source-v2-gcc-options':
        return derive_project_database
    if mode == 'nested-source-v1':
        return derive_nested_database
    if mode is None:
        return derive_database
    raise ValueError('worker_generated_configuration_invalid')


def collect_compiler(request):
    """Compile captured configuration, retaining original/generated populations."""
    import resource
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_generated_analyst_identity')
    group = request['configuration']
    data = base64.b64decode(request['database'], validate=True)
    context_raw = base64.b64decode(request['generated_context'], validate=True)
    context = validate_snapshot(_strict_json(context_raw), group, request['headers'])
    derived = derive_database(data, request['units'], group, request['headers'])
    rows = _strict_json(derived)
    targets = request['targets']
    generated_root = snapshot_directory(group)
    for path, item in context['files'].items():
        full = Path(generated_root) / path
        info = full.lstat()
        raw = _regular_bytes(str(full), MAX_GENERATED_FILE_BYTES)
        if (info.st_uid != 1001 or stat.S_IMODE(info.st_mode) != 0o444 or info.st_nlink != 1
                or hashlib.sha256(raw).hexdigest() != item['sha256']):
            raise ValueError('worker_generated_frozen_file_mismatch')
    directory = Path('/work/analysis/compiler-' + group)
    directory.mkdir(mode=0o700)
    resource.setrlimit(resource.RLIMIT_FSIZE, (67108864, 67108864))
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
        'HOME': str(directory), 'TMPDIR': str(directory), 'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
    deadline = time.monotonic() + 60
    result = {'schema': 'nico.cpp-direct-compiler.v2', 'configuration': group,
        'database_sha256': hashlib.sha256(data).hexdigest(),
        'analysis_database_sha256': hashlib.sha256(derived).hexdigest(),
        'generated_context_sha256': hashlib.sha256(context_raw).hexdigest(),
        'analyst_uid': os.getuid(), 'records': [], 'test_binary_instrumentation_verified': False}
    for index, row in enumerate(rows):
        unit = row['file'].removeprefix('/work/source/')
        stem = str(directory / ('u' + str(index)))
        record = {'unit': unit, 'source_sha256': targets.get(unit), 'invocation': None,
            'compiler': None, 'object_sha256': None, 'object_bytes': None,
            'dependency_bytes': '', 'dependency_sha256': None, 'source_dependencies': {},
            'generated_dependencies': {}, 'toolchain_dependencies': [], 'nm': None, 'error': None}
        result['records'].append(record)
        try:
            if hashlib.sha256(_regular_bytes(row['file'], 16777216)).hexdigest() != targets[unit]:
                raise ValueError('worker_compiler_source_mismatch')
            record['invocation'] = row['arguments']
            record['compiler'] = _run(row['arguments'], stem, deadline, environment)
            if (record['compiler']['exit_code'] != 0 or record['compiler']['timed_out']
                    or record['compiler']['output_truncated']): continue
            obj = _regular_bytes(stem + '.o', 67108864)
            if len(obj) < 64 or obj[:6] != b'\x7fELF\x02\x01' or obj[16:20] != b'\x01\x00\x3e\x00':
                raise ValueError('worker_compiler_object_invalid')
            record['object_sha256'], record['object_bytes'] = hashlib.sha256(obj).hexdigest(), len(obj)
            deps = _regular_bytes(stem + '.d', 262144)
            record['dependency_bytes'] = base64.b64encode(deps).decode('ascii')
            record['dependency_sha256'] = hashlib.sha256(deps).hexdigest()
            for path in parse_dependencies(deps):
                if _source_path(path):
                    relative = path.removeprefix('/work/source/')
                    if relative not in targets or hashlib.sha256(_regular_bytes(path, 16777216)).hexdigest() != targets[relative]:
                        raise ValueError('worker_compiler_dependency_unbound')
                    record['source_dependencies'][relative] = targets[relative]
                elif path.startswith(generated_root + '/'):
                    relative = path[len(generated_root) + 1:]
                    item = context['files'].get(relative)
                    if not item or hashlib.sha256(_regular_bytes(path, MAX_GENERATED_FILE_BYTES)).hexdigest() != item['sha256']:
                        raise ValueError('worker_generated_dependency_unbound')
                    record['generated_dependencies'][relative] = item['sha256']
                elif path.startswith('/usr/'):
                    record['toolchain_dependencies'].append(path)
                else:
                    raise ValueError('worker_generated_mutable_dependency')
            if unit not in record['source_dependencies']:
                raise ValueError('worker_compiler_source_dependency_missing')
            record['toolchain_dependencies'] = sorted(set(record['toolchain_dependencies']))
            record['nm'] = _run(['/usr/bin/nm', '--undefined-only', stem + '.o'], stem + '-nm', deadline, environment)
        except (ValueError, OSError, KeyError, TypeError) as error:
            code = str(error)
            record['error'] = code if re.fullmatch(r'worker_(?:compiler|generated)_[a-z_]+', code) else 'worker_generated_compiler_unavailable'
    return result


def validate_failure(value, group, phase):
    if (not isinstance(value, dict) or set(value) != {'schema', 'configuration', 'phase', 'error'}
            or value['schema'] != 'nico.cpp-generated-failure.v1'
            or value['configuration'] != group or value['phase'] != phase
            or not isinstance(value['error'], str)
            or re.fullmatch(r'worker_(?:compiler|generated)_[a-z_]+', value['error']) is None):
        raise ValueError('worker_generated_failure_invalid')
    return value


def run_generated_program(phase, collector):
    """Retain a whitelisted failed stage instead of printing filesystem details."""
    import sys
    request = None
    try:
        raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('worker_generated_request_size_invalid')
        request = _strict_json(raw)
        result = collector(request)
    except Exception as error:
        group = request.get('configuration') if isinstance(request, dict) else None
        code = str(error)
        if re.fullmatch(r'worker_(?:compiler|generated)_[a-z_]+', code) is None:
            code = 'worker_generated_capture_unavailable'
        print(json.dumps({'schema': 'nico.cpp-generated-failure.v1', 'configuration': group,
                          'phase': phase, 'error': code}, sort_keys=True, separators=(',', ':')))
        sys.exit(1)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))


def validate_generated_compiler(raw, database, context_raw, contract, group):
    """Reconstruct argv, byte bindings and inclusion populations independently."""
    from nico.assessment_cpp_full_project import _database
    from nico.assessment_cpp_configuration import decode_stream
    units, headers = contract['configuration']['translation_units'], contract['configuration']['generated_headers']
    _database(database, units, build_directory(group), None if group == 'baseline' else group,
              nested=contract['configuration'].get('cmake_layout') in ('nested-source-v1', 'nested-source-v2-gcc-options'))
    context = validate_snapshot(_strict_json(context_raw), group, headers, decoder=decode_stream)
    evidence = _strict_json(raw)
    if isinstance(evidence, dict) and evidence.get('schema') == 'nico.cpp-generated-failure.v1':
        validate_failure(evidence, group, 'compiler')
        return {'required_translation_units': units, 'attempted_translation_units': [],
            'compiled_translation_units': [], 'complete': False, 'header_inclusions': {},
            'generated_header_inclusions': {}, 'object_instrumentation_observed_units': [],
            'test_binary_instrumentation_verified': False,
            'native_evidence_sha256': hashlib.sha256(raw).hexdigest(), 'error': evidence['error']}
    derive = configured_database_parser(contract['configuration'])
    derived = derive(database, units, group, headers)
    plans = _strict_json(derived)
    fields = {'schema', 'configuration', 'database_sha256', 'analysis_database_sha256',
        'generated_context_sha256', 'analyst_uid', 'records', 'test_binary_instrumentation_verified'}
    if (not isinstance(evidence, dict) or set(evidence) != fields
            or evidence['schema'] != 'nico.cpp-direct-compiler.v2' or evidence['configuration'] != group
            or evidence['database_sha256'] != hashlib.sha256(database).hexdigest()
            or evidence['analysis_database_sha256'] != hashlib.sha256(derived).hexdigest()
            or evidence['generated_context_sha256'] != hashlib.sha256(context_raw).hexdigest()
            or type(evidence['analyst_uid']) is not int or evidence['analyst_uid'] != 1001
            or evidence['test_binary_instrumentation_verified'] is not False
            or not isinstance(evidence['records'], list) or len(evidence['records']) != len(units)):
        raise ValueError('worker_generated_compiler_evidence_invalid')
    def execution(row):
        fields = {'exit_code', 'timed_out', 'output_truncated', 'duration_ms', 'output', 'output_sha256'}
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError('worker_generated_execution_invalid')
        output = decode_stream(row['output'])
        if (type(row['exit_code']) is not int or not -255 <= row['exit_code'] <= 255
                or type(row['timed_out']) is not bool or type(row['output_truncated']) is not bool
                or type(row['duration_ms']) is not int or not 0 <= row['duration_ms'] <= 65000
                or hashlib.sha256(output).hexdigest() != row['output_sha256']):
            raise ValueError('worker_generated_execution_invalid')
        return row['exit_code'] == 0 and not row['timed_out'] and not row['output_truncated'], output
    completed, attempted, originals, generated, symbols_found, toolchain = [], [], {}, {}, [], set()
    for unit, record, plan in zip(units, evidence['records'], plans):
        fields = {'unit', 'source_sha256', 'invocation', 'compiler', 'object_sha256', 'object_bytes',
            'dependency_bytes', 'dependency_sha256', 'source_dependencies', 'generated_dependencies',
            'toolchain_dependencies', 'nm', 'error'}
        if (not isinstance(record, dict) or set(record) != fields or record['unit'] != unit
                or record['source_sha256'] != contract['targets'][unit]
                or record['error'] is not None and (not isinstance(record['error'], str)
                    or re.fullmatch(r'worker_(?:compiler|generated)_[a-z_]+', record['error']) is None)):
            raise ValueError('worker_generated_compiler_record_invalid')
        for part in (record['compiler'], record['nm']):
            if part is not None: execution(part)
        deps = decode_stream(record['dependency_bytes'])
        if record['compiler'] is None:
            if record['error'] is None or record['invocation'] is not None:
                raise ValueError('worker_generated_execution_missing')
            continue
        if record['invocation'] != plan['arguments']:
            raise ValueError('worker_generated_invocation_mismatch')
        okay, _ = execution(record['compiler']); attempted.append(unit)
        if not okay or record['error'] is not None: continue
        if (not isinstance(record['object_sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', record['object_sha256']) is None
                or type(record['object_bytes']) is not int or not 64 <= record['object_bytes'] <= 67108864
                or hashlib.sha256(deps).hexdigest() != record['dependency_sha256']):
            raise ValueError('worker_generated_object_or_dependency_invalid')
        source_set, generated_set, image_set = set(), set(), set()
        for path in parse_dependencies(deps):
            if _source_path(path): source_set.add(path.removeprefix('/work/source/'))
            elif path.startswith(snapshot_directory(group) + '/'):
                generated_set.add(path[len(snapshot_directory(group)) + 1:])
            elif path.startswith('/usr/'): image_set.add(path)
            else: raise ValueError('worker_generated_mutable_dependency')
        if (unit not in source_set or not source_set <= set(contract['targets'])
                or not generated_set <= set(context['files'])
                or record['source_dependencies'] != {p: contract['targets'][p] for p in source_set}
                or record['generated_dependencies'] != {p: context['files'][p]['sha256'] for p in generated_set}
                or record['toolchain_dependencies'] != sorted(image_set)):
            raise ValueError('worker_generated_dependency_binding_invalid')
        nm_ok, symbols = execution(record['nm'])
        if not nm_ok: continue
        completed.append(unit); toolchain.update(image_set)
        for path in source_set - set(units): originals.setdefault(path, []).append(unit)
        for path in generated_set: generated.setdefault(path, []).append(unit)
        prefix = b'__asan_' if group == 'address' else b'__ubsan_handle_' if group == 'undefined' else None
        if prefix and any(line.split()[-1].startswith(prefix) for line in symbols.splitlines() if line.split()):
            symbols_found.append(unit)
    return {'required_translation_units': units, 'attempted_translation_units': attempted,
        'compiled_translation_units': completed, 'complete': completed == units,
        'header_inclusions': {p: sorted(v) for p, v in sorted(originals.items())},
        'generated_header_inclusions': {p: sorted(v) for p, v in sorted(generated.items())},
        'captured_generated_header_hashes': {p: item['sha256'] for p, item in context['files'].items()},
        'generated_context_sha256': hashlib.sha256(context_raw).hexdigest(),
        'analysis_database_sha256': hashlib.sha256(derived).hexdigest(),
        'toolchain_header_paths': sorted(toolchain), 'toolchain_image_digest': contract['image_digest'],
        'object_instrumentation_observed_units': symbols_found,
        'test_binary_instrumentation_verified': False, 'native_evidence_sha256': hashlib.sha256(raw).hexdigest()}


_PRELUDE = ('import base64, hashlib, json, os, re, shlex, shutil, stat, subprocess, sys, tempfile, time\n'
    'from pathlib import Path\n'
    f'MAX_GENERATED_FILES={MAX_GENERATED_FILES}\nMAX_GENERATED_FILE_BYTES={MAX_GENERATED_FILE_BYTES}\n'
    f'MAX_GENERATED_BYTES={MAX_GENERATED_BYTES}\n')
SNAPSHOT_PROGRAM = (_PRELUDE + '\n'.join(inspect.getsource(f) for f in (
    _strict_json, validate_header_paths, build_directory, snapshot_directory,
    _stable_bytes, capture_headers, collect_snapshot, run_generated_program))
    + "\nrun_generated_program('snapshot', collect_snapshot)\n")
COMPILER_PROGRAM = (_PRELUDE + inspect.getsource(_legacy_compile_argv).replace(
    'def safe_compile_argv(', 'def _legacy_compile_argv(', 1) + '\n'
    + '\n'.join(inspect.getsource(f) for f in (_source_path, _regular_bytes, _run,
        parse_dependencies, _strict_json, validate_header_paths, build_directory, snapshot_directory,
        validate_snapshot, _include_context, safe_generated_compile_argv, derive_database,
        collect_compiler, run_generated_program))
    + "\nrun_generated_program('compiler', collect_compiler)\n")

# v6 opts in to nested CMake context; the older program stays byte-identical.
NESTED_COMPILER_PROGRAM = COMPILER_PROGRAM.replace(
    inspect.getsource(derive_database),
    inspect.getsource(valid_build_directory) + '\n' + inspect.getsource(derive_nested_database).replace(
        'def derive_nested_database(', 'def derive_database(', 1), 1)


# The opt-in dialect is a separate program. Neither prior embedded program is
# regenerated with different semantics, so old native receipts remain verifiable.
PROJECT_COMPILER_PROGRAM = NESTED_COMPILER_PROGRAM.replace(
    inspect.getsource(derive_nested_database).replace('def derive_nested_database(', 'def derive_database(', 1),
    inspect.getsource(derive_nested_database) + '\n' + inspect.getsource(_project_option) + '\n' +
    inspect.getsource(derive_project_database).replace('def derive_project_database(', 'def derive_database(', 1), 1)
