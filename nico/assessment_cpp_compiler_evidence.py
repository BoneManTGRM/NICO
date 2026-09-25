"""Direct, source-bound compiler observations in the existing private analyst UID.

A compilation database is a plan. This pass actually compiles each declared TU,
retains GCC dependency bytes and object hashes, and inspects those objects with
nm. It does not execute target binaries or certify instrumentation of CTest's
separate binaries. Mutable/generated include contexts fail explicitly.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import time


def _source_path(path):
    return (isinstance(path, str) and path.startswith('/work/source/')
        and re.fullmatch(r'[A-Za-z0-9_./+-]+', path) is not None
        and all(p not in {'', '.', '..'} for p in path.split('/')[1:]))


def safe_compile_argv(argv, source, stem):
    """Retain supported semantics; reject any option that can run target helpers.

    Never execute a shell/response file/plugin or silently drop an unknown flag.
    Output/dependency destinations alone are replaced by analyst-owned paths.
    """
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 4096
            or any(not isinstance(a, str) or not a or len(a) > 4096
                   or any(ord(c) < 32 for c in a) for a in argv)
            or argv[0] not in {'/usr/local/bin/gcc', '/usr/local/bin/g++'}
            or not _source_path(source)
            or re.fullmatch(r'/work/analysis/compiler-(baseline|address|undefined)/u[0-9]+', stem) is None
            or argv.count('-c') != 1 or argv.count(source) != 1 or argv.count('-o') != 1):
        raise ValueError('worker_compiler_invocation_invalid')
    result = [argv[0]]
    index = 1
    while index < len(argv):
        arg = argv[index]; index += 1
        if arg in {'-o', '-MF', '-MT', '-MQ'}:
            if index >= len(argv) or argv[index].startswith('-'):
                raise ValueError('worker_compiler_output_invalid')
            index += 1
            continue
        if arg in {'-MD', '-MMD', '-MP'}:
            continue
        if arg in {'-I', '-isystem', '-iquote', '-include', '-imacros'}:
            if index >= len(argv) or not (argv[index] == '/work/source' or _source_path(argv[index])):
                raise ValueError('worker_compiler_mutable_include_context')
            result.extend([arg, argv[index]]); index += 1
            continue
        if arg.startswith('-I'):
            if not (arg[2:] == '/work/source' or _source_path(arg[2:])):
                raise ValueError('worker_compiler_mutable_include_context')
        elif arg.startswith(('-D', '-U')):
            if not re.fullmatch(r'-[DU][A-Za-z_][A-Za-z0-9_]*(?:=.*)?', arg):
                raise ValueError('worker_compiler_define_invalid')
        elif arg == source or arg == '-c':
            pass
        elif arg in {'-g', '-g0', '-g1', '-g2', '-g3', '-ggdb', '-pthread', '-pipe',
                     '-fPIC', '-fPIE', '-fpic', '-fpie', '-fno-pie', '-fno-exceptions',
                     '-fno-rtti', '-fno-omit-frame-pointer', '-fno-strict-aliasing',
                     '-fwrapv', '-fno-sanitize-recover=all', '-fsanitize=address',
                     '-fsanitize=undefined'}:
            pass
        elif re.fullmatch(r'-O(?:0|1|2|3|s|g|z)|-std=(?:gnu\+\+|c\+\+|gnu|c)[0-9]+', arg):
            pass
        elif re.fullmatch(r'-W(?:no-)?[A-Za-z][A-Za-z0-9_-]*(?:=[0-9]+)?', arg):
            pass
        else:
            raise ValueError('worker_compiler_option_unsupported')
        result.append(arg)
    return [*result, '-o', stem + '.o', '-MD', '-MF', stem + '.d', '-MT', 'nico_unit']


def parse_dependencies(raw):
    if (not isinstance(raw, bytes) or not raw or len(raw) > 262144 or b'\0' in raw):
        raise ValueError('worker_compiler_dependencies_invalid')
    text = raw.decode('utf-8').replace('\\\n', ' ').strip()
    if not text.startswith('nico_unit:'):
        raise ValueError('worker_compiler_dependencies_invalid')
    paths = shlex.split(text[len('nico_unit:'):], comments=False, posix=True)
    if (not paths or len(paths) > 20000 or any(not p.startswith('/') or ':' in p
            or any(c in p for c in '\n\r\x00') or '..' in p.split('/') for p in paths)):
        raise ValueError('worker_compiler_dependencies_invalid')
    return list(dict.fromkeys(paths))


def _regular_bytes(path, maximum):
    """No symlinks or special files in any component, including the leaf."""
    parts = Path(path).parts
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise ValueError('worker_compiler_artifact_invalid')
            raw = handle.read(maximum + 1)
        if len(raw) > maximum:
            raise ValueError('worker_compiler_artifact_limit')
        return raw
    finally:
        os.close(fd)


def _run(argv, stem, deadline, environment):
    """Disk and outer cgroup/time limits apply; retain failed native output too."""
    start = time.monotonic()
    with open(stem + '.log', 'xb') as output:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output,
            stderr=subprocess.STDOUT, env=environment, cwd='/work/analysis',
            start_new_session=True, shell=False)
        expired = False
        try:
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            expired = True
        finally:
            import signal
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=2)
    with open(stem + '.log', 'rb') as output:
        raw = output.read(65537)
    return {'exit_code': 124 if expired else process.returncode, 'timed_out': expired,
        'output_truncated': len(raw) > 65536, 'duration_ms': int((time.monotonic() - start) * 1000),
        'output': base64.b64encode(raw[:65536]).decode(),
        'output_sha256': hashlib.sha256(raw[:65536]).hexdigest()}


def collect(request):
    """Only called by the trusted program inside the disposable analyst boundary."""
    import resource
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_compiler_analyst_identity')
    group = request['configuration']
    if group not in {'baseline', 'address', 'undefined'}:
        raise ValueError('worker_compiler_configuration_invalid')
    data = base64.b64decode(request['database'], validate=True)
    rows = json.loads(data)
    targets = request['targets']
    if len(rows) != len(request['units']) or len(rows) > 20000:
        raise ValueError('worker_compiler_population_invalid')
    directory = Path('/work/analysis/compiler-' + group)
    directory.mkdir(mode=0o700)
    (directory / 'compile_commands.json').write_bytes(data)
    # Restrict compiler log/object files, not the serving process or host.
    resource.setrlimit(resource.RLIMIT_FSIZE, (67108864, 67108864))
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
        'HOME': str(directory), 'TMPDIR': str(directory),
        'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
    deadline = time.monotonic() + 60
    result = {'schema': 'nico.cpp-direct-compiler.v1', 'configuration': group,
        'database_sha256': hashlib.sha256(data).hexdigest(), 'analyst_uid': os.getuid(),
        'records': [], 'test_binary_instrumentation_verified': False}
    for index, entry in enumerate(sorted(rows, key=lambda r: r['file'])):
        source = entry['file']; unit = source.removeprefix('/work/source/')
        stem = str(directory / ('u' + str(index)))
        record = {'unit': unit, 'source_sha256': targets.get(unit), 'invocation': None,
            'compiler': None, 'object_sha256': None, 'object_bytes': None,
            'dependency_bytes': '', 'dependency_sha256': None,
            'source_dependencies': {}, 'nm': None, 'error': None}
        result['records'].append(record)
        try:
            if unit != request['units'][index] or not _source_path(source):
                raise ValueError('worker_compiler_population_invalid')
            raw_source = _regular_bytes(source, 16777216)
            if hashlib.sha256(raw_source).hexdigest() != targets[unit]:
                raise ValueError('worker_compiler_source_mismatch')
            argv = entry.get('arguments')
            if argv is None: argv = shlex.split(entry['command'])
            record['invocation'] = safe_compile_argv(argv, source, stem)
            record['compiler'] = _run(record['invocation'], stem, deadline, environment)
            if (record['compiler']['exit_code'] != 0 or record['compiler']['timed_out']
                    or record['compiler']['output_truncated']):
                continue
            obj = _regular_bytes(stem + '.o', 67108864)
            if (len(obj) < 64 or obj[:6] != b'\x7fELF\x02\x01'
                    or obj[16:20] != b'\x01\x00\x3e\x00'):
                raise ValueError('worker_compiler_object_invalid')
            record['object_sha256'] = hashlib.sha256(obj).hexdigest(); record['object_bytes'] = len(obj)
            deps = _regular_bytes(stem + '.d', 262144)
            record['dependency_bytes'] = base64.b64encode(deps).decode()
            record['dependency_sha256'] = hashlib.sha256(deps).hexdigest()
            for path in parse_dependencies(deps):
                if path.startswith('/work/source/'):
                    relative = path[len('/work/source/'):]
                    if relative not in targets or not _source_path(path):
                        raise ValueError('worker_compiler_dependency_unbound')
                    digest = hashlib.sha256(_regular_bytes(path, 16777216)).hexdigest()
                    if digest != targets[relative]:
                        raise ValueError('worker_compiler_dependency_mismatch')
                    record['source_dependencies'][relative] = digest
                elif path.startswith('/work/'):
                    raise ValueError('worker_compiler_mutable_include_context')
            if unit not in record['source_dependencies']:
                raise ValueError('worker_compiler_source_dependency_missing')
            # The objects remain analyst-owned. This inspects, never executes them.
            record['nm'] = _run(['/usr/bin/nm', '--undefined-only', stem + '.o'], stem + '-nm', deadline, environment)
        except (ValueError, OSError, KeyError, TypeError) as error:
            name = str(error)
            record['error'] = name if re.fullmatch(r'worker_compiler_[a-z_]+', name) else 'worker_compiler_evidence_unavailable'
    return result


PROGRAM = ('import base64, hashlib, json, os, re, shlex, stat, subprocess, sys, time\n'
           'from pathlib import Path\n' + '\n'.join(inspect.getsource(f) for f in (
               _source_path, safe_compile_argv, parse_dependencies, _regular_bytes, _run, collect)) +
           "\nrequest = json.loads(sys.stdin.buffer.read(4 * 1024 * 1024 + 1))\n"
           "print(json.dumps(collect(request), sort_keys=True, separators=(',', ':')))\n")


def validate_compiler_evidence(raw, database, contract, group):
    """Reconstruct target/header/object populations; never accept a success flag."""
    from nico.assessment_cpp_full_project import _json, _database
    from nico.assessment_cpp_configuration import decode_stream
    units = contract['configuration']['translation_units']
    _database(database, units, '/work/build' if group == 'baseline' else '/work/' + group,
              None if group == 'baseline' else group)
    evidence = _json(raw)
    fields = {'schema', 'configuration', 'database_sha256', 'analyst_uid', 'records',
              'test_binary_instrumentation_verified'}
    if (not isinstance(evidence, dict) or set(evidence) != fields
            or evidence['schema'] != 'nico.cpp-direct-compiler.v1' or evidence['configuration'] != group
            or evidence['database_sha256'] != hashlib.sha256(database).hexdigest()
            or type(evidence['analyst_uid']) is not int or evidence['analyst_uid'] != 1001
            or evidence['test_binary_instrumentation_verified'] is not False
            or not isinstance(evidence['records'], list) or len(evidence['records']) != len(units)):
        raise ValueError('worker_compiler_evidence_invalid')
    plans = sorted(_json(database), key=lambda row: row['file'])
    completed, attempted, headers, symbol_units = [], [], {}, []
    def execution(row):
        if not isinstance(row, dict) or set(row) != {'exit_code', 'timed_out', 'output_truncated',
                'duration_ms', 'output', 'output_sha256'}:
            raise ValueError('worker_compiler_execution_invalid')
        output = decode_stream(row['output'])
        if (type(row['exit_code']) is not int or not -255 <= row['exit_code'] <= 255
                or type(row['timed_out']) is not bool or type(row['output_truncated']) is not bool
                or type(row['duration_ms']) is not int or not 0 <= row['duration_ms'] <= 65000
                or hashlib.sha256(output).hexdigest() != row['output_sha256']):
            raise ValueError('worker_compiler_execution_invalid')
        return row['exit_code'] == 0 and not row['timed_out'] and not row['output_truncated'], output
    for index, (unit, record, plan) in enumerate(zip(units, evidence['records'], plans)):
        if (not isinstance(record, dict) or set(record) != {'unit', 'source_sha256', 'invocation',
                'compiler', 'object_sha256', 'object_bytes', 'dependency_bytes', 'dependency_sha256',
                'source_dependencies', 'nm', 'error'} or record['unit'] != unit
                or record['source_sha256'] != contract['targets'][unit]
                or record['error'] is not None and (not isinstance(record['error'], str)
                    or re.fullmatch(r'worker_compiler_[a-z_]+', record['error']) is None)):
            raise ValueError('worker_compiler_record_invalid')
        # Scan every nested stream before any error/unattempted short-circuit.
        for candidate in (record['compiler'], record['nm']):
            if candidate is not None:
                execution(candidate)
        decode_stream(record['dependency_bytes'])
        argv = plan.get('arguments')
        if argv is None: argv = shlex.split(plan['command'])
        try:
            expected = safe_compile_argv(argv, plan['file'], '/work/analysis/compiler-' + group + '/u' + str(index))
        except ValueError:
            if record['compiler'] is not None or record['invocation'] is not None or record['error'] is None:
                raise ValueError('worker_compiler_unsupported_execution')
            continue
        if record['compiler'] is None:
            if record['error'] is None: raise ValueError('worker_compiler_execution_missing')
            continue
        if record['invocation'] != expected:
            raise ValueError('worker_compiler_invocation_mismatch')
        okay, _ = execution(record['compiler']); attempted.append(unit)
        if not okay or record['error'] is not None:
            continue
        if (not isinstance(record['object_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', record['object_sha256'])
                or type(record['object_bytes']) is not int or not 64 <= record['object_bytes'] <= 67108864):
            raise ValueError('worker_compiler_object_invalid')
        deps = decode_stream(record['dependency_bytes'])
        if hashlib.sha256(deps).hexdigest() != record['dependency_sha256']:
            raise ValueError('worker_compiler_dependency_mismatch')
        paths = parse_dependencies(deps)
        retained = {p[len('/work/source/'):] for p in paths if p.startswith('/work/source/')}
        if (unit not in retained or not retained <= set(contract['targets'])
                or any(p.startswith('/work/') and not _source_path(p) for p in paths)
                or not isinstance(record['source_dependencies'], dict)
                or record['source_dependencies'] != {p: contract['targets'][p] for p in retained}):
            raise ValueError('worker_compiler_dependency_unbound')
        nm_ok, symbols = execution(record['nm'])
        if not nm_ok: continue
        completed.append(unit)
        for path in retained - set(units):
            headers.setdefault(path, []).append(unit)
        prefix = b'__asan_' if group == 'address' else b'__ubsan_handle_' if group == 'undefined' else None
        if prefix and any(line.split()[-1].startswith(prefix) for line in symbols.splitlines() if line.split()):
            symbol_units.append(unit)
    return {'required_translation_units': units, 'attempted_translation_units': attempted,
        'compiled_translation_units': completed, 'complete': completed == units,
        'header_inclusions': {p: sorted(v) for p, v in sorted(headers.items())},
        'object_instrumentation_observed_units': symbol_units,
        'test_binary_instrumentation_verified': False,
        'native_evidence_sha256': hashlib.sha256(raw).hexdigest()}
