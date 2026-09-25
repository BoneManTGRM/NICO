"""Run the owned multi-file CMake control in the declared 2 GiB envelope.

This is qualification tooling, not a production dispatcher or a Bitcoin runner.
The host retains native exits/output; the assessed executable cannot write the
receipt. No user repository, credentials, image publication or network is used.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import time
from uuid import uuid4

FIXTURE = {
    'CMakeLists.txt': '''cmake_minimum_required(VERSION 3.22)
project(nico_owned_control LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(NICO_SANITIZE "Instrument the owned diagnostic control" OFF)
if(NICO_SANITIZE)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie)
  add_link_options(-fsanitize=address,undefined -no-pie)
endif()
add_library(control_sum STATIC sum.cpp)
add_executable(control main.cpp)
target_link_libraries(control PRIVATE control_sum)
enable_testing()
add_test(NAME unit COMMAND control unit)
add_test(NAME integration COMMAND control integration)
add_test(NAME negative COMMAND control negative)
''',
    'sum.hpp': '#pragma once\nint control_sum(int a, int b);\n',
    'sum.cpp': '#include "sum.hpp"\nint control_sum(int a, int b) { return a + b; }\n',
    'main.cpp': '''#include "sum.hpp"
#include <climits>
#include <iostream>
#include <string>
int main(int argc, char** argv) {
    if (argc != 2) return 9;
    const std::string mode(argv[1]);
    if (mode == "negative") return 7;
    if (mode == "diagnostic") {
        volatile int maximum = INT_MAX;
        volatile int one = 1;
        return control_sum(maximum, one);
    }
    if (mode == "unit") return control_sum(19, 23) == 42 ? 0 : 1;
    if (mode == "integration") {
        int value = 0;
        for (int i = 0; i != 10; ++i) value = control_sum(value, i);
        std::cout << value << '\\n';
        return value == 45 ? 0 : 2;
    }
    return 8;
}
''',
}


def _step(identity, argv, *, exit_code=0, marker=''):
    return {'id': identity, 'argv': argv, 'exit_code': exit_code, 'marker': marker}


STEPS = (
    _step('cmake_version', ['cmake', '--version'], marker='cmake version 3.31.6'),
    _step('compiler_version', ['g++', '-dumpfullversion'], marker='14.2.0'),
    _step('cmake_configure', ['cmake', '-S', '/work/source', '-B', '/work/build',
        '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']),
    _step('baseline_build', ['cmake', '--build', '/work/build', '--parallel', '2']),
    _step('unit_tests', ['ctest', '--test-dir', '/work/build', '--no-tests=error',
        '--output-on-failure', '-R', '^unit$'], marker='100% tests passed, 0 tests failed out of 1'),
    _step('integration_tests', ['ctest', '--test-dir', '/work/build', '--no-tests=error',
        '--output-on-failure', '-R', '^integration$'], marker='100% tests passed, 0 tests failed out of 1'),
    _step('negative_test', ['ctest', '--test-dir', '/work/build', '--no-tests=error',
        '--output-on-failure', '-R', '^negative$'], exit_code=8,
        marker='0% tests passed, 1 tests failed out of 1'),
    _step('sanitizer_configure', ['cmake', '-S', '/work/source', '-B', '/work/sanitized',
        '-DCMAKE_BUILD_TYPE=Debug', '-DNICO_SANITIZE=ON']),
    _step('sanitizer_build', ['cmake', '--build', '/work/sanitized', '--parallel', '2']),
    _step('sanitizer_clean', ['ctest', '--test-dir', '/work/sanitized', '--no-tests=error',
        '--output-on-failure', '-R', '^(unit|integration)$'],
        marker='100% tests passed, 0 tests failed out of 2'),
    _step('sanitizer_diagnostic', ['/work/sanitized/control', 'diagnostic'], exit_code=1,
        marker='runtime error: signed integer overflow'),
    _step('memory_probe', ['python3', '-I', '-S', '-c',
        'data=bytearray(335544320)\nfor offset in range(0,len(data),4096): data[offset]=1\nprint(len(data))'],
        marker='335544320'),
)

BOUNDARY_PROGRAM = r'''
import errno, json, os, pathlib, socket
status = dict(line.split(':', 1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
mounts = [line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()]
work = next(row for row in mounts if row[4] == '/work')
root = next(row for row in mounts if row[4] == '/')
def cgroup(name): return pathlib.Path('/sys/fs/cgroup', name).read_text().strip()
blocked = False
probe = socket.socket(); probe.settimeout(1)
try: probe.connect(('192.0.2.1', 443))
except OSError as error: blocked = error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH)
finally: probe.close()
print(json.dumps({'uid':os.getuid(), 'gid':os.getgid(),
 'no_new_privileges':status['NoNewPrivs'].strip() == '1',
 'effective_capabilities':int(status['CapEff'].strip(),16),
 'cpu_max':cgroup('cpu.max'), 'memory_max':cgroup('memory.max'),
 'pids_max':cgroup('pids.max'), 'swap_max':cgroup('memory.swap.max'),
 'work_mount':work[5].split(','), 'root_read_only':'ro' in root[5].split(','),
 'docker_socket_absent':not pathlib.Path('/var/run/docker.sock').exists(),
 'credential_environment_absent':not any(key.startswith(('NICO_', 'GITHUB_', 'ACTIONS_', 'RAILWAY_')) for key in os.environ),
 'external_network_blocked':blocked}))
'''

INPUT_PROGRAM = r'''
import hashlib, json, pathlib, sys
files = json.loads(sys.stdin.buffer.read(65537))
root = pathlib.Path('/work/source'); root.mkdir()
for name, text in files.items():
    if '/' in name or name in ('', '.', '..'): raise ValueError('control_input_path_invalid')
    (root / name).write_text(text, encoding='utf-8')
print(json.dumps({name:hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}, sort_keys=True))
'''


def boundary_valid(value):
    if not isinstance(value, dict):
        return False
    try:
        quota, period = map(int, value['cpu_max'].split())
        mounts = set(value['work_mount'])
        return (type(value['uid']) is int and value['uid'] == 1000
            and type(value['gid']) is int and value['gid'] == 1000
            and value['no_new_privileges'] is True
            and type(value['effective_capabilities']) is int and value['effective_capabilities'] == 0
            and period > 0 and quota == 2 * period
            and value['memory_max'] == '2147483648' and value['pids_max'] == '256'
            and value['swap_max'] == '0' and {'rw', 'nosuid', 'nodev'} <= mounts
            and 'noexec' not in mounts
            and all(value[key] is True for key in ('root_read_only', 'docker_socket_absent',
                'credential_environment_absent', 'external_network_blocked')))
    except (KeyError, TypeError, ValueError):
        return False


def record_step(spec, result, duration_ms):
    raw = result['output']
    matched = (type(result['exit_code']) is int and result['exit_code'] == spec['exit_code']
        and result['timed_out'] is False and result['output_truncated'] is False
        and spec.get('marker', '').encode() in raw)
    return {'id': spec['id'], 'invocation': spec['argv'], 'attempted': True,
        'exit_code': result['exit_code'], 'timed_out': result['timed_out'],
        'output_truncated': result['output_truncated'], 'duration_ms': duration_ms,
        'expected_exit_code': spec['exit_code'], 'matched_expectation': matched,
        'output_base64': base64.b64encode(raw).decode('ascii'),
        'output_sha256': hashlib.sha256(raw).hexdigest(), 'output_bytes': len(raw)}


def control_passed(rows):
    return (len(rows) == len(STEPS) and all(
        row.get('id') == spec['id'] and row.get('matched_expectation') is True
        and row.get('attempted') is True and row.get('timed_out') is False
        and row.get('output_truncated') is False
        and type(row.get('exit_code')) is int and row['exit_code'] == spec['exit_code']
        for row, spec in zip(rows, STEPS)))


def run_control(image, source_sha, *, command=None):
    if (not isinstance(image, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', image)
            or not isinstance(source_sha, str) or not re.fullmatch(r'[a-f0-9]{40}', source_sha)):
        raise ValueError('control_identity_invalid')
    if command is None:
        from nico.assessment_worker_container import _command
        command = _command
    from nico.assessment_worker_capacity_v1 import FULL_PROJECT_PROFILE, docker_resource_args
    name = 'nico-cmake-control-' + uuid4().hex
    start = time.monotonic()
    deadline = start + 180
    receipt = {'schema': 'nico.cpp_full_project_control.v1', 'controller_source_sha': source_sha,
        'controller_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'image_config_digest': image, 'resource_profile': FULL_PROJECT_PROFILE,
        'resource_class': 'full-project-v1', 'controlled_cmake_passed': False,
        'full_project_qualified': False, 'production_qualified': False, 'bitcoin_executed': False,
        'limitations': ['Owned control only; not a large-repository qualification.',
            'No third-party dependency resolution or libFuzzer execution.',
            'No production dispatcher or Comprehensive report integration.',
            'Work tmpfs and compiler share the same 2 GiB memory budget.'],
        'fixture_sha256': {key: hashlib.sha256(text.encode()).hexdigest() for key, text in FIXTURE.items()},
        'steps': [], 'boundary': None, 'memory_peak_bytes': None, 'cleanup_verified': False,
        'error': None, 'failed_stage': None}
    phase = 'image_identity'
    def invoke(argv, *, input_bytes=None, timeout=30):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('control_deadline')
        result = command(argv, checkpoint=lambda: None, timeout=min(timeout, remaining),
            input_bytes=input_bytes, limit=65536, native_exit=True)
        return result
    def require(argv, **kwargs):
        result = invoke(argv, **kwargs)
        if (result['exit_code'] != 0 or result['timed_out'] or result['output_truncated']):
            raise ValueError('control_prerequisite_failed')
        return result['output']
    try:
        meta = json.loads(require(['docker', 'image', 'inspect', image]))
        if len(meta) != 1 or meta[0].get('Id') != image:
            raise ValueError('control_image_mismatch')
        phase = 'container_creation'
        require(['docker', 'create', '--name', name, '--network=none', '--read-only',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            *docker_resource_args(FULL_PROJECT_PROFILE, executable=True), '--log-driver=none',
            '--env=TMPDIR=/work', '--env=ASAN_OPTIONS=detect_leaks=0:halt_on_error=1',
            '--env=UBSAN_OPTIONS=halt_on_error=1', '--entrypoint=sleep', image, '200'])
        phase = 'container_start'
        require(['docker', 'start', name])
        phase = 'isolation_boundary'
        receipt['boundary'] = json.loads(require(['docker', 'exec', name, 'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        if not boundary_valid(receipt['boundary']):
            raise ValueError('control_boundary_failed')
        phase = 'fixture_transfer'
        actual = json.loads(require(['docker', 'exec', '--interactive', name, 'python3', '-I', '-S', '-c', INPUT_PROGRAM],
            input_bytes=json.dumps(FIXTURE).encode()))
        if actual != receipt['fixture_sha256']:
            raise ValueError('control_source_mismatch')
        for spec in STEPS:
            phase = spec['id']
            before = time.monotonic()
            result = invoke(['docker', 'exec', name, *spec['argv']])
            row = record_step(spec, result, int((time.monotonic() - before) * 1000))
            receipt['steps'].append(row)
            if not row['matched_expectation']:
                receipt['failed_stage'] = phase
                break
        phase = 'memory_measurement'
        peak = require(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak']).strip()
        receipt['memory_peak_bytes'] = int(peak)
        if not 335544320 <= receipt['memory_peak_bytes'] <= 2147483648:
            raise ValueError('control_memory_measurement_failed')
        receipt['controlled_cmake_passed'] = control_passed(receipt['steps'])
    except (Exception, KeyboardInterrupt):
        # Never serialize raw provider/controller exceptions into the receipt.
        receipt['error'] = 'control_failed_or_interrupted'
        receipt['failed_stage'] = receipt['failed_stage'] or phase
        receipt['controlled_cmake_passed'] = False
    finally:
        try:
            cleanup = command(['docker', 'rm', '--force', name], checkpoint=lambda: None,
                timeout=10, limit=65536, native_exit=True)
            receipt['cleanup_verified'] = (cleanup['exit_code'] == 0 and not cleanup['timed_out']
                and not cleanup['output_truncated'])
        except Exception:
            receipt['cleanup_verified'] = False
        if not receipt['cleanup_verified']:
            receipt['error'] = receipt['error'] or 'control_cleanup_failed'
            receipt['failed_stage'] = receipt['failed_stage'] or 'cleanup'
        receipt['controlled_cmake_passed'] &= receipt['cleanup_verified']
        receipt['duration_ms'] = int((time.monotonic() - start) * 1000)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    receipt = run_control(args.image, args.source_sha)
    Path('cpp-full-project-control.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({key: receipt[key] for key in ('controlled_cmake_passed', 'memory_peak_bytes',
        'cleanup_verified', 'production_qualified', 'bitcoin_executed', 'error', 'failed_stage')}))
    return 0 if receipt['controlled_cmake_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
