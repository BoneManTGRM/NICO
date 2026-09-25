import base64
import hashlib
import json

from nico.assessment_cpp_runtime_execution import execute_runtime_plan, validate_runtime_evidence


def plan():
    corpus=[
        {'path':'qa/a','git_blob_sha':'a'*40,'sha256':hashlib.sha256(b'a').hexdigest(),'bytes':1,'base64':base64.b64encode(b'a').decode()},
        {'path':'qa/b','git_blob_sha':'b'*40,'sha256':hashlib.sha256(b'b').hexdigest(),'bytes':1,'base64':base64.b64encode(b'b').decode()},
    ]
    return {'schema':'nico.cpp-runtime-plan.v1','total_seconds':6000,'unit_test_data':None,
        'functional':{'policy':'source-declared-functional-v1','runner':'test/functional/test_runner.py',
            'selected_tests':['feature_a.py','mempool_a.py'],'seconds':900,'parallel':4},
        'sanitizers':{'interface':'SANITIZERS','kinds':['address','undefined'],'build_seconds':1200,
            'test_seconds':600,'test_case_seconds':120,'parallel':4},
        'fuzz':{'policy':'source-declared-libfuzzer-v1','build_target':'fuzz','binary':'bin/fuzz',
            'target':'connect_block','qa_assets_repository':'bitcoin-core/qa-assets','qa_assets_commit':'c'*40,
            'corpus':corpus,'replay_runs':1,'campaign_runs':256,'campaign_seconds':300,'parallel':1}}


class Observe:
    def __init__(self, fault=None):
        self.fault=fault; self.calls={}
    def __call__(self,key,argv,**kwargs):
        self.calls[key]=argv
        output=b''
        exit_code=1 if key==self.fault else 0
        if key.startswith('runtime-reclaim-'):
            phase=key.removeprefix('runtime-reclaim-')
            removed={'baseline':['build','functional-tests'],
                     'address':['sanitize-address'],'undefined':['sanitize-undefined']}[phase]
            output=json.dumps({'phase':phase,'removed':removed,
                'before':{'capacity_bytes':9*1024**3,'available_bytes':1024**3},
                'after':{'capacity_bytes':9*1024**3,'available_bytes':8*1024**3}}).encode()
        elif key=='runtime-functional-results':
            csv=b'test,status,duration(seconds)\r\nfeature_a.py,Passed,1\r\nmempool_a.py,Passed,1\r\nALL,Passed,2\r\n'
            output=json.dumps({'data':base64.b64encode(csv).decode(),'truncated':False}).encode()
        elif key.endswith('-discover'):
            output=json.dumps({'tests':[{'name':'unit_a'}]}).encode()
        elif key.endswith('-junit'):
            xml=b'<testsuite tests="1"><testcase name="unit_a"/></testsuite>'
            output=json.dumps({'data':base64.b64encode(xml).decode(),'truncated':False}).encode()
        elif key=='runtime-fuzz-campaign':
            output=b'#2 INITED cov: 7 ft: 9 corp: 2/4b\n#256 DONE cov: 31 ft: 40 corp: 7/100b\nstat::number_of_executed_units: 256\n'
        elif key=='runtime-fuzz-corpus-stage':
            output=json.dumps([
                {'path':'/work/runtime-corpus/connect_block/s0','sha256':hashlib.sha256(b'a').hexdigest(),'bytes':1},
                {'path':'/work/runtime-corpus/connect_block/s1','sha256':hashlib.sha256(b'b').hexdigest(),'bytes':1},
            ],sort_keys=True).encode()
        return {'exit_code':exit_code,'timed_out':False,'output_truncated':False,'output':output}


def test_runtime_execution_requires_functional_sanitizers_and_bounded_fuzz():
    value=execute_runtime_plan(Observe(),'container',plan(),{'BUILD_TESTS':'ON'})
    assert value['complete'] is True and value['error'] is None
    proof=validate_runtime_evidence(value,plan())
    assert proof['complete'] is True
    assert proof['functional']['passed']==['feature_a.py','mempool_a.py']
    assert [row['kind'] for row in proof['sanitizers']]==['address','undefined']
    assert proof['fuzz']['replay_count']==2 and proof['fuzz']['campaign_completed'] is True
    assert proof['fuzz']['campaign_executions']==256 and proof['fuzz']['campaign_coverage_signal']==31
    assert '-print_final_stats=1' in value['fuzz']['campaign']['argv']


def test_runtime_execution_failure_is_retained_and_cannot_be_complete():
    value=execute_runtime_plan(Observe('runtime-fuzz-campaign'),'container',plan(),{'BUILD_TESTS':'ON'})
    assert value['complete'] is False
    assert value['error']=='worker_runtime_fuzz_failed'
    proof=validate_runtime_evidence(value,plan())
    assert proof['complete'] is False

def test_runtime_evidence_retains_raw_functional_and_sanitizer_result_reads():
    value=execute_runtime_plan(Observe(),'container',plan(),{'BUILD_TESTS':'ON'})
    assert 'results_read' in value['functional']
    assert all('junit_read' in row for row in value['sanitizers'])
    proof=validate_runtime_evidence(value,plan())
    assert proof['complete'] is True


def test_runtime_validator_rejects_tampered_retained_result_read():
    import pytest
    value=execute_runtime_plan(Observe(),'container',plan(),{'BUILD_TESTS':'ON'})
    value['functional']['results_read']['output_sha256']='0'*64
    with pytest.raises(ValueError,match='runtime_evidence_invalid'):
        validate_runtime_evidence(value,plan())


"""Runtime CSV membership, not presentation order, binds executed tests."""
import base64
import csv
import io
import json

import pytest

from nico.assessment_cpp_runtime_execution import (
    _parse_functional_csv, execute_runtime_plan, validate_runtime_evidence,
)


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['test', 'status', 'duration(seconds)'])
    writer.writerows(rows)
    return stream.getvalue().encode()


class SortedResults(Observe):
    def __call__(self, key, argv, **kwargs):
        result = super().__call__(key, argv, **kwargs)
        if key == 'runtime-functional-results':
            raw = csv_bytes([
                ['feature_a.py', 'Passed', '1'],
                ['interface_ipc.py', 'Passed', '2'],
                ['mempool_a.py', 'Passed', '3'],
                ['ALL', 'Passed', '3'],
            ])
            result['output'] = json.dumps({
                'data': base64.b64encode(raw).decode(), 'truncated': False,
            }).encode()
        return result


def test_sorted_upstream_csv_completes_the_original_selected_population():
    contract = plan()
    selected = ['feature_a.py', 'mempool_a.py', 'interface_ipc.py']
    contract['functional']['selected_tests'] = selected
    native = execute_runtime_plan(SortedResults(), 'container', contract, {'BUILD_TESTS': 'ON'})
    assert native['complete'] is True, native['error']
    verified = validate_runtime_evidence(native, contract)
    assert verified['functional']['required'] == selected
    assert verified['functional']['executed'] == selected
    assert verified['functional']['passed'] == selected


def test_status_sorted_failures_and_skips_preserve_the_selected_order_and_truth():
    selected = ['feature_a.py', 'mempool_a.py', 'interface_ipc.py']
    raw = csv_bytes([
        ['interface_ipc.py', 'Passed', '1'],
        ['mempool_a.py', 'Skipped', '0'],
        ['feature_a.py', 'Failed', '2'],
        ['ALL', 'Failed', '2'],
    ])
    assert _parse_functional_csv(raw, selected) == {
        'required': selected,
        'executed': ['feature_a.py', 'interface_ipc.py'],
        'passed': ['interface_ipc.py'],
        'failed': ['feature_a.py'],
        'skipped': ['mempool_a.py'],
    }


def test_skipped_rows_are_not_executed_even_when_upstream_total_says_passed():
    raw = csv_bytes([['feature_a.py', 'Skipped', '0'], ['ALL', 'Passed', '0']])
    result = _parse_functional_csv(raw, ['feature_a.py'])
    assert result['executed'] == []
    assert result['skipped'] == ['feature_a.py']


@pytest.mark.parametrize('rows', [
    [['feature_a.py', 'Passed', '1'], ['feature_a.py', 'Passed', '1'], ['ALL', 'Passed', '2']],
    [['other.py', 'Passed', '1'], ['ALL', 'Passed', '1']],
    [['ALL', 'Passed', '0']],
    [['feature_a.py', 'Passed', '1'], []],
    [[], ['ALL', 'Passed', '1']],
    [['feature_a.py', 'Passed', '1'], ['ALL']],
    [['feature_a.py', 'Failed', '1'], ['ALL', 'Passed', '1']],
    [['feature_a.py', 'Passed', '1'], ['ALL', 'Failed', '1']],
    [['feature_a.py', 'Passed', '-1'], ['ALL', 'Passed', '1']],
    [['feature_a.py', 'Passed', 'nan'], ['ALL', 'Passed', '1']],
    [['feature_a.py', 'Passed', '1'], ['ALL', 'Passed', 'Infinity']],
])
def test_malformed_or_contradictory_csv_cannot_pass(rows):
    with pytest.raises(ValueError, match='worker_runtime_functional_results_invalid'):
        _parse_functional_csv(csv_bytes(rows), ['feature_a.py'])


"""Native summaries cannot stand in for the frozen command/seed population."""
from copy import deepcopy

import pytest

from nico.assessment_cpp_runtime_execution import execute_runtime_plan, validate_runtime_evidence


def native():
    contract = plan()
    value = execute_runtime_plan(Observe(), 'container', contract, {'BUILD_TESTS': 'ON'})
    return contract, value


@pytest.mark.parametrize('fault', [
    'functional_command', 'functional_user', 'functional_workdir', 'functional_read_failed',
    'functional_read_path', 'sanitizer_flags', 'sanitizer_options', 'sanitizer_read_failed',
    'sanitizer_test_environment', 'fuzz_target_environment', 'fuzz_campaign_runs',
    'fuzz_replays_missing', 'fuzz_replays_duplicate', 'fuzz_replay_other_seed',
    'fuzz_replay_user', 'fuzz_replay_extra', 'fuzz_replay_id',
    'negative_duration', 'sequential_duration', 'exit_code_range',
])
def test_reconstructed_runtime_rejects_changed_commands_seeds_and_envelopes(fault):
    contract, value = native()
    functional = value['functional']
    sanitizer = value['sanitizers'][0]
    fuzz = value['fuzz']
    if fault == 'functional_command': functional['operation']['argv'] = ['true']
    elif fault == 'functional_user': functional['operation']['user'] = '0:0'
    elif fault == 'functional_workdir': functional['operation']['workdir'] = '/tmp'
    elif fault == 'functional_read_failed': functional['results_read']['exit_code'] = 1
    elif fault == 'functional_read_path': functional['results_read']['argv'][-2] = '/work/other.csv'
    elif fault == 'sanitizer_flags': sanitizer['configure']['argv'][-1] = '-DSANITIZERS='
    elif fault == 'sanitizer_options': sanitizer['configure']['argv'][-2] = '-DBUILD_TESTS=OFF'
    elif fault == 'sanitizer_read_failed': sanitizer['junit_read']['timed_out'] = True
    elif fault == 'sanitizer_test_environment': sanitizer['tests']['environment'] = {}
    elif fault == 'fuzz_target_environment': fuzz['campaign']['environment']['FUZZ'] = 'other'
    elif fault == 'fuzz_campaign_runs': fuzz['campaign']['argv'][1] = '-runs=1'
    elif fault == 'fuzz_replays_missing': fuzz['replays'] = []
    elif fault == 'fuzz_replays_duplicate': fuzz['replays'][1] = deepcopy(fuzz['replays'][0])
    elif fault == 'fuzz_replay_other_seed': fuzz['replays'][1]['argv'][-1] = '/work/runtime-corpus/connect_block/s0'
    elif fault == 'fuzz_replay_user': fuzz['replays'][0]['user'] = '0:0'
    elif fault == 'fuzz_replay_extra': fuzz['replays'].append(deepcopy(fuzz['replays'][0]))
    elif fault == 'fuzz_replay_id': fuzz['replays'][0]['id'] = 'another-operation'
    elif fault == 'negative_duration': fuzz['replays'][0]['duration_ms'] = -1
    elif fault == 'sequential_duration': functional['operation']['duration_ms'] = value['duration_ms'] + 3000
    elif fault == 'exit_code_range': functional['operation']['exit_code'] = 1000000
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        validate_runtime_evidence(value, contract, project_options={'BUILD_TESTS': 'ON'})


def test_runtime_validation_keeps_real_failure_and_valid_bound_control():
    contract, value = native()
    assert validate_runtime_evidence(value, contract, project_options={'BUILD_TESTS': 'ON'})['complete']
    failed = execute_runtime_plan(Observe('runtime-fuzz-campaign'), 'container', contract, {'BUILD_TESTS': 'ON'})
    assert validate_runtime_evidence(failed, contract, project_options={'BUILD_TESTS': 'ON'})['complete'] is False


"""Retained-stage reclamation and first-failure transport regressions.

The observer models only the unavailable Docker transport. The reclamation
program itself is exercised against real owned directories and symlinks below.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from nico import assessment_cpp_runtime_execution as runtime

PHASES = {'baseline': ['build', 'functional-tests'],
          'address': ['sanitize-address'], 'undefined': ['sanitize-undefined']}


class ReclaimObserve(Observe):
    def __call__(self, key, argv, **kwargs):
        value = super().__call__(key, argv, **kwargs)
        if key.startswith('runtime-reclaim-'):
            phase = key.removeprefix('runtime-reclaim-')
            value['output'] = json.dumps({'phase': phase, 'removed': PHASES[phase],
                'before': {'capacity_bytes': 9*1024**3, 'available_bytes': 1024**3},
                'after': {'capacity_bytes': 9*1024**3, 'available_bytes': 8*1024**3}}).encode()
        return value


@pytest.mark.parametrize('phase,next_operation', [
    ('baseline', 'runtime-address-configure'),
    ('address', 'runtime-undefined-configure'),
    ('undefined', 'runtime-fuzz-corpus-stage'),
])
def test_completed_worktree_is_reclaimed_only_after_native_result_retention(phase, next_operation):
    observer = ReclaimObserve()
    value = runtime.execute_runtime_plan(observer, 'container', plan(), {'BUILD_TESTS': 'ON'})
    calls = list(observer.calls)
    retained = 'runtime-functional-results' if phase == 'baseline' else 'runtime-'+phase+'-junit'
    reclaimed = 'runtime-reclaim-'+phase
    assert reclaimed in calls, 'The completed build is still occupying the shared scratch budget.'
    assert calls.index(retained) < calls.index(reclaimed) < calls.index(next_operation)
    assert value['complete'] is True
    assert runtime.validate_runtime_evidence(value, plan())['complete'] is True


@pytest.mark.parametrize('failed,forbidden', [
    ('runtime-address-configure', 'runtime-address-build'),
    ('runtime-address-build', 'runtime-address-discover'),
    ('runtime-address-discover', 'runtime-address-tests'),
    ('runtime-undefined-configure', 'runtime-undefined-build'),
    ('runtime-undefined-build', 'runtime-undefined-discover'),
    ('runtime-fuzz-corpus-stage', 'runtime-fuzz-configure'),
    ('runtime-fuzz-configure', 'runtime-fuzz-build'),
    ('runtime-fuzz-build', 'runtime-fuzz-replay-0'),
])
def test_native_prerequisite_failure_is_retained_before_stopping(failed, forbidden):
    observer = ReclaimObserve(failed)
    value = runtime.execute_runtime_plan(observer, 'container', plan(), {'BUILD_TESTS': 'ON'})
    assert failed in observer.calls
    assert forbidden not in observer.calls, 'Execution continued after its required producer failed.'
    assert value['complete'] is False
    assert failed in json.dumps(value), 'The exact failed operation was discarded.'


@pytest.mark.parametrize('phase', list(PHASES))
def test_failed_reclamation_never_starts_the_next_stage(phase):
    observer = ReclaimObserve('runtime-reclaim-'+phase)
    value = runtime.execute_runtime_plan(observer, 'container', plan(), {'BUILD_TESTS': 'ON'})
    assert value['complete'] is False
    assert value['error'] == 'worker_runtime_reclamation_failed'
    assert value['reclamations'][-1]['exit_code'] == 1
    following = {'baseline': 'runtime-address-configure', 'address': 'runtime-undefined-configure',
                 'undefined': 'runtime-fuzz-corpus-stage'}[phase]
    assert following not in observer.calls


def _native_reclaimer():
    assert hasattr(runtime, 'RECLAIM_PROGRAM'), 'No fixed-scope workspace reclamation exists.'
    namespace = {'__name__': 'owned_reclamation_test'}
    exec(compile(runtime.RECLAIM_PROGRAM, '<trusted-workspace-reclaimer>', 'exec'), namespace)
    return namespace['reclaim']


def test_real_owned_reclamation_preserves_source_and_does_not_follow_nested_links(tmp_path):
    root = tmp_path/'work'; root.mkdir()
    for name in ('build', 'functional-tests', 'source', 'analysis-private', 'unit_test_data'):
        (root/name).mkdir()
        (root/name/'retained').write_bytes((name*1000).encode())
    (root/'build'/'source-link').symlink_to(root/'source', target_is_directory=True)
    expected = {name: (root/name/'retained').read_bytes()
                for name in ('source', 'analysis-private', 'unit_test_data')}
    result = _native_reclaimer()('baseline', root=root)
    assert result['removed'] == ['build', 'functional-tests']
    assert not (root/'build').exists() and not (root/'functional-tests').exists()
    for name, raw in expected.items():
        assert (root/name/'retained').read_bytes() == raw
    assert result['after']['available_bytes'] >= result['before']['available_bytes']


def test_reclaimer_rejects_top_level_link_before_deleting_any_stage(tmp_path):
    root = tmp_path/'work'; root.mkdir()
    (root/'build').mkdir(); (root/'build'/'proof').write_text('must survive')
    (root/'source').mkdir(); (root/'source'/'proof').write_text('immutable source')
    (root/'functional-tests').symlink_to(root/'source', target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        _native_reclaimer()('baseline', root=root)
    assert (root/'build'/'proof').read_text() == 'must survive'
    assert (root/'source'/'proof').read_text() == 'immutable source'


@pytest.mark.parametrize('phase', ['source', '../source', '/work', '', 'fuzz-build'])
def test_reclaimer_has_no_caller_selected_cleanup_path(tmp_path, phase):
    (tmp_path/'sentinel').write_text('owned')
    with pytest.raises(ValueError):
        _native_reclaimer()(phase, root=tmp_path)
    assert (tmp_path/'sentinel').read_text() == 'owned'


@pytest.mark.parametrize('fault', ['missing', 'repeated', 'swapped', 'command', 'root-user',
    'exit', 'truncated', 'digest', 'negative-space', 'boolean-space', 'capacity-changed', 'wrong-path'])
def test_reclamation_completion_cannot_be_forged(fault):
    contract = plan()
    value = runtime.execute_runtime_plan(ReclaimObserve(), 'container', contract, {'BUILD_TESTS': 'ON'})
    assert value['complete'] is True
    rows = value['reclamations']; row = rows[0]
    if fault == 'missing': rows.pop()
    elif fault == 'repeated': rows[1] = deepcopy(rows[0])
    elif fault == 'swapped': rows.reverse()
    elif fault == 'command': row['argv'][-1] = 'source'
    elif fault == 'root-user': row['user'] = '0:0'
    elif fault == 'exit': row['exit_code'] = 1
    elif fault == 'truncated': row['output_truncated'] = True
    elif fault == 'digest': row['output_sha256'] = '0'*64
    else:
        payload = json.loads(base64.b64decode(row['output']))
        if fault == 'negative-space': payload['after']['available_bytes'] = -1
        elif fault == 'boolean-space': payload['after']['available_bytes'] = True
        elif fault == 'capacity-changed': payload['after']['capacity_bytes'] += 1
        elif fault == 'wrong-path': payload['removed'] = ['source']
        raw = json.dumps(payload).encode()
        row['output'] = base64.b64encode(raw).decode()
        row['output_sha256'] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        runtime.validate_runtime_evidence(value, contract, project_options={'BUILD_TESTS': 'ON'})


def test_legacy_v1_evidence_remains_readable_without_new_reclamation_claim():
    contract = plan()
    v2 = runtime.execute_runtime_plan(ReclaimObserve(), 'container', contract, {'BUILD_TESTS': 'ON'})
    legacy = deepcopy(v2)
    legacy['schema'] = 'nico.cpp-runtime-evidence.v1'
    del legacy['reclamations']
    proof = runtime.validate_runtime_evidence(legacy, contract, project_options={'BUILD_TESTS': 'ON'})
    assert proof['complete'] is True
    assert proof['native_evidence_sha256'] == runtime._digest(legacy)
    assert 'reclamation' not in json.dumps(proof)
