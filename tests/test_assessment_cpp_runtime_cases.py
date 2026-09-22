"""Owned named unit/integration and bounded corpus receipts; not native proof."""
from copy import deepcopy
import base64
import hashlib
import json

import pytest

from nico.assessment_worker_receipts import validate_contract
from test_assessment_cpp_configuration import configured_contract, configured_receipt, validate_configured

CASES = [
    {'id': 'unit-add', 'kind': 'unit', 'argv': ['--case', 'add'], 'stdin_target': None, 'expected_exit': 0},
    {'id': 'integration-chain', 'kind': 'integration', 'argv': ['--case', 'chain'],
     'stdin_target': None, 'expected_exit': 0},
    {'id': 'corpus-seven', 'kind': 'corpus', 'argv': ['--corpus'],
     'stdin_target': 'corpus/seed-seven.bin', 'expected_exit': 0},
]
SEED = b'\x01\x02\x04'


def runtime_plan():
    plan = configured_contract()
    plan['profile'] = 'cpp-runtime-cases-v1'
    plan['targets']['corpus/seed-seven.bin'] = hashlib.sha256(SEED).hexdigest()
    plan['configuration']['runtime_cases'] = deepcopy(CASES)
    return plan


@pytest.mark.parametrize('kind', ['unit', 'integration', 'corpus'])
def test_typed_runtime_contract_requires_all_declared_kinds(kind):
    plan = runtime_plan()
    plan['configuration']['runtime_cases'] = [case for case in plan['configuration']['runtime_cases']
                                              if case['kind'] == kind]
    if kind != 'corpus':
        del plan['targets']['corpus/seed-seven.bin']
    with pytest.raises(ValueError):
        validate_contract(plan)


def test_typed_runtime_contract_is_supported():
    plan = runtime_plan()
    assert validate_contract(plan) == plan


@pytest.mark.parametrize('expected', [1, 127, 255])
def test_nonzero_expected_exit_cannot_mask_sandbox_startup_failure(expected):
    plan = runtime_plan()
    plan['configuration']['runtime_cases'][-1]['expected_exit'] = expected
    with pytest.raises(ValueError, match='worker_runtime_case_invalid'):
        validate_contract(plan)


def test_original_profiles_cannot_silently_request_runtime_cases():
    plan = runtime_plan()
    plan['profile'] = 'cpp-configured-v1'
    with pytest.raises(ValueError):
        validate_contract(plan)
    plan = runtime_plan()
    plan['profile'] = 'cpp-sanitized-v1'
    plan['configuration']['sanitizer'] = 'address'
    with pytest.raises(ValueError):
        validate_contract(plan)


def test_runtime_profile_cannot_request_sanitizer_instrumentation():
    plan = runtime_plan()
    plan['configuration']['sanitizer'] = 'address'
    with pytest.raises(ValueError):
        validate_contract(plan)


@pytest.mark.parametrize('change', [
    'shell_argv', 'reserved_id', 'duplicate_id', 'unbound_corpus', 'unit_stdin',
    'corpus_on_header', 'empty_argv', 'missing_corpus_target', 'extra_input',
])
def test_unbound_or_executable_runtime_case_is_rejected(change):
    plan = runtime_plan()
    cases = plan['configuration']['runtime_cases']
    if change == 'shell_argv':
        cases[0]['argv'] = ['--case', 'add;reboot']
    elif change == 'reserved_id':
        cases[0]['id'] = 'test'
    elif change == 'duplicate_id':
        cases[1]['id'] = cases[0]['id']
    elif change == 'unbound_corpus':
        cases[2]['stdin_target'] = 'corpus/missing.bin'
    elif change == 'unit_stdin':
        cases[0]['stdin_target'] = 'corpus/seed-seven.bin'
    elif change == 'corpus_on_header':
        cases[2]['stdin_target'] = 'include/value.h'
    elif change == 'empty_argv':
        cases[0]['argv'] = []
    elif change == 'missing_corpus_target':
        del plan['targets']['corpus/seed-seven.bin']
    else:
        plan['targets']['corpus/extra.bin'] = 'a' * 64
    with pytest.raises(ValueError):
        validate_contract(plan)


def runtime_receipt(plan=None):
    from nico.assessment_cpp_configuration import native_steps
    plan = plan or runtime_plan()
    job, receipt = configured_receipt(plan)
    receipt['schema'] = 'nico.worker-native-receipt.v5'
    present = {row['id'] for row in receipt['native']['steps']}
    encoded = lambda value: base64.b64encode(value).decode('ascii')
    for spec in native_steps(plan['configuration']):
        if spec['id'] in present:
            continue
        receipt['native']['steps'].append({
            'id': spec['id'], 'invocation': spec['invocation'], 'attempted': True, 'exit_code': 0,
            'timed_out': False, 'output_truncated': False, 'duration_ms': 1,
            'stdout': encoded(b''), 'stderr': '', 'artifact': ''})
    return plan, job, receipt


def test_clean_runtime_receipt_retains_named_cases_and_corpus_assurance():
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    plan, _, receipt = runtime_receipt()
    record = validate_configured(plan, receipt)
    assert record['completed']
    build = record['cpp_build_evidence']
    runtime = build['runtime_cases']
    assert runtime['required'] == runtime['passed'] == 3
    assert runtime['by_kind'] == {
        'unit': {'required': 1, 'passed': 1},
        'integration': {'required': 1, 'passed': 1},
        'corpus': {'required': 1, 'passed': 1},
    }
    assert runtime['corpus_seeds'] == ['corpus/seed-seven.bin']
    assert runtime['corpus_assurance'] and runtime['corpus_replayed']
    assert runtime['executed'] == 3
    assert build['fuzz_executed'] is False
    assert build['native_test'] == {'required': 1, 'attempted': 1, 'executed': 1, 'passed': 1}
    assert not record['client_delivery_allowed']
    assert all(not row['independently_verified_finding'] for row in runtime['cases'])
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256='f' * 64)
    projected = compact_scanner_records({'scan_id': record['scan_id'], 'scanner_results': [record]},
                                       commit_sha=record['commit_sha'])
    assert projected[0]['cpp_build_evidence'] == build


def test_mismatched_corpus_exit_cannot_complete_or_claim_fuzz():
    plan, _, receipt = runtime_receipt()
    receipt['native']['steps'][-1].update(exit_code=2, stdout=base64.b64encode(b'sum mismatch\n').decode())
    record = validate_configured(plan, receipt)
    assert record['status'] == 'failed' and not record['completed']
    runtime = record['cpp_build_evidence']['runtime_cases']
    assert runtime['passed'] == 2 and runtime['executed'] is None
    assert runtime['corpus_assurance'] is False
    assert runtime['corpus_replayed'] is None
    assert not runtime['cases'][-1]['matched']
    assert runtime['cases'][-1]['original_output_retained']
    assert record['cpp_build_evidence']['native_test']['passed'] == 1
    assert record['cpp_build_evidence']['fuzz_executed'] is False
    assert record['findings'] == [] or all(row.get('rule_id') != 'corpus' for row in record['findings'])


@pytest.mark.parametrize('exit_code', [1, 127])
def test_failed_sandbox_startup_does_not_establish_corpus_replay(exit_code):
    plan, _, receipt = runtime_receipt()
    receipt['native']['steps'][-1].update(exit_code=exit_code, stdout=base64.b64encode(
        b'PermissionError: [Errno 13] Permission denied: /work/source/native-test\n').decode())
    record = validate_configured(plan, receipt)
    runtime = record['cpp_build_evidence']['runtime_cases']
    assert not record['completed']
    assert runtime['passed'] == 2 and runtime['executed'] is None
    assert runtime['corpus_assurance'] is False
    assert runtime['corpus_replayed'] is None
    assert runtime['cases'][-1]['original_output_retained']


def test_oversized_corpus_is_rejected_before_any_native_execution(tmp_path, monkeypatch):
    from nico import assessment_cpp_execution as execution
    from nico.assessment_worker_container import run_isolated_cppcheck
    plan = runtime_plan()
    source = tmp_path / 'source'
    source.mkdir()
    for name in plan['targets']:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = b'x' * 4097 if name == 'corpus/seed-seven.bin' else name.encode()
        path.write_bytes(data)
        plan['targets'][name] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(execution, '_command', lambda *a, **kw: json.dumps([{'Id': plan['image_digest']}]).encode())
    monkeypatch.setattr(execution, '_container', lambda *a, **kw: pytest.fail('oversized corpus reached native execution'))
    with pytest.raises(ValueError, match='worker_runtime_corpus_budget_invalid'):
        run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)


@pytest.mark.parametrize('failure,expected_passed', [
    ('timeout', 2), ('truncated', 2), ('unattempted', 2), ('unit_exit', 2),
])
def test_runtime_failure_or_omission_cannot_become_complete(failure, expected_passed):
    plan, _, receipt = runtime_receipt()
    row = receipt['native']['steps'][-1] if failure != 'unit_exit' else receipt['native']['steps'][-3]
    if failure == 'timeout':
        row.update(exit_code=124, timed_out=True)
    elif failure == 'truncated':
        row['output_truncated'] = True
    elif failure == 'unattempted':
        row.update(attempted=False, exit_code=None, duration_ms=0, stdout='')
    else:
        row.update(exit_code=47)
    record = validate_configured(plan, receipt)
    assert not record['completed']
    runtime = record['cpp_build_evidence']['runtime_cases']
    assert runtime['passed'] == expected_passed
    if failure == 'unattempted':
        assert not runtime['corpus_assurance']
    assert record['cpp_build_evidence']['fuzz_executed'] is False


@pytest.mark.parametrize('change', ['argv', 'missing_step', 'schema', 'profile'])
def test_runtime_configuration_substitution_is_rejected(change):
    plan, _, receipt = runtime_receipt()
    if change == 'argv':
        receipt['native']['steps'][-3]['invocation'] = ['/work/source/native-test', '--case', 'other']
    elif change == 'missing_step':
        receipt['native']['steps'].pop()
    elif change == 'schema':
        receipt['schema'] = 'nico.worker-native-receipt.v4'
    else:
        plan['profile'] = 'cpp-configured-v1'
        del plan['configuration']['runtime_cases']
        del plan['targets']['corpus/seed-seven.bin']
        receipt['schema'] = 'nico.worker-native-receipt.v5'
    with pytest.raises(ValueError):
        validate_configured(plan, receipt)


def test_consumer_uses_versioned_runtime_receipt():
    from dataclasses import asdict
    from nico.assessment_worker_consumer import _receipt
    plan, job, receipt = runtime_receipt()
    actual = _receipt({'identity': asdict(job), 'contract': plan,
                      'worker_id': receipt['worker_id'], 'lease_id': receipt['lease_id']},
                     {'native': receipt['native']})
    assert actual['schema'] == 'nico.worker-native-receipt.v5'
    assert validate_configured(plan, actual)['completed']


def test_named_cases_enter_separate_sandboxes_with_bound_stdin(tmp_path, monkeypatch):
    from nico import assessment_cpp_execution as execution
    from nico.assessment_worker_container import run_isolated_cppcheck
    plan, _, receipt = runtime_receipt()
    source = tmp_path / 'source'
    source.mkdir()
    for name in plan['targets']:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(SEED if name == 'corpus/seed-seven.bin' else name.encode())
    payloads = []
    binary = b'synthetic executable placeholder'

    def boundary(image, program, payload, **kwargs):
        payloads.append(payload)
        if 'commands' in payload:
            native = {key: receipt['native'][key] for key in receipt['native']
                      if key != 'steps'}
            native['steps'] = [row for row in receipt['native']['steps']
                               if row['id'] not in {'test', 'unit-add', 'integration-chain', 'corpus-seven'}]
            native['binary'] = base64.b64encode(binary).decode()
            return json.dumps(native).encode()
        return {'exit_code': 0, 'output': b'owned-case\n', 'timed_out': False, 'output_truncated': False}

    monkeypatch.setattr(execution, '_container', boundary)
    monkeypatch.setattr(execution, '_command', lambda *a, **kw: json.dumps([{'Id': plan['image_digest']}]).encode())
    result = run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    assert len(payloads) == 5
    assert 'argv' not in payloads[1] and 'stdin' not in payloads[1]
    assert set(payloads[1]['inputs']) == {'native-test'}
    assert payloads[2]['argv'] == ['--case', 'add']
    assert payloads[3]['argv'] == ['--case', 'chain']
    assert payloads[4]['argv'] == ['--corpus']
    assert base64.b64decode(payloads[4]['stdin']) == SEED
    assert base64.b64decode(payloads[2]['stdin']) == b''
    assert result['native']['steps'][-1]['id'] == 'corpus-seven'
    assert result['native']['steps'][-1]['exit_code'] == 0
    assert base64.b64decode(result['native']['steps'][-1]['stdout']) == b'owned-case\n'
