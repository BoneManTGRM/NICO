"""Source-bound owned evidence controls; no native or production qualification."""
from copy import deepcopy
import base64
import hashlib
import json

import pytest

from nico.assessment_cpp_runtime_collection import validate_runtime_collection
from nico.assessment_cpp_runtime_execution import execute_runtime_plan
from nico.assessment_cpp_runtime_scope import (
    capture_runtime_interfaces, derive_runtime_plan, retained_runtime_bytes, validate_retained_runtime,
)
from nico.assessment_worker_receipts import canonical_bytes
from tests.test_cpp_completed_sanitizer_failure_collection import CompletedTestFailure, envelope
from tests.test_cpp_contention_scheduling import source_and_scope
from tests.test_cpp_runtime_execution import Observe


def fixture(tmp_path, *, kind='undefined', later_fault=None, message='Failed', transport_timeout=False):
    source, targets, scope = source_and_scope(tmp_path)
    options = {'BUILD_TESTS': 'ON'}
    plan = derive_runtime_plan(source, targets, options, scope)
    delegate = (CompletedTestFailure(kind, later_fault=later_fault, message=message,
                    transport_timeout=transport_timeout) if kind else Observe(later_fault))

    def observe(key, argv, **kwargs):
        row = delegate(key, argv, **kwargs)
        if key == 'runtime-functional-results':
            raw = ('test,status,duration(seconds)\n' + ''.join(
                name + ',Passed,1\n' for name in plan['functional']['selected_tests']) + 'ALL,Passed,4\n').encode()
            row['output'] = envelope(raw)
        elif key == 'runtime-fuzz-corpus-stage':
            row['output'] = canonical_bytes([{'path': '/work/runtime-corpus/connect_block/s'+str(i),
                'sha256': value['sha256'], 'bytes': value['bytes']} for i, value in enumerate(plan['fuzz']['corpus'])])
        elif key.endswith('-resources'):
            row['output'] = canonical_bytes({'memory_current_bytes': 100, 'memory_peak_bytes': 200,
                'memory_events': {'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0},
                'scratch_capacity_bytes': 1000, 'scratch_available_bytes': 100})
        return row

    evidence = execute_runtime_plan(observe, 'owned', plan, options)
    interfaces = capture_runtime_interfaces(source, targets)
    return json.loads(retained_runtime_bytes(interfaces, plan, evidence)), targets, options, scope


def validate(value):
    retained, targets, options, scope = value
    return validate_runtime_collection(canonical_bytes(retained), targets, options, scope)


def output(row, raw):
    row.update(output=base64.b64encode(raw).decode(), output_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('kind', [None, 'address', 'undefined'])
def test_complete_collection_keeps_the_original_target_outcome_and_input_bytes(tmp_path, kind):
    value = fixture(tmp_path, kind=kind)
    before = deepcopy(value)
    decision = validate(value)
    original = validate_retained_runtime(canonical_bytes(value[0]), *value[1:])['summary']
    assert value == before
    assert decision['summary'] == original
    assert decision['schema'] == 'nico.cpp-runtime-collection.v1'
    assert decision['collection_complete'] is True
    assert decision['target_tests_passed'] is (kind is None)
    assert decision['status'] == ('passed' if kind is None else 'complete_with_findings')
    assert decision['production_qualified'] is False and decision['full_project_qualified'] is False
    assert decision['runtime_artifact_sha256'] == hashlib.sha256(canonical_bytes(value[0])).hexdigest()
    if kind:
        assert original['complete'] is False and original['error'] == 'worker_runtime_sanitizer_failed'
        assert next(row for row in original['sanitizers'] if row['kind'] == kind)['passed'] == []


@pytest.mark.parametrize('fault', ['runtime-functional', 'runtime-address-build', 'runtime-fuzz-build',
    'runtime-fuzz-replay-0', 'runtime-fuzz-campaign', 'runtime-reclaim-address'])
def test_infrastructure_and_incomplete_work_cannot_be_accepted(tmp_path, fault):
    value = fixture(tmp_path, later_fault=fault)
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize('message,timeout', [('Timeout', False), ('SegFault', False), ('Not Run', False), ('Failed', True)])
def test_timeout_crash_missing_or_transport_failure_is_not_a_completed_finding(tmp_path, message, timeout):
    value = fixture(tmp_path, message=message, transport_timeout=timeout)
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize('fault', ['log_exit', 'log_truncated', 'empty_log', 'resource_exit', 'missing_memory',
    'unknown_events', 'missing_oom', 'oom', 'oom_kill', 'oom_group_kill', 'unknown_scratch', 'full_scratch'])
def test_failed_test_requires_retained_diagnostics_and_known_available_resources(tmp_path, fault):
    value = fixture(tmp_path)
    diag = value[0]['evidence']['failure_diagnostics'][0]
    if fault == 'log_exit': diag['log_read']['exit_code'] = 1
    elif fault == 'log_truncated':
        output(diag['log_read'], canonical_bytes({'data': base64.b64encode(b'partial').decode(), 'truncated': True}))
    elif fault == 'empty_log': output(diag['log_read'], envelope(b''))
    elif fault == 'resource_exit': diag['resources']['exit_code'] = 1
    else:
        resource = json.loads(base64.b64decode(diag['resources']['output']))
        if fault == 'missing_memory': resource['memory_peak_bytes'] = None
        elif fault == 'unknown_events': resource['memory_events'] = None
        elif fault == 'missing_oom': del resource['memory_events']['oom']
        elif fault in {'oom', 'oom_kill', 'oom_group_kill'}: resource['memory_events'][fault] = 1
        elif fault == 'unknown_scratch': resource.update(scratch_capacity_bytes=None, scratch_available_bytes=None)
        elif fault == 'full_scratch': resource['scratch_available_bytes'] = 0
        output(diag['resources'], canonical_bytes(resource))
    # These remain valid retained failures under the original evidence policy.
    assert validate_retained_runtime(canonical_bytes(value[0]), *value[1:])['summary']['complete'] is False
    with pytest.raises(ValueError, match='worker_runtime_collection_incomplete'):
        validate(value)


@pytest.mark.parametrize('count', [1, 255])
def test_exit_zero_does_not_accept_an_incomplete_fuzz_campaign(tmp_path, count):
    value = fixture(tmp_path)
    fuzz = value[0]['evidence']['fuzz']
    output(fuzz['campaign'], f'#2 DONE cov: 31\nstat::number_of_executed_units: {count}\n'.encode())
    fuzz['campaign_metrics']['executions'] = count
    assert validate_retained_runtime(canonical_bytes(value[0]), *value[1:])['summary']['complete'] is False
    with pytest.raises(ValueError, match='worker_runtime_collection_incomplete'):
        validate(value)


def test_zero_coverage_does_not_prove_a_completed_instrumented_campaign(tmp_path):
    value = fixture(tmp_path)
    fuzz = value[0]['evidence']['fuzz']
    output(fuzz['campaign'], b'#256 DONE cov: 0\nstat::number_of_executed_units: 256\n')
    fuzz['campaign_metrics']['coverage_signal'] = 0
    assert validate_retained_runtime(canonical_bytes(value[0]), *value[1:])['summary']['complete'] is False
    with pytest.raises(ValueError, match='worker_runtime_collection_incomplete'):
        validate(value)


@pytest.mark.parametrize('fault', ['source', 'options', 'scope', 'plan', 'summary', 'output_hash', 'missing_replay',
    'legacy_schema', 'skipped', 'missing_result'])
def test_source_population_plan_and_evidence_cannot_be_relabelled(tmp_path, fault):
    value = fixture(tmp_path)
    retained, targets, options, scope = value
    if fault == 'source': targets['CMakeLists.txt'] = '0'*64
    elif fault == 'options': options['BUILD_TESTS'] = 'OFF'
    elif fault == 'scope': scope['fuzz_campaign_runs'] = 257
    elif fault == 'plan': retained['plan']['fuzz']['build_parallel'] = 4
    elif fault == 'summary': retained['evidence']['complete'] = True
    elif fault == 'output_hash': retained['evidence']['fuzz']['build']['output_sha256'] = '0'*64
    elif fault == 'missing_replay': retained['evidence']['fuzz']['replays'].pop()
    elif fault == 'legacy_schema': retained['evidence']['schema'] = 'nico.cpp-runtime-evidence.v3'
    elif fault == 'skipped': retained['evidence']['sanitizers'][1]['results']['skipped'] = ['unit_a']
    elif fault == 'missing_result': retained['evidence']['sanitizers'][1]['results']['executed'] = []
    with pytest.raises(ValueError):
        validate(value)
