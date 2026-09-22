"""Owned sanitizer receipt contracts; synthetic records are not native proof."""
import base64
import hashlib
import json

import pytest

from nico.assessment_worker_receipts import validate_contract
from test_assessment_cpp_configuration import configured_contract, configured_receipt, validate_configured


def sanitizer_plan(kind='address'):
    plan = configured_contract()
    plan['profile'] = 'cpp-sanitized-v1'
    plan['configuration']['sanitizer'] = kind
    return plan


@pytest.mark.parametrize('kind', ['address', 'undefined'])
def test_typed_sanitizer_contract_is_supported(kind):
    plan = sanitizer_plan(kind)
    assert validate_contract(plan) == plan


@pytest.mark.parametrize('kind', ['address,undefined', 'thread', '-fsanitize=address', ['address'], None])
def test_unsupported_or_executable_instrumentation_is_rejected(kind):
    with pytest.raises(ValueError):
        validate_contract(sanitizer_plan(kind))


def test_original_profile_cannot_silently_request_sanitizer_execution():
    plan = sanitizer_plan()
    plan['profile'] = 'cpp-configured-v1'
    with pytest.raises(ValueError):
        validate_contract(plan)


def sanitizer_receipt(kind='address'):
    from nico.assessment_cpp_configuration import instrumentation
    plan = sanitizer_plan(kind)
    job, receipt = configured_receipt(plan)
    receipt['schema'] = 'nico.worker-native-receipt.v4'
    receipt['native']['instrumentation'] = instrumentation(plan['configuration'])
    return plan, job, receipt


@pytest.mark.parametrize('kind', ['address', 'undefined'])
def test_clean_sanitized_receipt_retains_instrumentation_and_source_proof(kind):
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    plan, _, receipt = sanitizer_receipt(kind)
    record = validate_configured(plan, receipt)
    assert record['completed']
    build = record['cpp_build_evidence']
    assert build['sanitizers_executed'] is True
    assert build['sanitizer']['kind'] == kind
    assert build['sanitizer']['outcome'] == 'clean'
    assert not build['sanitizer']['independently_verified_finding']
    assert record['cppcheck_source_coverage']['header_context_verified']
    assert all('-fsanitize=' + kind in row['invocation'] for row in receipt['native']['steps']
               if row['id'].startswith('compile-') or row['id'] == 'link')
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256='f' * 64)
    projected = compact_scanner_records({'scan_id': record['scan_id'], 'scanner_results': [record]},
                                       commit_sha=record['commit_sha'])
    assert projected[0]['cpp_build_evidence'] == build


@pytest.mark.parametrize('kind,output,exit_code', [
    ('address', '==5==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x1234\n', 86),
    ('undefined', 'value.cpp:3:20: runtime error: signed integer overflow\n', 87),
])
def test_reported_diagnostic_is_retained_without_fabricating_a_verified_finding(kind, output, exit_code):
    plan, _, receipt = sanitizer_receipt(kind)
    receipt['native']['steps'][-1].update(exit_code=exit_code,
        stdout=base64.b64encode(output.encode()).decode())
    record = validate_configured(plan, receipt)
    assert record['status'] == 'failed' and not record['completed']
    build = record['cpp_build_evidence']
    assert build['build_completed']
    assert build['sanitizers_executed'] is None
    assert build['native_test']['executed'] is None
    assert build['sanitizer']['outcome'] == 'diagnostic_reported'
    assert build['sanitizer']['diagnostic_origin'] == 'untrusted_native_program_output'
    assert not build['sanitizer']['independently_verified_finding']
    assert record['findings'] == []


@pytest.mark.parametrize('failure,expected', [
    ('startup', 'execution_failed'), ('timeout', 'timed_out'), ('truncated', 'output_truncated'),
    ('unattempted', 'not_attempted'), ('contradictory_success', 'execution_failed'),
])
def test_runtime_failure_cannot_become_a_clean_sanitizer_run(failure, expected):
    plan, _, receipt = sanitizer_receipt()
    row = receipt['native']['steps'][-1]
    if failure == 'startup':
        row.update(exit_code=1, stdout=base64.b64encode(b'PermissionError: native-test').decode())
    elif failure == 'timeout': row.update(exit_code=124, timed_out=True)
    elif failure == 'truncated': row['output_truncated'] = True
    elif failure == 'unattempted': row.update(attempted=False, exit_code=None, duration_ms=0)
    else: row['stdout'] = base64.b64encode(b'ERROR: AddressSanitizer: heap-buffer-overflow\n').decode()
    record = validate_configured(plan, receipt)
    assert not record['completed']
    assert record['cpp_build_evidence']['sanitizer']['outcome'] == expected
    assert record['cpp_build_evidence']['native_test']['passed'] == 0


@pytest.mark.parametrize('change', ['runtime_option', 'compile_option', 'kind', 'missing_proof', 'schema'])
def test_sanitizer_configuration_substitution_is_rejected(change):
    plan, _, receipt = sanitizer_receipt()
    proof = receipt['native']['instrumentation']
    if change == 'runtime_option': proof['runtime_options']['ASAN_OPTIONS'] = 'halt_on_error=0'
    elif change == 'compile_option': receipt['native']['steps'][0]['invocation'].remove('-fsanitize=address')
    elif change == 'kind': proof['kind'] = 'undefined'
    elif change == 'missing_proof': del receipt['native']['instrumentation']
    else: receipt['schema'] = 'nico.worker-native-receipt.v3'
    with pytest.raises(ValueError): validate_configured(plan, receipt)


def test_consumer_uses_versioned_sanitizer_receipt():
    from dataclasses import asdict
    from nico.assessment_worker_consumer import _receipt
    plan, job, receipt = sanitizer_receipt()
    actual = _receipt({'identity': asdict(job), 'contract': plan,
                      'worker_id': receipt['worker_id'], 'lease_id': receipt['lease_id']},
                     {'native': receipt['native']})
    assert actual['schema'] == 'nico.worker-native-receipt.v4'
    assert validate_configured(plan, actual)['completed']


def test_only_fixed_runtime_options_and_binary_enter_the_separate_sandbox(tmp_path, monkeypatch):
    from nico import assessment_cpp_execution as execution
    from nico.assessment_worker_container import run_isolated_cppcheck
    plan, _, receipt = sanitizer_receipt()
    source = tmp_path / 'source'; source.mkdir()
    for name in plan['targets']:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(name.encode())
    payloads = []
    binary = b'synthetic executable placeholder'
    def boundary(image, program, payload, **kwargs):
        payloads.append(payload)
        if len(payloads) == 1:
            native = receipt['native'].copy()
            native['steps'] = native['steps'][:-1]
            native.pop('instrumentation')
            native['binary'] = base64.b64encode(binary).decode()
            return json.dumps(native).encode()
        return {'exit_code': 0, 'output': b'', 'timed_out': False, 'output_truncated': False}
    monkeypatch.setattr(execution, '_container', boundary)
    monkeypatch.setattr(execution, '_command', lambda *a, **kw: json.dumps([{'Id': plan['image_digest']}]).encode())
    result = run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    assert len(payloads) == 2
    assert set(payloads[1]) == {'inputs', 'runtime_options'}
    assert set(payloads[1]['inputs']) == {'native-test'}
    assert payloads[1]['runtime_options'] == result['native']['instrumentation']['runtime_options']
    assert payloads[1]['inputs']['native-test']['sha256'] == hashlib.sha256(binary).hexdigest()
    assert result['native']['steps'][-1]['exit_code'] == 0
