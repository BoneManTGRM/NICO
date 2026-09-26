"""Cost hints change scheduling only; actual target completion needs native evidence."""
from copy import deepcopy
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from nico import assessment_cpp_runtime_execution as runtime
from nico import assessment_cpp_runtime_scope as scope_api
from tests.test_cpp_contention_scheduling import source_and_scope
from tests.test_cpp_runtime_execution import Observe


def test_new_plan_only_adds_versioned_address_cost_hints(tmp_path):
    source, targets, scope = source_and_scope(tmp_path)
    original = deepcopy(scope)
    current = scope_api.derive_runtime_plan(source, targets, {}, scope)
    old = scope_api.derive_runtime_plan(source, targets, {}, scope,
                                      plan_schema='nico.cpp-runtime-plan.v3')
    assert current['schema'] == 'nico.cpp-runtime-plan.v4'
    assert current['sanitizers']['test_schedule'] == 'retained-address-cost-v1'
    restored = deepcopy(current)
    restored['schema'] = old['schema']
    del restored['sanitizers']['test_schedule']
    del restored['sanitizers']['address_costs_ms']
    assert restored == old and scope == original
    assert current['sanitizers']['test_parallel'] == 2
    assert current['sanitizers']['test_case_seconds'] == 300
    assert current['sanitizers']['test_seconds'] == 900


def current_plan(tmp_path):
    source, targets, scope = source_and_scope(tmp_path)
    return scope_api.derive_runtime_plan(source, targets, {}, scope)


def scheduler():
    from nico.assessment_cpp_test_schedule import SCHEDULE_LOG_EXEC_PROGRAM
    namespace = {'__name__': 'owned_control'}
    exec(SCHEDULE_LOG_EXEC_PROGRAM, namespace)
    return namespace['schedule_costs']


@pytest.mark.parametrize('fault', ['missing', 'policy', 'cost', 'bool', 'name', 'historical'])
def test_invalid_cost_policy_aborts_before_native_execution(tmp_path, fault):
    plan = current_plan(tmp_path)
    if fault == 'missing': del plan['sanitizers']['address_costs_ms']
    elif fault == 'policy': plan['sanitizers']['test_schedule'] = 'unknown'
    elif fault == 'cost': plan['sanitizers']['address_costs_ms']['coinselector_tests'] += 1
    elif fault == 'bool': plan['sanitizers']['address_costs_ms']['coinselector_tests'] = True
    elif fault == 'name': plan['sanitizers']['address_costs_ms']['unexpected'] = 1
    else: plan['schema'] = 'nico.cpp-runtime-plan.v3'
    observe = Observe()
    with pytest.raises(ValueError, match='worker_runtime_scheduling_invalid'):
        runtime.execute_runtime_plan(observe, 'owned', plan, {})
    assert observe.calls == {}


def test_native_argv_preserves_limits_and_only_address_gets_new_wrapper(tmp_path):
    from nico.assessment_cpp_test_schedule import ADDRESS_COSTS_MS, SCHEDULE_LOG_EXEC_PROGRAM
    plan = current_plan(tmp_path)
    for kind in ('address', 'undefined'):
        argv = runtime._sanitizer_test_argv(plan, kind)
        assert argv[argv.index('ctest'):] == ['ctest', '--test-dir', '/work/sanitize-'+kind,
            '--parallel', '2', '--timeout', '300', '--output-on-failure',
            '--output-junit', '/work/sanitize-'+kind+'/nico-runtime-junit.xml']
        if kind == 'address':
            assert argv[4] == SCHEDULE_LOG_EXEC_PROGRAM and json.loads(argv[6]) == ADDRESS_COSTS_MS
        else:
            assert argv[4] == runtime.LOG_EXEC_PROGRAM


@pytest.mark.parametrize('schema', ['v1', 'v2', 'v3'])
def test_historical_plans_keep_the_original_wrapper(tmp_path, schema):
    source, targets, scope = source_and_scope(tmp_path)
    plan = scope_api.derive_runtime_plan(source, targets, {}, scope,
                                        plan_schema='nico.cpp-runtime-plan.'+schema)
    for kind in ('address', 'undefined'):
        assert runtime._sanitizer_test_argv(plan, kind)[4] == runtime.LOG_EXEC_PROGRAM


@pytest.mark.parametrize('fault', ['root_link', 'directory_link', 'file_link', 'hard_link',
                                  'fifo', 'oversized', 'empty', 'repeated'])
def test_metadata_write_rejects_unsafe_paths_without_changing_other_files(tmp_path, fault):
    root = tmp_path/'work'; root.mkdir()
    directory = root/'sanitize-address'; directory.mkdir()
    path = directory/'CTestTestfile.cmake'; original = b'add_test(unit_a /bin/true)\n'
    path.write_bytes(original)
    outside = tmp_path/'outside'; outside.write_bytes(original)
    if fault == 'root_link':
        link = tmp_path/'link'; link.symlink_to(root, target_is_directory=True); root = link
    elif fault == 'directory_link':
        real = root/'real'; directory.rename(real); directory.symlink_to(real, target_is_directory=True)
    elif fault == 'file_link': path.unlink(); path.symlink_to(outside)
    elif fault == 'hard_link': path.unlink(); os.link(outside, path)
    elif fault == 'fifo': path.unlink(); os.mkfifo(path)
    elif fault == 'oversized': path.write_bytes(b'x'*1048577)
    elif fault == 'empty': path.write_bytes(b'')
    else: scheduler()({'coinselector_tests': 121812}, root=str(root))
    with pytest.raises((OSError, ValueError)):
        scheduler()({'coinselector_tests': 121812}, root=str(root))
    assert outside.read_bytes() == original


@pytest.mark.parametrize('costs', [{}, {'a)': 5}, {'a\nb': 5}, {'a': True}, {'a': 0}, {'a': 300001}])
def test_metadata_never_interprets_arbitrary_cmake_or_unbounded_costs(tmp_path, costs):
    with pytest.raises(ValueError, match='worker_runtime_schedule_invalid'):
        scheduler()(costs, root=str(tmp_path))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('outcome', ['passed', 'failed', 'timed_out'])
def test_real_ctest_prioritizes_long_suites_without_changing_membership_or_results(tmp_path, outcome):
    from nico.assessment_cpp_test_schedule import ADDRESS_COSTS_MS
    ctest = shutil.which('ctest')
    if ctest is None:
        pytest.skip('native CTest unavailable')
    root = tmp_path/'work'; directory = root/'sanitize-address'; sub = directory/'nested'
    sub.mkdir(parents=True)
    names = ['quick_first', 'quick_second', 'coinselector_tests', 'cluster_linearize_tests']
    lines = []
    for name in names:
        code = ('import time; time.sleep(.2)' if outcome == 'timed_out' and name == 'coinselector_tests'
                else 'raise SystemExit(1)' if outcome == 'failed' and name == 'coinselector_tests'
                else 'import time; time.sleep(.02)')
        lines.append(f'add_test({name} "{sys.executable}" "-c" "{code}")\n')
    if outcome == 'timed_out':
        lines.append('set_tests_properties(coinselector_tests PROPERTIES TIMEOUT .01)\n')
    (sub/'CTestTestfile.cmake').write_text(''.join(lines))
    metadata = directory/'CTestTestfile.cmake'; metadata.write_text('subdirs("nested")\n')

    def discovery():
        data = json.loads(subprocess.check_output([ctest, '--test-dir', str(directory), '--show-only=json-v1']))
        data.pop('backtraceGraph', None)
        for test in data['tests']:
            test.pop('backtrace', None)
            test['properties'] = [p for p in test.get('properties', []) if p['name'] != 'COST']
        return data

    before = discovery()
    unchanged = (sub/'CTestTestfile.cmake').read_bytes()
    proof = scheduler()(dict(ADDRESS_COSTS_MS), root=str(root))
    assert proof['policy'] == 'retained-address-cost-v1'
    assert discovery() == before
    assert (sub/'CTestTestfile.cmake').read_bytes() == unchanged
    junit = directory/'junit.xml'
    completed = subprocess.run([ctest, '--test-dir', str(directory), '--parallel', '2',
        '--timeout', '300', '--output-on-failure', '--output-junit', str(junit)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900)
    assert re.findall(r'Start\s+\d+: (\S+)', completed.stdout)[:2] == [
        'cluster_linearize_tests', 'coinselector_tests']
    rows = list(ET.parse(junit).getroot().iter('testcase'))
    assert sorted(row.get('name') for row in rows) == sorted(names)
    assert completed.returncode == (0 if outcome == 'passed' else 8)
    failures = [row for row in rows if row.find('failure') is not None]
    assert [row.get('name') for row in failures] == ([] if outcome == 'passed' else ['coinselector_tests'])
    if outcome == 'timed_out':
        assert failures[0].find('failure').get('message') == 'Timeout'
