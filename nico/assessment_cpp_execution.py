"""Configured compilation and analysis, followed by a separate native-test sandbox."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from nico.assessment_cpp_configuration import (
    commands, compilation_database, database_bytes, instrumentation, native_steps,
    COMPILER_VERSION, MAX_CORPUS_BYTES)

from nico.assessment_worker_container import SETUP_PROGRAM, _command, _read_input

IMPORTS = 'import base64, hashlib, json, os, pathlib, resource, signal, socket, subprocess, sys, time\n'
BUILD_PROGRAM = IMPORTS + SETUP_PROGRAM + r'''
mount = next(line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()
             if line.split()[4] == '/work')
assert {'noexec', 'nosuid', 'nodev'} <= set(mount[5].split(','))
os.chdir(root)
tool_env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TMPDIR': '/work',
            'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
versions = {}
for tool in ('gcc', 'g++', 'cppcheck'):
    option = '--version' if tool == 'cppcheck' else '-dumpfullversion'
    version = subprocess.run([tool, option], capture_output=True, check=True, timeout=5, env=tool_env)
    versions[tool] = version.stdout.decode().strip().removeprefix('Cppcheck ')
assert versions == request['tool_versions']
for index, unit in enumerate(request['database']):
    pathlib.Path('/work/unit-' + str(index) + '.json').write_text(json.dumps([unit], sort_keys=True, separators=(',', ':')))
output_limit = request['output_limit']
resource.setrlimit(resource.RLIMIT_FSIZE, (max(output_limit, 2 * 1024 * 1024),) * 2)
deadline = time.monotonic() + request['timeout_seconds']
steps = []
def read(path):
    if path is None: return b''
    p = pathlib.Path(path)
    if not p.exists(): return b''
    with p.open('rb') as handle: return handle.read(output_limit)
for spec in request['commands']:
    row = {**{key: spec[key] for key in ('id', 'invocation')}, 'attempted': False,
        'exit_code': None, 'timed_out': False, 'output_truncated': False, 'duration_ms': 0,
        'stdout': '', 'stderr': '', 'artifact': ''}
    remaining = deadline - time.monotonic()
    if remaining > 0:
        start = time.monotonic(); row['attempted'] = True
        with open('/work/stdout', 'wb') as stdout, open('/work/stderr', 'wb') as stderr:
            process = subprocess.Popen(spec['invocation'], stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True, env=tool_env)
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                row['timed_out'] = True
            finally:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=5)
        row['exit_code'] = 124 if row['timed_out'] else process.returncode
        row['duration_ms'] = int((time.monotonic() - start) * 1000)
        raw = {'stdout': read('/work/stdout'), 'stderr': read('/work/stderr'), 'artifact': read(spec['artifact'])}
        row['output_truncated'] = any(len(value) >= output_limit for value in raw.values())
        row.update({key: base64.b64encode(value).decode('ascii') for key, value in raw.items()})
    steps.append(row)
binary = pathlib.Path('/work/native-test')
raw_binary = b''
if binary.exists() and binary.is_file() and binary.stat().st_size <= 2 * 1024 * 1024:
    raw_binary = binary.read_bytes()
database = json.dumps(request['database'], sort_keys=True, separators=(',', ':')).encode()
print(json.dumps({'steps': steps, 'tool_versions': versions,
    'compilation_database': base64.b64encode(database).decode('ascii'),
    'binary_sha256': hashlib.sha256(raw_binary).hexdigest() if raw_binary else '',
    'binary': base64.b64encode(raw_binary).decode('ascii')}))
'''

# This helper is replaced by the assessed native executable. There is no
# compiler/analyzer controller or prior evidence in the executable's container.
TEST_PROGRAM = IMPORTS + SETUP_PROGRAM + r'''
mount = next(line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()
             if line.split()[4] == '/work')
assert 'noexec' not in mount[5].split(',') and {'nosuid', 'nodev'} <= set(mount[5].split(','))
path = root / 'native-test'
path.chmod(0o500)
os.chdir(root)
runtime = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
    'TMPDIR': '/work', 'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
runtime.update(request.get('runtime_options', {}))
extra = request.get('argv') or []
assert isinstance(extra, list) and len(extra) <= 8
assert all(isinstance(item, str) and 1 <= len(item) <= 64 for item in extra)
raw_stdin = base64.b64decode(request['stdin'], validate=True) if request.get('stdin') else b''
assert len(raw_stdin) <= 4096
reader, writer = os.pipe()
os.write(writer, raw_stdin)
os.close(writer)
os.dup2(reader, 0)
os.close(reader)
os.execve(str(path), [str(path), *extra], runtime)
'''


def _container(image, program, payload, *, checkpoint, timeout, limit, native_exit=False):
    name = 'nico-assessment-' + uuid4().hex
    mount = '--tmpfs=/work:rw,nosuid,nodev,' + ('exec' if native_exit else 'noexec') + ',size=33554432,mode=1777'
    try:
        _command(['docker', 'create', '--name', name, '--interactive', '--network=none',
            '--read-only', '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--cpus=0.5', '--memory=256m', '--memory-swap=256m', '--pids-limit=32',
            mount, '--log-driver=none',
            '--entrypoint=python3', image, '-I', '-S', '-c', program], checkpoint=checkpoint)
        return _command(['docker', 'start', '--attach', '--interactive', name], checkpoint=checkpoint,
            input_bytes=json.dumps(payload).encode(), timeout=timeout, limit=limit, native_exit=native_exit)
    finally:
        _command(['docker', 'rm', '--force', name], checkpoint=lambda: None)


def run_configured(contract, source: Path, *, checkpoint, timeout_seconds):
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= min(300, contract['limits']['wall_seconds']):
        raise ValueError('worker_execution_budget_invalid')
    deadline = time.monotonic() + timeout_seconds
    metadata = json.loads(_command(['docker', 'image', 'inspect', contract['image_digest']], checkpoint=checkpoint))
    if len(metadata) != 1 or metadata[0].get('Id') != contract['image_digest']:
        raise ValueError('worker_image_identity_mismatch')
    if source.is_symlink() or not source.is_dir() or source.absolute() != source.resolve(strict=True):
        raise ValueError('worker_input_type_invalid')
    paths = set()
    for path in source.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('worker_input_type_invalid')
        if path.is_file(): paths.add(path.relative_to(source).as_posix())
    if paths != set(contract['targets']):
        raise ValueError('worker_input_population_mismatch')
    config = contract['configuration']
    corpus_paths = {case['stdin_target'] for case in config.get('runtime_cases') or []
                    if case['kind'] == 'corpus'}
    encoded, size = {}, 0
    fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path, digest in sorted(contract['targets'].items()):
            checkpoint()
            raw = _read_input(fd, path, 16 * 1024 * 1024 - size)
            size += len(raw)
            if size > 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('worker_input_digest_or_budget_mismatch')
            if path in corpus_paths and len(raw) > MAX_CORPUS_BYTES:
                raise ValueError('worker_runtime_corpus_budget_invalid')
            encoded[path] = {'base64': base64.b64encode(raw).decode('ascii'), 'sha256': digest}
    finally:
        os.close(fd)
    instrument = instrumentation(config)
    payload = {'inputs': encoded, 'database': compilation_database(config), 'commands': commands(config),
        'tool_versions': {'gcc': COMPILER_VERSION, 'g++': COMPILER_VERSION, 'cppcheck': contract['tool_version']},
        'output_limit': max(32, contract['max_receipt_bytes'] // (16 * len(native_steps(config)))),
        'timeout_seconds': max(0.01, deadline - time.monotonic() - 5)}
    if len(json.dumps(payload).encode()) > 24 * 1024 * 1024:
        raise ValueError('worker_input_budget_exceeded')
    raw = _container(contract['image_digest'], BUILD_PROGRAM, payload, checkpoint=checkpoint,
        timeout=max(0.01, deadline-time.monotonic()), limit=contract['max_receipt_bytes'] + 3 * 1024 * 1024)
    result = json.loads(raw)
    if instrument:
        result['instrumentation'] = instrument
    binary = base64.b64decode(result.pop('binary'), validate=True)
    if (len(binary) > 2 * 1024 * 1024 or result.get('tool_versions') != payload['tool_versions']
            or base64.b64decode(result['compilation_database'], validate=True) != database_bytes(config)
            or result['binary_sha256'] != (hashlib.sha256(binary).hexdigest() if binary else '')):
        raise ValueError('worker_build_result_invalid')
    test = {'id': 'test', 'invocation': ['/work/source/native-test'], 'attempted': False, 'exit_code': None,
        'timed_out': False, 'output_truncated': False, 'duration_ms': 0, 'stdout': '', 'stderr': '', 'artifact': ''}
    if binary and time.monotonic() < deadline:
        checkpoint()
        started = time.monotonic()
        observed = _container(contract['image_digest'], TEST_PROGRAM,
            {'inputs': {'native-test': {'base64': base64.b64encode(binary).decode('ascii'), 'sha256': result['binary_sha256']}},
             **({'runtime_options': instrument['runtime_options']} if instrument else {})},
            checkpoint=checkpoint, timeout=max(0.01, deadline-time.monotonic()),
            limit=payload['output_limit'], native_exit=True)
        test.update(attempted=True, exit_code=observed['exit_code'], timed_out=observed['timed_out'],
            output_truncated=observed['output_truncated'], duration_ms=int((time.monotonic()-started)*1000),
            stdout=base64.b64encode(observed['output']).decode('ascii'))
    result['steps'].append(test)
    runtime_env = {'runtime_options': instrument['runtime_options']} if instrument else {}
    for case in config.get('runtime_cases') or []:
        row = {'id': case['id'], 'invocation': ['/work/source/native-test', *case['argv']],
               'attempted': False, 'exit_code': None, 'timed_out': False, 'output_truncated': False,
               'duration_ms': 0, 'stdout': '', 'stderr': '', 'artifact': ''}
        if binary and time.monotonic() < deadline:
            checkpoint()
            stdin_bytes = b''
            if case['stdin_target']:
                stdin_bytes = base64.b64decode(encoded[case['stdin_target']]['base64'], validate=True)
            started = time.monotonic()
            observed = _container(contract['image_digest'], TEST_PROGRAM,
                {'inputs': {'native-test': {'base64': base64.b64encode(binary).decode('ascii'),
                                           'sha256': result['binary_sha256']}},
                 'argv': case['argv'], 'stdin': base64.b64encode(stdin_bytes).decode('ascii'),
                 **runtime_env},
                checkpoint=checkpoint, timeout=max(0.01, deadline - time.monotonic()),
                limit=payload['output_limit'], native_exit=True)
            row.update(attempted=True, exit_code=observed['exit_code'], timed_out=observed['timed_out'],
                       output_truncated=observed['output_truncated'],
                       duration_ms=int((time.monotonic() - started) * 1000),
                       stdout=base64.b64encode(observed['output']).decode('ascii'))
        result['steps'].append(row)
    return {'native': result, 'tool_version': contract['tool_version']}
