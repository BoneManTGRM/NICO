"""Owned transport/receipt regressions; fake Docker is not native execution proof."""
from copy import deepcopy
from pathlib import Path
import base64
import hashlib
import json

import pytest

from nico.assessment_cpp_full_project import execution_steps, validate_native
from nico.assessment_cpp_full_project_execution import run_full_project, READ_PROGRAM
from nico.assessment_worker_receipts import canonical_bytes, validate_receipt
from scripts.worker_protocol_fixture import identity
from tests.test_assessment_cpp_full_project import FakeDocker, encoded, native, plan, wrap


class BoundedDocker(FakeDocker):
    """Model the real reader and command output bounds, not an unlimited mock."""
    def __call__(self, args, **kwargs):
        result = super().__call__(args, **kwargs)
        if READ_PROGRAM in args:
            read_limit = int(args[-1])
            value = json.loads(result['output'])
            raw = base64.b64decode(value['data'])
            result['output'] = json.dumps({'data': encoded(raw[:read_limit]),
                'truncated': len(raw) > read_limit}).encode()
        output_limit = kwargs['limit']
        if len(result['output']) > output_limit:
            result.update(output=result['output'][:output_limit], output_truncated=True)
        return result


def owned_population(tmp_path, count=512, *, long_options=0):
    p = plan()
    units = ['u%04d.cpp' % i for i in range(count)]
    p['configuration']['translation_units'] = units
    p['targets'] = {name: hashlib.sha256(name.encode()).hexdigest()
                    for name in ['CMakeLists.txt', *units]}
    p['max_receipt_bytes'] = 8 * 1024 * 1024
    for name in p['targets']:
        (tmp_path / name).write_bytes(name.encode())
    n = native(p)
    for row in n['steps']:
        if row['id'].endswith('-configure'):
            data = json.loads(base64.b64decode(row['artifacts']['compilation_database']))
            for command in data:
                command['arguments'].extend(['-DVALUE_' + str(i) + '=' + 'x'*80
                                              for i in range(long_options)])
            row['artifacts']['compilation_database'] = encoded(json.dumps(data).encode())
        if row['id'] == 'static-analysis':
            row['output'] = encoded(''.join('Checking /work/source/' + u + ' ...\n' for u in units).encode())
            row['artifacts']['compilation_database'] = next(
                r['artifacts']['compilation_database'] for r in n['steps'] if r['id'] == 'baseline-configure')
    return p, n


@pytest.mark.parametrize('count', [256, 512, 768])
def test_large_frozen_database_reaches_existing_receipt_without_sampling(tmp_path, count):
    p, n = owned_population(tmp_path, count)
    expected = next(r['artifacts']['compilation_database'] for r in n['steps']
                    if r['id'] == 'baseline-configure')
    fake = BoundedDocker(p, n)
    result = run_full_project(p, tmp_path, checkpoint=lambda: None,
                             timeout_seconds=60, command=fake)['native']
    actual = next(r for r in result['steps'] if r['id'] == 'baseline-configure')
    assert actual['output_truncated'] is False
    assert actual['artifacts']['compilation_database'] == expected
    receipt = wrap(result, p)
    assert len(canonical_bytes(receipt)) <= p['max_receipt_bytes']
    _, record, _ = validate_receipt(identity(p), p, receipt['lease_id'], receipt['worker_id'], receipt)
    assert record['completed'] is True
    assert record['cpp_build_evidence']['compilation_database_translation_units'] == p['configuration']['translation_units']
    assert record['cpp_build_evidence']['full_project_qualified'] is False
    assert record['client_delivery_allowed'] is False
    assert fake.calls[-1][0][:3] == ['docker', 'rm', '--force']


def test_excessive_database_retains_bounded_partial_not_success(tmp_path):
    p, n = owned_population(tmp_path, 512, long_options=32)
    fake = BoundedDocker(p, n)
    result = run_full_project(p, tmp_path, checkpoint=lambda: None,
                             timeout_seconds=60, command=fake)['native']
    configured = next(r for r in result['steps'] if r['id'] == 'baseline-configure')
    assert configured['output_truncated'] is True
    assert configured['artifacts']['compilation_database']
    assert next(r for r in result['steps'] if r['id'] == 'baseline-build')['attempted'] is False
    receipt = wrap(result, p)
    assert len(canonical_bytes(receipt)) <= p['max_receipt_bytes']
    _, record, _ = validate_receipt(identity(p), p, receipt['lease_id'], receipt['worker_id'], receipt)
    assert record['completed'] is False
    assert record['output_truncated'] is True
    assert fake.calls[-1][0][:3] == ['docker', 'rm', '--force']


@pytest.mark.parametrize('problem', ['digest', 'missing-unit', 'duplicate-unit'])
def test_larger_capture_does_not_relax_identity_or_population_checks(tmp_path, problem):
    p, n = owned_population(tmp_path, 256)
    row = next(r for r in n['steps'] if r['id'] == 'baseline-configure')
    db = json.loads(base64.b64decode(row['artifacts']['compilation_database']))
    if problem == 'missing-unit': db.pop()
    elif problem == 'duplicate-unit': db.append(db[0])
    else: db[0]['file'] = '/work/source/unrequested.cpp'
    row['artifacts']['compilation_database'] = encoded(json.dumps(db).encode())
    fake = BoundedDocker(p, n)
    result = run_full_project(p, tmp_path, checkpoint=lambda: None,
                             timeout_seconds=60, command=fake)['native']
    assert validate_native(result, p)['complete'] is False
    assert result['cleanup_verified'] is True


def test_metadata_that_cannot_fit_fails_before_container_creation(tmp_path):
    p, n = owned_population(tmp_path, 256)
    p['max_receipt_bytes'] = 1024
    fake = BoundedDocker(p, n)
    with pytest.raises(ValueError, match='worker_full_project_evidence_budget_invalid'):
        run_full_project(p, tmp_path, checkpoint=lambda: None,
                         timeout_seconds=60, command=fake)
    assert fake.calls == []


def test_compound_controller_output_is_bounded_and_cannot_become_success(tmp_path, monkeypatch):
    from nico.assessment_cpp_full_project import configuration
    from nico import assessment_cpp_native_tests as binding
    p, _ = owned_population(tmp_path, 4)
    p['configuration'] = configuration(units=p['configuration']['translation_units'],
        unit_tests=['unit'], integration_tests=['integration'], compiler_evidence=True,
        native_test_evidence=True)
    p['max_receipt_bytes'] = 2 * 1024 * 1024
    n = native(p)
    # This stands for bounded child outputs aggregated by the external native
    # controller; the host must still enforce the enclosing receipt allowance.
    monkeypatch.setattr(binding, 'run_bound_tests', lambda *args: {
        'error': None, 'observations': 'x' * (3 * 1024 * 1024)})
    class ControllerDocker(BoundedDocker):
        def __call__(self, args, **kwargs):
            if binding.SETUP_PROGRAM in args:
                self.calls.append((args, kwargs))
                return {'output': b'runtime_snapshot_destination_ready\n', 'exit_code': 0,
                        'timed_out': False, 'output_truncated': False}
            if args[:2] == ['docker', 'exec'] and '--interactive' in args:
                for spec, row in zip(execution_steps(self.plan), self.native['steps']):
                    if args[-len(spec['invocation']):] == spec['invocation']:
                        self.calls.append((args, kwargs))
                        raw = base64.b64decode(row['output'])
                        return {'output': raw[:kwargs['limit']], 'exit_code': row['exit_code'],
                                'timed_out': False, 'output_truncated': len(raw) > kwargs['limit']}
            return super().__call__(args, **kwargs)
    fake = ControllerDocker(p, n)
    result = run_full_project(p, tmp_path, checkpoint=lambda: None,
                             timeout_seconds=60, command=fake)['native']
    row = next(s for s in result['steps'] if s['id'] == 'address-native-test-evidence')
    assert row['attempted'] is True
    assert row['output_truncated'] is True
    assert row['output']
    assert next(s for s in result['steps'] if s['id'] == 'undefined-native-test-evidence')['attempted'] is False
    receipt = wrap(result, p)
    assert len(canonical_bytes(receipt)) <= p['max_receipt_bytes']
    _, record, _ = validate_receipt(identity(p), p, receipt['lease_id'], receipt['worker_id'], receipt)
    assert record['cpp_build_evidence']['requested_scope_complete'] is False
    assert result['cleanup_verified'] is True


@pytest.mark.parametrize('receipt_limit,count', [(2*1024*1024, 4), (8*1024*1024, 512),
                                                (8*1024*1024, 4096)])
def test_all_capture_slots_together_fit_the_actual_serialized_receipt(tmp_path, receipt_limit, count):
    from nico.assessment_cpp_full_project_execution import _capture_limits
    p, n = owned_population(tmp_path, count)
    p['max_receipt_bytes'] = receipt_limit
    specs = execution_steps(p)
    empty = deepcopy(n)
    for row in empty['steps']:
        row.update(output='', artifacts={})
    limits = _capture_limits(p, specs, empty)
    for spec, row in zip(specs, n['steps']):
        row['output'] = encoded(b'x' * limits[(spec['id'], 'output')])
        for key in spec['artifacts']:
            row['artifacts'][key] = encoded(b'x' * limits[(spec['id'], key)])
    assert len(canonical_bytes(wrap(n, p))) <= receipt_limit
    assert max(limits.values()) <= 2097152
    assert min(limits.values()) >= 1024


def test_capture_regressions_are_required_before_native_integration():
    import shlex
    path = Path(__file__).resolve().parents[1] / '.github/workflows/cpp-full-project-integration.yml'
    command = next(line.strip() for line in path.read_text().splitlines()
                   if 'python -m pytest -q tests/test_cpp_fixture_tree.py' in line)
    assert 'tests/test_cpp_full_project_capture_budget.py' in shlex.split(command)
