"""Owned transport faults prove abort/retention, not native Bitcoin execution."""
from copy import deepcopy
import pytest
import nico.assessment_cpp_runtime_execution as runtime
from tests.test_cpp_runtime_execution import Observe, plan
from tests.test_cpp_completed_sanitizer_failure_collection import CompletedTestFailure


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('fault', ['timeout', 'truncated', 'exit'])
@pytest.mark.parametrize('earlier_failure', [False, True])
def test_replay_fault_is_retained_and_stops_all_later_execution(index, fault, earlier_failure):
    parent = CompletedTestFailure if earlier_failure else Observe
    class Fault(parent):
        def __call__(self, key, argv, **kwargs):
            result = super().__call__(key, argv, **kwargs)
            if key == f'runtime-fuzz-replay-{index}':
                result.update({'timeout': {'timed_out': True, 'exit_code': 124},
                               'truncated': {'output_truncated': True},
                               'exit': {'exit_code': 1}}[fault])
            return result
    transport = Fault()
    value = runtime.execute_runtime_plan(transport, 'container', plan(), {'BUILD_TESTS': 'ON'})
    assert len(value['fuzz']['replays']) == index + 1
    assert 'runtime-fuzz-campaign' not in transport.calls
    assert f'runtime-fuzz-replay-{index+1}' not in transport.calls
    proof = runtime.validate_runtime_evidence(value, plan())
    assert proof['complete'] is False
    assert proof['failure_operation'] == f'runtime-fuzz-replay-{index}'
    assert proof['first_failure_operation'] == ('runtime-undefined-tests' if earlier_failure else proof['failure_operation'])
    assert proof['fuzz']['replay_count'] == index + 1
    assert proof['fuzz']['campaign_completed'] is False


def deadline_evidence(monkeypatch, replay_count, earlier_failure=False):
    clock = [0.0]
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: clock[0])
    original = runtime._run
    last = 'runtime-fuzz-build' if replay_count == 0 else f'runtime-fuzz-replay-{replay_count-1}'
    def run(*args, **kwargs):
        result = original(*args, **kwargs)
        if result['id'] == last:
            # Simulate scheduling delay between operations, after the last row
            # was measured. The real bounded observer rejects the next call.
            clock[0] = 6000.0
        return result
    monkeypatch.setattr(runtime, '_run', run)
    transport = CompletedTestFailure() if earlier_failure else Observe()
    value = runtime.execute_runtime_plan(transport, 'container', plan(), {'BUILD_TESTS': 'ON'})
    return value, transport


@pytest.mark.parametrize('replay_count', [0, 1, 2])
@pytest.mark.parametrize('earlier_failure', [False, True])
def test_real_shared_deadline_retains_exact_prefix_without_inventing_operation(monkeypatch, replay_count, earlier_failure):
    value, transport = deadline_evidence(monkeypatch, replay_count, earlier_failure)
    assert value['error'] == 'worker_runtime_deadline'
    assert len(value['fuzz']['replays']) == replay_count
    assert 'runtime-fuzz-campaign' not in transport.calls
    assert f'runtime-fuzz-replay-{replay_count}' not in transport.calls
    proof = runtime.validate_runtime_evidence(value, plan())
    assert proof['complete'] is False and proof['failure_operation'] is None
    assert proof['first_failure_operation'] == ('runtime-undefined-tests' if earlier_failure else None)
    assert proof['fuzz']['replay_count'] == replay_count
    assert proof['fuzz']['campaign_completed'] is False


@pytest.mark.parametrize('mutation', ['success', 'short_time', 'wrong_error', 'gap', 'order', 'digest', 'argv', 'legacy'])
def test_deadline_prefix_cannot_forge_completion_or_operation_identity(monkeypatch, mutation):
    value, _ = deadline_evidence(monkeypatch, 2)
    value = deepcopy(value)
    if mutation == 'success': value.update(complete=True, error=None)
    elif mutation == 'short_time': value['duration_ms'] = 5999999
    elif mutation == 'wrong_error': value['error'] = 'worker_runtime_deadline_exceeded'
    elif mutation == 'gap': value['fuzz']['replays'].pop(0)
    elif mutation == 'order': value['fuzz']['replays'].reverse()
    elif mutation == 'digest': value['fuzz']['replays'][0]['output_sha256'] = '0'*64
    elif mutation == 'argv': value['fuzz']['replays'][0]['argv'][-1] = '/work/unbound'
    elif mutation == 'legacy':
        value['schema'] = 'nico.cpp-runtime-evidence.v2'
        value.pop('failure_diagnostics')
    with pytest.raises(ValueError, match='worker_runtime_evidence_invalid'):
        runtime.validate_runtime_evidence(value, plan())


def test_campaign_timeout_retains_campaign_and_both_replays():
    class Fault(Observe):
        def __call__(self, key, argv, **kwargs):
            result = super().__call__(key, argv, **kwargs)
            if key == 'runtime-fuzz-campaign': result.update(timed_out=True, exit_code=124)
            return result
    value = runtime.execute_runtime_plan(Fault(), 'container', plan(), {'BUILD_TESTS': 'ON'})
    assert value['fuzz']['campaign']['timed_out'] is True
    proof = runtime.validate_runtime_evidence(value, plan())
    assert proof['complete'] is False and proof['fuzz']['replay_count'] == 2
    assert proof['fuzz']['campaign_completed'] is False
