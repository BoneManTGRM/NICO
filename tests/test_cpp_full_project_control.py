"""The owned CMake probe must not certify production or Bitcoin execution."""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from scripts.qualify_cpp_full_project_control import (
    FIXTURE, STEPS, boundary_valid, control_passed, record_step, run_control,
)


def observed(output=b'', exit_code=0, **changes):
    return {'output': output, 'exit_code': exit_code, 'timed_out': False,
            'output_truncated': False, **changes}


def boundary():
    return {'uid': 1000, 'gid': 1000, 'no_new_privileges': True,
            'effective_capabilities': 0, 'cpu_max': '200000 100000',
            'memory_max': '2147483648', 'pids_max': '256',
            'swap_max': '0', 'work_mount': ['rw', 'nosuid', 'nodev'],
            'root_read_only': True, 'docker_socket_absent': True,
            'credential_environment_absent': True, 'external_network_blocked': True}


def good_rows():
    return [record_step(spec, observed(spec.get('marker', '').encode(),
                        exit_code=spec['exit_code']), 1) for spec in STEPS]


def test_owned_control_is_a_real_multifile_cmake_project():
    assert set(FIXTURE) == {'CMakeLists.txt', 'sum.hpp', 'sum.cpp', 'main.cpp'}
    assert 'add_library' in FIXTURE['CMakeLists.txt']
    assert 'add_executable' in FIXTURE['CMakeLists.txt']
    assert 'enable_testing()' in FIXTURE['CMakeLists.txt']
    assert {'cmake_configure', 'baseline_build', 'unit_tests', 'integration_tests',
            'sanitizer_configure', 'sanitizer_build', 'sanitizer_clean',
            'sanitizer_diagnostic', 'negative_test', 'memory_probe'} <= {s['id'] for s in STEPS}


def test_boundary_must_match_expanded_class():
    assert boundary_valid(boundary())


@pytest.mark.parametrize('key,value', [
    ('uid', 0), ('gid', 0), ('no_new_privileges', False),
    ('effective_capabilities', 1), ('cpu_max', '50000 100000'),
    ('cpu_max', 'max 100000'), ('memory_max', '268435456'),
    ('memory_max', 'max'), ('pids_max', '32'), ('swap_max', 'max'),
    ('work_mount', ['rw', 'noexec', 'nosuid', 'nodev']),
    ('root_read_only', False), ('docker_socket_absent', False),
    ('credential_environment_absent', False), ('external_network_blocked', False),
])
def test_boundary_rejects_wrong_or_unproven_controls(key, value):
    data = boundary(); data[key] = value
    assert not boundary_valid(data)


def test_empty_and_missing_boundary_rejected():
    assert not boundary_valid({})
    assert not boundary_valid(None)


def test_complete_control_requires_every_native_step():
    rows = good_rows()
    assert control_passed(rows)
    assert not control_passed(rows[:-1])
    assert not control_passed([])
    assert not control_passed(rows + [rows[0]])


@pytest.mark.parametrize('changes', [
    {'exit_code': 1}, {'exit_code': None}, {'exit_code': False},
    {'timed_out': True}, {'output_truncated': True},
])
def test_native_failure_cannot_be_success(changes):
    spec = next(row for row in STEPS if row['id'] == 'baseline_build')
    row = record_step(spec, observed(**changes), 3)
    assert row['matched_expectation'] is False


def test_missing_test_output_cannot_certify_a_test():
    spec = next(row for row in STEPS if row['id'] == 'unit_tests')
    assert not record_step(spec, observed(), 1)['matched_expectation']


def test_expected_failure_is_preserved_as_a_native_failure():
    spec = next(row for row in STEPS if row['id'] == 'negative_test')
    row = record_step(spec, observed(spec['marker'].encode(), spec['exit_code']), 2)
    assert row['matched_expectation'] is True
    assert row['exit_code'] != 0
    assert not record_step(spec, observed(), 2)['matched_expectation']


def test_raw_output_is_retained_without_decoding_loss():
    raw = b'\xffnative\x00\n'
    spec = next(row for row in STEPS if row['id'] == 'baseline_build')
    row = record_step(spec, observed(raw), 5)
    assert base64.b64decode(row['output_base64'], validate=True) == raw
    assert row['output_sha256'] == hashlib.sha256(raw).hexdigest()
    assert row['output_bytes'] == len(raw)


@pytest.mark.parametrize('image,revision', [
    ('gcc:latest', 'a' * 40), ('sha256:' + 'a' * 64, 'main'),
    ('--privileged', 'a' * 40), ('sha256:' + 'A' * 64, 'a' * 40),
])
def test_bad_identity_fails_before_any_external_call(image, revision):
    calls = []
    with pytest.raises(ValueError, match='control_identity_invalid'):
        run_control(image, revision, command=lambda *a, **k: calls.append(a))
    assert calls == []


def test_receipt_cannot_activate_production_selector():
    from nico.assessment_worker_capacity_v1 import select_production_profile
    receipt = {'schema': 'nico.cpp_full_project_control.v1',
               'controlled_cmake_passed': True, 'full_project_qualified': False,
               'production_qualified': False, 'bitcoin_executed': False}
    assert select_production_profile(receipt) is None


def fake_command(*, failed_step=None, failed_cleanup=False, broken_boundary=False):
    from scripts.qualify_cpp_full_project_control import BOUNDARY_PROGRAM, INPUT_PROGRAM
    calls = []
    def execute(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[:3] == ['docker', 'image', 'inspect']:
            return observed(json.dumps([{'Id': argv[-1]}]).encode())
        if argv[:3] == ['docker', 'rm', '--force']:
            return observed(exit_code=1 if failed_cleanup else 0)
        if argv[:2] in (['docker', 'create'], ['docker', 'start']):
            return observed(b'container-id\n')
        if argv[-1] == BOUNDARY_PROGRAM:
            value = boundary()
            if broken_boundary: value['uid'] = 0
            return observed(json.dumps(value).encode())
        if argv[-1] == INPUT_PROGRAM:
            source = json.loads(kwargs['input_bytes'])
            return observed(json.dumps({k: hashlib.sha256(v.encode()).hexdigest() for k, v in source.items()}).encode())
        if argv[-1] == '/sys/fs/cgroup/memory.peak':
            return observed(b'536870912\n')
        for spec in STEPS:
            if argv[3:] == spec['argv']:
                return observed(spec['marker'].encode(), spec['exit_code'] if failed_step != spec['id'] else 99)
        raise AssertionError('Unexpected command')
    return calls, execute


def test_complete_mock_lifecycle_retains_limits_and_nonproduction_state():
    calls, command = fake_command()
    receipt = run_control('sha256:' + 'a' * 64, 'b' * 40, command=command)
    assert receipt['controlled_cmake_passed'] is True
    assert receipt['cleanup_verified'] is True
    assert receipt['production_qualified'] is False
    assert receipt['full_project_qualified'] is False
    assert receipt['bitcoin_executed'] is False
    assert receipt['memory_peak_bytes'] == 536870912
    create = next(argv for argv, _ in calls if argv[:2] == ['docker', 'create'])
    assert {'--network=none', '--read-only', '--user=1000:1000', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--cpus=2', '--memory=2g',
            '--memory-swap=2g', '--pids-limit=256'} <= set(create)
    assert not any(arg.startswith(('--volume', '--privileged', '--mount')) for arg in create)
    assert all(kwargs['timeout'] <= 30 and kwargs['limit'] <= 65536 for _, kwargs in calls)
    assert calls[-1][0][:3] == ['docker', 'rm', '--force']


@pytest.mark.parametrize('failure', ['baseline_build', 'unit_tests', 'sanitizer_diagnostic'])
def test_failed_native_step_stops_dependents_but_cleans_up(failure):
    calls, command = fake_command(failed_step=failure)
    receipt = run_control('sha256:' + 'a' * 64, 'b' * 40, command=command)
    assert receipt['controlled_cmake_passed'] is False
    assert receipt['cleanup_verified'] is True
    assert receipt['failed_stage'] == failure
    assert receipt['steps'][-1]['id'] == failure
    assert receipt['steps'][-1]['exit_code'] == 99
    assert calls[-1][0][:3] == ['docker', 'rm', '--force']


def test_cleanup_failure_prevents_qualification():
    _, command = fake_command(failed_cleanup=True)
    receipt = run_control('sha256:' + 'a' * 64, 'b' * 40, command=command)
    assert receipt['controlled_cmake_passed'] is False
    assert receipt['cleanup_verified'] is False


def test_failed_boundary_cannot_execute_owned_project():
    calls, command = fake_command(broken_boundary=True)
    receipt = run_control('sha256:' + 'a' * 64, 'b' * 40, command=command)
    assert receipt['controlled_cmake_passed'] is False
    assert receipt['steps'] == []
    assert receipt['cleanup_verified'] is True


def test_controller_exception_is_redacted_and_cleanup_attempted():
    calls = []
    def command(argv, **kwargs):
        calls.append(argv)
        if argv[:3] == ['docker', 'rm', '--force']: return observed()
        raise RuntimeError('private-exception-detail')
    receipt = run_control('sha256:' + 'a' * 64, 'b' * 40, command=command)
    assert 'private-exception-detail' not in json.dumps(receipt)
    assert not receipt['controlled_cmake_passed']
    assert receipt['cleanup_verified']
