"""Scheduling contracts and transport controls; not native workload qualification."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import base64
import zlib

import pytest

from nico import assessment_cpp_runtime_scope as scope_api
from nico import assessment_cpp_runtime_execution as runtime
from nico import assessment_cpp_project_static as static
from nico import assessment_cpp_clang_fallback as fallback
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_runtime_execution import Observe, plan
from tests.test_cpp_project_static_stage import stage_inputs
from tests.test_cpp_static_environment_integration import EnvironmentDocker, native_v2
from tests.test_cpp_clang_fallback import fallback_native, primary_with_one_failure
from tests.test_cpp_runtime_scope import _write


def source_and_scope(tmp_path):
    source = tmp_path / 'source'; source.mkdir(); targets = {}
    files = {
        'CMakeLists.txt': b'SANITIZERS BUILD_FUZZ_BINARY BUILD_FOR_FUZZING\n',
        'test/functional/test_runner.py': b'BASE_SCRIPTS = ["feature_a.py", "mempool_a.py", "p2p_a.py", "rpc_a.py"]\n',
        'test/fuzz/test_runner.py': b'FUZZ=1\n',
        'src/test/fuzz/CMakeLists.txt': b'add_executable(fuzz connect_block.cpp)\n',
        'src/test/fuzz/connect_block.cpp': b'int owned_fixture;\n',
    }
    for name in ('feature_a.py', 'mempool_a.py', 'p2p_a.py', 'rpc_a.py'):
        files['test/functional/' + name] = b'# owned fixture\n'
    for name, raw in files.items():
        _write(source, name, raw, targets)
    scope = json.loads(Path('tests/fixtures/cpp/bitcoin-runtime-scope.json').read_text())
    return source, targets, scope


def test_new_plan_caps_test_concurrency_without_changing_builds_or_clocks(tmp_path):
    source, targets, scope = source_and_scope(tmp_path)
    before = deepcopy(scope)
    derived = scope_api.derive_runtime_plan(source, targets, {}, scope,
        plan_schema='nico.cpp-runtime-plan.v2')
    assert derived['schema'] == 'nico.cpp-runtime-plan.v2'
    assert derived['sanitizers']['test_parallel'] == 2
    assert derived['sanitizers']['parallel'] == 4
    assert derived['functional']['parallel'] == 4
    assert derived['sanitizers']['test_case_seconds'] == 300
    assert derived['sanitizers']['test_seconds'] == 900
    assert derived['total_seconds'] == 6000
    assert derived['sanitizers']['kinds'] == ['address', 'undefined']
    assert scope == before


def test_runtime_transport_uses_two_tests_but_four_build_jobs_and_keeps_full_results():
    contract = plan(); contract['schema'] = 'nico.cpp-runtime-plan.v2'
    contract['sanitizers']['test_parallel'] = 2
    observed = Observe()
    evidence = runtime.execute_runtime_plan(observed, 'owned-container', contract, {'BUILD_TESTS': 'ON'})
    assert evidence['complete'] is True
    for kind in ('address', 'undefined'):
        build = observed.calls[f'runtime-{kind}-build']
        tests = observed.calls[f'runtime-{kind}-tests']
        assert build[build.index('--parallel') + 1] == '4'
        assert tests[tests.index('--parallel') + 1] == '2'
        assert tests[tests.index('--timeout') + 1] == '120'
        assert not {'-R', '-E', '--repeat', '--rerun-failed'}.intersection(tests)
    checked = runtime.validate_runtime_evidence(evidence, contract, project_options={'BUILD_TESTS': 'ON'})
    assert checked['complete'] is True
    assert all(row['passed'] == ['unit_a'] for row in checked['sanitizers'])
    assert checked['fuzz']['replay_count'] == 2
    assert checked['fuzz']['campaign_completed'] is True


class FallbackDocker(EnvironmentDocker):
    def __call__(self, argv, **kwargs):
        if static.PROGRAM in argv:
            self.calls.append((argv, kwargs)); request = json.loads(kwargs['input_bytes'])
            value = json.loads(native_v2(request, missing='stdint.h', rule='uninitvar'))
            row = value['records'][0]
            raw = base64.b64decode(row['xml'])
            if row.get('xml_encoding') == 'zlib': raw = zlib.decompress(raw)
            tree = ET.fromstring(raw)
            ET.SubElement(tree.find('errors'), 'error', {'id': 'syntaxError', 'severity': 'error', 'msg': 'Owned parser failure'})
            encoded, digest, encoding = static._encode_xml(ET.tostring(tree), compact=True)
            row.update(xml=encoded, xml_sha256=digest, xml_encoding=encoding)
            return {'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'output': _canonical(value)}
        if fallback.PROGRAM in argv:
            self.calls.append((argv, kwargs)); request = json.loads(kwargs['input_bytes'])
            return {'exit_code': 0, 'timed_out': False, 'output_truncated': False,
                    'output': _canonical(fallback_native(request, finding=True))}
        return super().__call__(argv, **kwargs)


def test_real_static_orchestrator_reduces_parallelism_but_not_coverage_or_case_limit(tmp_path):
    source, targets, database, snapshot, compiler = stage_inputs(tmp_path)
    docker = FallbackDocker(targets); artifacts = {}
    def sink(key, raw):
        artifacts[key] = raw; digest = hashlib.sha256(raw).hexdigest()
        return {'path': f'artifacts/{key}-{digest}.json', 'sha256': digest, 'bytes': len(raw)}
    result = static.run_project_static_stage(source, targets, 'sha256:'+'a'*64,
        database, snapshot, compiler, compiler_environment=True, command=docker, retain_artifact=sink)
    assert result['complete'] is True, result['error']
    requests = [json.loads(kw['input_bytes']) for argv, kw in docker.calls if fallback.PROGRAM in argv]
    assert len(requests) == 1
    request = requests[0]
    assert request['limits'] == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
    assert request['schema'] == 'nico.cpp-clang-fallback-request.v4'
    assert result['execution_budget_seconds'] == 1020 and result['wall_budget_seconds'] == 1030
    assert len(result['analysis']['analyzed_contexts']) == len(result['analysis']['required_contexts'])
    assert any(f.get('analyzer') == 'clang-static-analyzer' for f in result['analysis']['findings'])


@pytest.mark.parametrize('parallel', [1, 2, 3, 4])
def test_plan_scheduling_never_exceeds_existing_parallel_limit(tmp_path, parallel):
    source, targets, scope = source_and_scope(tmp_path)
    scope['parallel'] = parallel
    current = scope_api.derive_runtime_plan(source, targets, {}, scope,
        plan_schema='nico.cpp-runtime-plan.v2')
    historical = scope_api.derive_runtime_plan(source, targets, {}, scope,
        plan_schema='nico.cpp-runtime-plan.v1')
    assert runtime._sanitizer_test_parallel(current) == min(parallel, 2)
    assert runtime._sanitizer_test_parallel(historical) == parallel
    without_schedule = deepcopy(current)
    without_schedule['schema'] = historical['schema']
    del without_schedule['sanitizers']['test_parallel']
    assert without_schedule == historical


@pytest.mark.parametrize('value', [0, 1, 3, 4, True, '2', None])
def test_invalid_new_test_schedule_is_rejected_before_any_native_call(value):
    contract = plan(); contract['schema'] = 'nico.cpp-runtime-plan.v2'
    contract['sanitizers']['test_parallel'] = value
    observed = Observe()
    with pytest.raises(ValueError, match='worker_runtime_scheduling_invalid'):
        runtime.execute_runtime_plan(observed, 'owned', contract, {})
    assert observed.calls == {}


def test_new_runtime_result_cannot_be_relabelled_as_historical_parallel_execution():
    contract = plan(); contract['schema'] = 'nico.cpp-runtime-plan.v2'
    contract['sanitizers']['test_parallel'] = 2
    result = runtime.execute_runtime_plan(Observe(), 'owned', contract, {})
    old = plan()
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        runtime.validate_runtime_evidence(result, old, project_options={})
    # Recomputing the plan digest still cannot change the retained argv.
    result['plan_sha256'] = hashlib.sha256(_canonical(old)).hexdigest()
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        runtime.validate_runtime_evidence(result, old, project_options={})


def test_runtime_failure_is_not_retried_or_given_completion_credit():
    contract = plan(); contract['schema'] = 'nico.cpp-runtime-plan.v2'
    contract['sanitizers']['test_parallel'] = 2
    observed = Observe('runtime-address-tests')
    result = runtime.execute_runtime_plan(observed, 'owned', contract, {}, capture_failure_diagnostics=False)
    assert result['complete'] is False
    assert result['error'] == 'worker_runtime_sanitizer_failed'
    checked = runtime.validate_runtime_evidence(result, contract, project_options={})
    assert checked['complete'] is False
    assert checked['sanitizers_not_executed'] == ['undefined']
    assert checked['fuzz']['campaign_completed'] is False
    assert 'runtime-undefined-tests' not in observed.calls


def test_fallback_historical_requests_keep_exact_limits_and_current_request_keeps_membership(tmp_path):
    primary, proof = primary_with_one_failure(tmp_path)
    v1 = fallback.clang_fallback_request(primary, proof)
    v2 = fallback.clang_fallback_request(primary, proof, extended_budget=True)
    v4 = fallback.clang_fallback_request(primary, proof, extended_budget=True, contention_aware=True)
    assert fallback._request_limits(v1) == {'wall_seconds': 180, 'case_seconds': 45, 'parallel': 4}
    assert fallback._request_limits(v2) == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 4}
    assert fallback._request_limits(v4) == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
    changed = deepcopy(v4); changed['schema'] = v2['schema']; changed['limits'] = v2['limits']
    assert changed == v2
    native = fallback_native(v4, finding=True)
    assert fallback.validate_clang_fallback(_canonical(native), v4, primary)['complete'] is True
    with pytest.raises(ValueError):
        fallback.validate_clang_fallback(_canonical(native), v2, primary)


@pytest.mark.parametrize('field,value', [('parallel', 4), ('parallel', True), ('case_seconds', 240),
    ('wall_seconds', 900), ('parallel', 1)])
def test_tampered_fallback_limits_are_rejected(tmp_path, field, value):
    primary, proof = primary_with_one_failure(tmp_path)
    request = fallback.clang_fallback_request(primary, proof, extended_budget=True, contention_aware=True)
    request['limits'][field] = value
    with pytest.raises(ValueError, match='worker_clang_fallback_request_invalid'):
        fallback._request_limits(request)


def test_unpublished_extended_timeout_schema_is_not_admitted(tmp_path):
    primary, proof = primary_with_one_failure(tmp_path)
    request = fallback.clang_fallback_request(primary, proof, extended_budget=True, contention_aware=True)
    request['schema'] = 'nico.cpp-clang-fallback-request.v3'
    with pytest.raises(ValueError, match='worker_clang_fallback_request_invalid'):
        fallback._request_limits(request)
    with pytest.raises(ValueError, match='worker_clang_fallback_request_invalid'):
        fallback.clang_fallback_request(primary, proof, contention_aware=True)


def test_retained_runtime_rejects_cross_schema_corruption_even_after_plan_rehash(tmp_path):
    source, targets, scope = source_and_scope(tmp_path)
    original = scope_api.derive_runtime_plan(source, targets, {}, scope, plan_schema='nico.cpp-runtime-plan.v1')
    class SourceObserve(Observe):
        def __call__(self, key, argv, **kwargs):
            row = super().__call__(key, argv, **kwargs)
            if key == 'runtime-functional-results':
                raw = ('test,status,duration(seconds)\n' + ''.join(
                    name + ',Passed,1\n' for name in original['functional']['selected_tests']) + 'ALL,Passed,4\n').encode()
                row['output'] = _canonical({'data':base64.b64encode(raw).decode(), 'truncated':False})
            if key == 'runtime-fuzz-corpus-stage':
                row['output'] = _canonical([{'path':'/work/runtime-corpus/connect_block/s'+str(i),
                    'sha256':value['sha256'], 'bytes':value['bytes']}
                    for i,value in enumerate(original['fuzz']['corpus'])])
            return row
    evidence = runtime.execute_runtime_plan(SourceObserve(), 'owned', original, {})
    assert evidence['complete'] is True
    interfaces = scope_api.capture_runtime_interfaces(source, targets)
    retained = scope_api.retained_runtime_bytes(interfaces, original, evidence)
    assert scope_api.validate_retained_runtime(retained, targets, {}, scope)['summary']['complete'] is True
    corrupted = json.loads(retained)
    corrupted['plan']['schema'] = 'nico.cpp-runtime-plan.v2'
    with pytest.raises(ValueError, match='worker_runtime_retained_invalid'):
        scope_api.validate_retained_runtime(_canonical(corrupted), targets, {}, scope)
    corrupted['plan']['sanitizers']['test_parallel'] = 2
    corrupted['evidence']['plan_sha256'] = hashlib.sha256(_canonical(corrupted['plan'])).hexdigest()
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        scope_api.validate_retained_runtime(_canonical(corrupted), targets, {}, scope)


@pytest.mark.parametrize('bad', [None, True, 1, {}, [], 'nico.cpp-runtime-plan.v4'])
def test_unknown_or_nonstring_plan_schema_is_rejected(tmp_path, bad):
    source, targets, scope = source_and_scope(tmp_path)
    with pytest.raises(ValueError, match='worker_runtime_scope_unsupported'):
        scope_api.derive_runtime_plan(source, targets, {}, scope, plan_schema=bad)
