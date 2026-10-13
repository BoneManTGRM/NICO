"""Regression tests for evidence retention and the bounded native CI schedule."""
from pathlib import Path
import json
import os
import subprocess
import sys

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_REF = 'refs/pull/1722/merge'
FULL_GROUP = 'cpp-full-project-integration-${{ github.ref }}'
DIAGNOSTIC_GROUP = 'cpp-full-project-integration-' + PRODUCER_REF
REQUIRED_TEST_FILES = {
    'tests/test_cpp_fixture_tree.py', 'tests/test_cpp_bounded_fuzz.py',
    'tests/test_cpp_fuzz_tool_provisioning.py', 'tests/test_cpp_generated_context.py',
    'tests/test_cpp_combined_configuration.py', 'tests/test_cpp_compiler_evidence.py',
    'tests/test_assessment_cpp_full_project.py', 'tests/test_cpp_analysis_phase_boundary.py',
    'tests/test_cpp_native_test_binding.py', 'tests/test_assessment_worker_capacity_v1.py',
    'tests/test_cpp_fuzz_workspace.py', 'tests/test_cpp_native_test_timing.py',
    'tests/test_assessment_worker_archive.py', 'tests/test_cpp_qualification_failure_diagnostics.py',
}


def test_contract_tests_do_not_consume_the_native_job_execution_budget():
    workflow = yaml.safe_load((ROOT / '.github/workflows/cpp-full-project-integration.yml').read_text())
    assert workflow['permissions'] == {'contents': 'read'}
    jobs = workflow['jobs']
    regression = jobs['contract-regressions']
    native = jobs['owned-project-integration']
    assert native['needs'] == ['contract-regressions']
    assert native['timeout-minutes'] == 10
    assert all(jobs[name]['timeout-minutes'] == 5 for name in (
        'contract-regressions', 'exact-source', 'llvm-toolchain-inventory'))
    assert set(jobs) == {'contract-regressions', 'owned-project-integration', 'exact-source',
                         'llvm-toolchain-inventory', 'project-baseline-qualification'}
    assert jobs['project-baseline-qualification']['timeout-minutes'] == 155
    assert 'if' not in native and native.get('continue-on-error', False) is False
    assert 'services' not in regression
    commands = '\n'.join(step.get('run', '') for step in regression['steps'])
    for test in REQUIRED_TEST_FILES:
        assert test in commands
    assert ' -k ' not in commands and '|| true' not in commands
    native_commands = '\n'.join(step.get('run', '') for step in native['steps'])
    assert 'pytest' not in native_commands
    assert '--generated-headers --bounded-fuzz' in native_commands
    assert 'timeout 210s docker build --network=none' in native_commands
    assert 'services' in native and native['services']['postgres']
    assert not any(s.get('continue-on-error') for job in jobs.values() for s in job['steps'])


def test_hard_interruption_retains_unproven_attempt_and_never_implies_execution(tmp_path):
    output = tmp_path / 'interrupted-control'
    # Abrupt exit models a CI cancellation where finally/atexit cannot run.
    # Stop before consume_control can acquire a job or launch any target code.
    program = """
import os, sys
from scripts import qualify_cpp_full_project_integration as control
control.consume_control = lambda *args, **kwargs: os._exit(71)
sys.argv = ['owned-control', '--image', 'sha256:' + 'd' * 64,
            '--generated-headers', '--bounded-fuzz', '--output', sys.argv[1]]
control.main()
"""
    result = subprocess.run([sys.executable, '-c', program, str(output)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
    assert result.returncode == 71, result.stderr.decode(errors='replace')
    evidence = json.loads((output / 'receipt.json').read_bytes())
    assert evidence['status'] == 'UNPROVEN'
    assert evidence['stage'] == 'control_requested'
    assert evidence['active_control_negative'] is False
    assert evidence['controls'] == [] and evidence['reports'] == []
    assert evidence['synthetic_issuer'] is True
    assert evidence['production_qualified'] is False and evidence['bitcoin_executed'] is False
    assert not list(output.glob('*.tmp'))


def test_native_result_is_retained_before_persistence_lookup_can_be_interrupted(tmp_path):
    output = tmp_path / 'returned-control'
    program = """
import os, sys
from scripts import qualify_cpp_full_project_integration as control
from nico import scanner_worker
control.consume_control = lambda *args, **kwargs: {
    'receipt': {'synthetic_retention_test': True},
    'canonical_record': {'scan_id': 'synthetic-scan'}}
scanner_worker.get_scan = lambda *args, **kwargs: os._exit(72)
sys.argv = ['owned-control', '--image', 'sha256:' + 'd' * 64,
            '--generated-headers', '--bounded-fuzz', '--output', sys.argv[1]]
control.main()
"""
    result = subprocess.run([sys.executable, '-c', program, str(output)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
    assert result.returncode == 72, result.stderr.decode(errors='replace')
    evidence = json.loads((output / 'receipt.json').read_bytes())
    assert evidence['stage'] == 'native_receipt_returned'
    assert evidence['status'] == 'UNPROVEN'
    assert evidence['controls'][0]['receipt'] == {'synthetic_retention_test': True}
    assert 'persisted_record' not in evidence['controls'][0]
    assert evidence['reports'] == [] and evidence['production_qualified'] is False


@pytest.mark.parametrize("filename", [
    "cpp-full-project-integration.yml", "native-timeout-diagnostic.yml",
])
def test_pending_native_workflows_are_queued_without_replacing_each_other(filename):
    # cancel-in-progress=false protects a running job, NOT the default pending slot.
    # Both participants must opt into GitHub's FIFO queue to preserve diagnostics.
    workflow = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
    concurrency = workflow["concurrency"]
    assert concurrency.get("queue") == "max", "pending native evidence can be cancelled"
    assert concurrency["cancel-in-progress"] is False
    expected = FULL_GROUP if filename == 'cpp-full-project-integration.yml' else DIAGNOSTIC_GROUP
    assert concurrency == {'group': expected, 'queue': 'max', 'cancel-in-progress': False}


def _native_workflows():
    directory = ROOT / ".github/workflows"
    full = yaml.safe_load((directory / "cpp-full-project-integration.yml").read_text())
    diagnostic = yaml.safe_load((directory / "native-timeout-diagnostic.yml").read_text())
    return full, diagnostic


def _assert_native_schedule(full, diagnostic):
    assert full['concurrency'] == {'group': FULL_GROUP, 'queue': 'max', 'cancel-in-progress': False}
    assert diagnostic['concurrency'] == {'group': DIAGNOSTIC_GROUP, 'queue': 'max', 'cancel-in-progress': False}
    # This stacked PR has its own github.ref. Its fixed lock must equal the
    # full workflow's evaluated lock for the producer PR, not its own PR ref.
    assert full['concurrency']['group'].replace('${{ github.ref }}', PRODUCER_REF) == diagnostic['concurrency']['group']
    assert full["permissions"] == {"contents": "read"}
    assert diagnostic["permissions"] == {"contents": "read", "actions": "read"}
    assert full["jobs"]["project-baseline-qualification"]["timeout-minutes"] == 155
    isolated = diagnostic["jobs"]["isolated-diagnostic"]
    assert isolated["timeout-minutes"] == 55
    assert isolated['if'] == (
        "github.event.pull_request.head.repo.full_name == github.repository && "
        "github.event.pull_request.head.ref == 'diagnostic/current-primary-38380333159' && "
        "github.event.pull_request.base.ref == 'repair/ast-boundary-independent-fc9a0a75-20261012'")
    assert isolated.get('continue-on-error', False) is False
    assert not any(step.get('continue-on-error', False) for step in isolated['steps'])
    guard = next(step for step in isolated["steps"] if step.get("id") == "need")
    assert 'gh api repos/BoneManTGRM/NICO/actions/runs/38380333159 > native-diagnostic-evidence/predecessor.json' in guard['run']
    assert 'test "$(jq -r .head_sha native-diagnostic-evidence/predecessor.json)" = 2bd1ea9dac2d38b721661eab68a26ef7d9747e33' in guard['run']
    assert 'test "$status" = completed' in guard["run"]
    assert "success) echo 'required=false'" in guard["run"]
    assert "failure) echo 'required=true'" in guard["run"]


def test_native_queue_remains_serial_and_preserves_existing_execution_boundaries():
    _assert_native_schedule(*_native_workflows())


@pytest.mark.parametrize('fault', [
    'wrong_producer', 'own_pr_lock', 'full_lock', 'full_queue', 'diagnostic_queue',
    'full_cancel', 'diagnostic_cancel', 'permissions', 'full_budget', 'diagnostic_budget',
    'repository_guard', 'head_guard', 'base_guard', 'producer_run', 'producer_head',
    'completed_guard', 'continue_job', 'continue_step',
])
def test_native_schedule_rejects_wrong_lock_or_weakened_boundaries(fault):
    full, diagnostic = _native_workflows()
    isolated = diagnostic['jobs']['isolated-diagnostic']
    guard = next(step for step in isolated['steps'] if step.get('id') == 'need')
    if fault == 'wrong_producer': diagnostic['concurrency']['group'] = DIAGNOSTIC_GROUP.replace('1722', '1727')
    elif fault == 'own_pr_lock': diagnostic['concurrency']['group'] = FULL_GROUP
    elif fault == 'full_lock': full['concurrency']['group'] = 'unshared'
    elif fault == 'full_queue': full['concurrency'].pop('queue')
    elif fault == 'diagnostic_queue': diagnostic['concurrency']['queue'] = 'single'
    elif fault == 'full_cancel': full['concurrency']['cancel-in-progress'] = True
    elif fault == 'diagnostic_cancel': diagnostic['concurrency']['cancel-in-progress'] = True
    elif fault == 'permissions': diagnostic['permissions']['contents'] = 'write'
    elif fault == 'full_budget': full['jobs']['project-baseline-qualification']['timeout-minutes'] += 1
    elif fault == 'diagnostic_budget': isolated['timeout-minutes'] += 1
    elif fault == 'repository_guard': isolated['if'] = isolated['if'].replace('head.repo.full_name == github.repository', 'head.repo.full_name != github.repository')
    elif fault == 'head_guard': isolated['if'] = isolated['if'].replace('diagnostic/current-primary-38380333159', 'unreviewed')
    elif fault == 'base_guard': isolated['if'] = isolated['if'].replace('repair/ast-boundary-independent-fc9a0a75-20261012', 'main')
    elif fault == 'producer_run': guard['run'] = guard['run'].replace('38380333159', '38403144843')
    elif fault == 'producer_head': guard['run'] = guard['run'].replace('2bd1ea9dac2d38b721661eab68a26ef7d9747e33', '0'*40)
    elif fault == 'completed_guard': guard['run'] = guard['run'].replace('test "$status" = completed', 'true')
    elif fault == 'continue_job': isolated['continue-on-error'] = True
    elif fault == 'continue_step': guard['continue-on-error'] = True
    with pytest.raises(AssertionError):
        _assert_native_schedule(full, diagnostic)
