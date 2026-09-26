"""Versioned build scheduling; these controls do not prove native throughput."""
from copy import deepcopy
import base64
import hashlib
import json

import pytest

from nico import assessment_cpp_runtime_execution as runtime
from nico import assessment_cpp_runtime_scope as scope_api
from nico.assessment_worker_receipts import canonical_bytes
from tests.test_cpp_contention_scheduling import source_and_scope
from tests.test_cpp_runtime_execution import Observe, plan


def current_plan():
    value = plan()
    value['schema'] = 'nico.cpp-runtime-plan.v3'
    value['sanitizers']['test_parallel'] = 2
    value['fuzz']['build_parallel'] = 2
    return value


@pytest.mark.parametrize('parallel', [1, 2, 3, 4])
def test_current_plan_only_adds_bounded_fuzz_build_scheduling(tmp_path, parallel):
    source, targets, scope = source_and_scope(tmp_path)
    scope['parallel'] = parallel
    before = deepcopy(scope)
    current = scope_api.derive_runtime_plan(source, targets, {}, scope)
    historical = scope_api.derive_runtime_plan(source, targets, {}, scope,
        plan_schema='nico.cpp-runtime-plan.v2')
    assert current['schema'] == 'nico.cpp-runtime-plan.v3'
    assert current['fuzz']['build_parallel'] == min(2, parallel)
    assert current['fuzz']['parallel'] == 1
    restored = deepcopy(current)
    restored['schema'] = historical['schema']
    del restored['fuzz']['build_parallel']
    assert restored == historical
    assert scope == before


def test_executor_and_validator_bind_two_build_jobs_with_original_limits():
    class Capture(Observe):
        def __init__(self):
            super().__init__(); self.options = {}
        def __call__(self, key, argv, **kwargs):
            self.options[key] = kwargs
            return super().__call__(key, argv, **kwargs)
    observer = Capture()
    contract = current_plan()
    result = runtime.execute_runtime_plan(observer, 'owned', contract, {})
    assert result['complete'] is True
    assert observer.calls['runtime-fuzz-build'] == ['docker', 'exec', 'owned',
        'cmake', '--build', '/work/fuzz-build', '--parallel', '2', '--target', 'fuzz']
    assert observer.options['runtime-fuzz-build']['seconds'] == 1200
    assert contract['total_seconds'] == 6000
    assert result['plan_sha256'] == hashlib.sha256(canonical_bytes(contract)).hexdigest()
    checked = runtime.validate_runtime_evidence(result, contract, project_options={})
    assert checked['complete'] is True
    assert checked['fuzz']['replay_count'] == 2
    assert checked['fuzz']['campaign_completed'] is True
    assert result['fuzz']['campaign']['argv'] == [
        '/work/fuzz-build/bin/fuzz', '-runs=256', '-max_total_time=300',
        '-print_final_stats=1', '-seed=1', '-max_len=4096',
        '/work/runtime-campaign/connect_block']


@pytest.mark.parametrize('schema', ['nico.cpp-runtime-plan.v1', 'nico.cpp-runtime-plan.v2'])
def test_historical_plans_keep_serial_native_argv(schema):
    contract = plan(); contract['schema'] = schema
    if schema.endswith('v2'):
        contract['sanitizers']['test_parallel'] = 2
    observer = Observe()
    result = runtime.execute_runtime_plan(observer, 'owned', contract, {})
    argv = observer.calls['runtime-fuzz-build']
    assert argv[argv.index('--parallel') + 1] == '1'
    assert runtime.validate_runtime_evidence(result, contract, project_options={})['complete'] is True


@pytest.mark.parametrize('value', [None, 0, 1, 3, 4, True, '2'])
def test_invalid_build_schedule_aborts_before_execution(value):
    contract = current_plan()
    if value is None:
        del contract['fuzz']['build_parallel']
    else:
        contract['fuzz']['build_parallel'] = value
    observer = Observe()
    with pytest.raises(ValueError, match='worker_runtime_scheduling_invalid'):
        runtime.execute_runtime_plan(observer, 'owned', contract, {})
    assert observer.calls == {}


@pytest.mark.parametrize('schema', ['nico.cpp-runtime-plan.v1', 'nico.cpp-runtime-plan.v2'])
def test_historical_schema_cannot_claim_new_schedule(schema):
    contract = current_plan(); contract['schema'] = schema
    if schema.endswith('v1'):
        del contract['sanitizers']['test_parallel']
    observer = Observe()
    with pytest.raises(ValueError, match='worker_runtime_scheduling_invalid'):
        runtime.execute_runtime_plan(observer, 'owned', contract, {})
    assert observer.calls == {}


@pytest.mark.parametrize('parallel', ['1', '3', '4'])
def test_native_build_argv_cannot_disagree_with_plan(parallel):
    contract = current_plan()
    result = runtime.execute_runtime_plan(Observe(), 'owned', contract, {})
    result['fuzz']['build']['argv'][4] = parallel
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        runtime.validate_runtime_evidence(result, contract, project_options={})


def test_rehashing_historical_plan_cannot_relabel_new_native_execution():
    contract = current_plan()
    result = runtime.execute_runtime_plan(Observe(), 'owned', contract, {})
    old = deepcopy(contract); old['schema'] = 'nico.cpp-runtime-plan.v2'
    del old['fuzz']['build_parallel']
    result['plan_sha256'] = hashlib.sha256(canonical_bytes(old)).hexdigest()
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        runtime.validate_runtime_evidence(result, old, project_options={})


def test_timed_out_build_is_retained_and_no_fuzz_execution_follows():
    class Timeout(Observe):
        def __call__(self, key, argv, **kwargs):
            row = super().__call__(key, argv, **kwargs)
            if key == 'runtime-fuzz-build':
                row.update(exit_code=124, timed_out=True, output=b'owned compile still running')
            return row
    observer = Timeout(); contract = current_plan()
    result = runtime.execute_runtime_plan(observer, 'owned', contract, {})
    assert result['complete'] is False
    assert result['fuzz']['build']['timed_out'] is True
    assert not any(k.startswith('runtime-fuzz-replay') for k in observer.calls)
    assert 'runtime-fuzz-campaign' not in observer.calls
    checked = runtime.validate_runtime_evidence(result, contract, project_options={})
    assert checked['complete'] is False
    assert checked['failure_operation'] == 'runtime-fuzz-build'
    assert checked['fuzz']['campaign_completed'] is False


@pytest.mark.parametrize('schema', ['nico.cpp-runtime-plan.v1', 'nico.cpp-runtime-plan.v2',
                                   'nico.cpp-runtime-plan.v3'])
def test_source_bound_retained_plan_reconstructs_with_its_original_schedule(tmp_path, schema):
    source, targets, scope = source_and_scope(tmp_path)
    contract = scope_api.derive_runtime_plan(source, targets, {}, scope, plan_schema=schema)
    class SourceObserve(Observe):
        def __call__(self, key, argv, **kwargs):
            row = super().__call__(key, argv, **kwargs)
            if key == 'runtime-functional-results':
                raw = ('test,status,duration(seconds)\n' + ''.join(
                    name + ',Passed,1\n' for name in contract['functional']['selected_tests'])
                    + 'ALL,Passed,4\n').encode()
                row['output'] = canonical_bytes({'data':base64.b64encode(raw).decode(), 'truncated':False})
            if key == 'runtime-fuzz-corpus-stage':
                row['output'] = canonical_bytes([{'path':'/work/runtime-corpus/connect_block/s'+str(i),
                    'sha256':value['sha256'], 'bytes':value['bytes']}
                    for i,value in enumerate(contract['fuzz']['corpus'])])
            return row
    evidence = runtime.execute_runtime_plan(SourceObserve(), 'owned', contract, {})
    interfaces = scope_api.capture_runtime_interfaces(source, targets)
    retained = scope_api.retained_runtime_bytes(interfaces, contract, evidence)
    checked = scope_api.validate_retained_runtime(retained, targets, {}, scope)
    assert checked['summary']['complete'] is True
    if schema.endswith('v3'):
        corrupted = json.loads(retained)
        corrupted['plan']['fuzz']['build_parallel'] = 4
        corrupted['evidence']['plan_sha256'] = hashlib.sha256(canonical_bytes(corrupted['plan'])).hexdigest()
        with pytest.raises(ValueError, match='worker_runtime_retained_invalid'):
            scope_api.validate_retained_runtime(canonical_bytes(corrupted), targets, {}, scope)
