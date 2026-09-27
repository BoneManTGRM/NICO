"""A retained target-test failure must stay failed while independent checks run.

The native transport is substituted here. These tests are not Bitcoin execution
or evidence that qualification should accept a failing target as clean.
"""
from copy import deepcopy
import base64
import hashlib
import json

import pytest

from nico.assessment_cpp_runtime_execution import execute_runtime_plan, validate_runtime_evidence
from tests.test_cpp_runtime_execution import Observe, plan


def envelope(raw: bytes) -> bytes:
    return json.dumps({'data': base64.b64encode(raw).decode(), 'truncated': False}).encode()


class CompletedTestFailure(Observe):
    def __init__(self, kind='undefined', *, message='Failed', later_fault=None, transport_timeout=False):
        super().__init__(later_fault)
        self.kind, self.message, self.transport_timeout = kind, message, transport_timeout

    def __call__(self, key, argv, **kwargs):
        result = super().__call__(key, argv, **kwargs)
        prefix = 'runtime-' + self.kind
        if key == prefix + '-tests':
            result.update(exit_code=8, timed_out=self.transport_timeout)
        elif key == prefix + '-junit':
            result['output'] = envelope((
                '<testsuite tests="1" failures="1"><testcase name="unit_a" status="fail">'
                f'<failure message="{self.message}"/></testcase></testsuite>'
            ).encode())
        elif key == prefix + '-test-log':
            result['output'] = envelope(b'Owned target failed its test; no production run represented.\n')
        elif key == prefix + '-resources':
            result['output'] = json.dumps({
                'memory_current_bytes':None, 'memory_peak_bytes':None, 'memory_events':None,
                'scratch_capacity_bytes':None, 'scratch_available_bytes':None,
            }).encode()
        return result


@pytest.mark.parametrize('kind', ['address', 'undefined'])
def test_completed_target_failure_collects_later_checks_without_granting_success(kind):
    transport = CompletedTestFailure(kind)
    contract = plan()
    evidence = execute_runtime_plan(transport, 'container', contract, {'BUILD_TESTS':'ON'})
    assert 'runtime-fuzz-campaign' in transport.calls, 'target finding stopped independent checks'
    assert evidence['complete'] is False
    assert evidence['error'] == 'worker_runtime_sanitizer_failed'
    assert evidence['schema'] == 'nico.cpp-runtime-evidence.v4'
    proof = validate_runtime_evidence(evidence, contract, project_options={'BUILD_TESTS':'ON'})
    assert proof['complete'] is False
    assert proof['first_failure_operation'] == 'runtime-' + kind + '-tests'
    failed = next(row for row in proof['sanitizers'] if row['kind'] == kind)
    assert failed['executed'] == ['unit_a'] and failed['passed'] == []
    assert failed['state'] == 'failed'
    assert proof['fuzz']['replay_count'] == 2 and proof['fuzz']['campaign_completed'] is True
    assert [row['kind'] for row in proof['failure_diagnostics']] == [kind]


def test_later_build_failure_retains_both_original_test_failure_and_abort_reason():
    transport = CompletedTestFailure(later_fault='runtime-fuzz-build')
    contract = plan()
    evidence = execute_runtime_plan(transport,'container',contract,{'BUILD_TESTS':'ON'})
    assert 'runtime-fuzz-build' in transport.calls
    assert 'runtime-fuzz-campaign' not in transport.calls
    assert evidence['complete'] is False and evidence['error'] == 'worker_runtime_fuzz_failed'
    proof = validate_runtime_evidence(evidence,contract,project_options={'BUILD_TESTS':'ON'})
    assert proof['first_failure_operation'] == 'runtime-undefined-tests'
    assert proof['failure_operation'] == 'runtime-fuzz-build'
    assert proof['sanitizers'][1]['passed'] == []
    assert proof['fuzz']['state'] == 'failed'


@pytest.mark.parametrize('message,transport_timeout', [('Timeout',False),('Failed',True),('Not Run',False)])
def test_incomplete_or_timed_out_test_execution_still_aborts(message,transport_timeout):
    transport = CompletedTestFailure(message=message,transport_timeout=transport_timeout)
    evidence=execute_runtime_plan(transport,'container',plan(),{'BUILD_TESTS':'ON'})
    assert evidence['complete'] is False
    assert 'runtime-fuzz-corpus-stage' not in transport.calls
    proof=validate_runtime_evidence(evidence,plan(),project_options={'BUILD_TESTS':'ON'})
    assert proof['complete'] is False
    assert proof['fuzz']['state'] == 'not_executed'


@pytest.mark.parametrize('mutation',['success','erase_error','erase_diagnostics','zero_exit','claim_pass','drop_fuzz','relabel_v3'])
def test_failed_complete_collection_cannot_be_promoted_or_relabelled(mutation):
    contract=plan();evidence=execute_runtime_plan(CompletedTestFailure(),'container',contract,{'BUILD_TESTS':'ON'})
    assert evidence.get('fuzz') is not None
    value=deepcopy(evidence)
    if mutation=='success':value['complete']=True;value['error']=None
    elif mutation=='erase_error':value['error']=None
    elif mutation=='erase_diagnostics':value['failure_diagnostics']=[]
    elif mutation=='zero_exit':value['sanitizers'][1]['tests']['exit_code']=0
    elif mutation=='claim_pass':value['sanitizers'][1]['results']['passed']=['unit_a']
    elif mutation=='drop_fuzz':value['fuzz']=None
    elif mutation=='relabel_v3':value['schema']='nico.cpp-runtime-evidence.v3'
    with pytest.raises(ValueError,match='worker_runtime_evidence_invalid'):
        validate_runtime_evidence(value,contract,project_options={'BUILD_TESTS':'ON'})


def test_legacy_no_diagnostic_policy_keeps_failure_prefix_semantics():
    transport=CompletedTestFailure()
    evidence=execute_runtime_plan(transport,'container',plan(),{'BUILD_TESTS':'ON'},capture_failure_diagnostics=False)
    assert evidence['schema']=='nico.cpp-runtime-evidence.v2'
    assert 'runtime-fuzz-build' not in transport.calls
    assert validate_runtime_evidence(evidence,plan(),project_options={'BUILD_TESTS':'ON'})['complete'] is False


@pytest.mark.parametrize('later_fault',[None,'runtime-fuzz-build','runtime-fuzz-campaign'])
def test_optional_log_unavailability_does_not_erase_failed_test_or_later_outcome(later_fault):
    class MissingDiagnostic(CompletedTestFailure):
        def __call__(self,key,argv,**kwargs):
            result=super().__call__(key,argv,**kwargs)
            if key=='runtime-undefined-test-log':
                result.update(exit_code=1,output=b'log not retained')
            return result
    evidence=execute_runtime_plan(MissingDiagnostic(later_fault=later_fault),'container',plan(),{'BUILD_TESTS':'ON'})
    proof=validate_runtime_evidence(evidence,plan(),project_options={'BUILD_TESTS':'ON'})
    assert proof['first_failure_operation']=='runtime-undefined-tests'
    assert proof['complete'] is False
    assert proof['failure_diagnostics'][0]['log']['state']=='unavailable'
    if later_fault=='runtime-fuzz-build':
        assert proof['failure_operation']==later_fault
    else:
        assert proof['fuzz']['replay_count']==2
        assert proof['fuzz']['campaign_completed'] is (later_fault is None)


@pytest.mark.parametrize('bad_xml',[
    b'<testsuite tests="0"></testsuite>',
    b'<testsuite tests="1"><testcase name="unit_a"><skipped/></testcase></testsuite>',
    b'<testsuite tests="1"><testcase name="unit_a"><error message="Failed"/></testcase></testsuite>',
    b'<testsuite tests="1"><testcase name="unit_a" status="fail"/></testsuite>',
])
def test_unproven_or_missing_test_results_do_not_enable_suffix_execution(bad_xml):
    class BadResults(CompletedTestFailure):
        def __call__(self,key,argv,**kwargs):
            result=super().__call__(key,argv,**kwargs)
            if key=='runtime-undefined-junit':result['output']=envelope(bad_xml)
            return result
    transport=BadResults()
    evidence=execute_runtime_plan(transport,'container',plan(),{'BUILD_TESTS':'ON'})
    assert evidence['complete'] is False
    assert 'runtime-fuzz-corpus-stage' not in transport.calls


def test_fuzz_only_failure_still_identifies_the_actual_first_failure():
    evidence=execute_runtime_plan(Observe('runtime-fuzz-campaign'),'container',plan(),{'BUILD_TESTS':'ON'})
    proof=validate_runtime_evidence(evidence,plan(),project_options={'BUILD_TESTS':'ON'})
    assert proof['complete'] is False
    assert proof['first_failure_operation']=='runtime-fuzz-campaign'
