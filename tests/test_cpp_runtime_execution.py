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
        if key=='runtime-functional-results':
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
