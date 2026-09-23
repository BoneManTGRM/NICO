"""Regression tests for evidence retention and the bounded native CI schedule."""
from pathlib import Path
import json
import os
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TEST_FILES = {
    'tests/test_cpp_fixture_tree.py', 'tests/test_cpp_bounded_fuzz.py',
    'tests/test_cpp_fuzz_tool_provisioning.py', 'tests/test_cpp_generated_context.py',
    'tests/test_cpp_combined_configuration.py', 'tests/test_cpp_compiler_evidence.py',
    'tests/test_assessment_cpp_full_project.py', 'tests/test_cpp_analysis_phase_boundary.py',
    'tests/test_cpp_native_test_binding.py', 'tests/test_assessment_worker_capacity_v1.py',
    'tests/test_cpp_fuzz_workspace.py', 'tests/test_cpp_native_test_timing.py',
    'tests/test_assessment_worker_archive.py',
}


def test_contract_tests_do_not_consume_the_native_job_execution_budget():
    workflow = yaml.safe_load((ROOT / '.github/workflows/cpp-full-project-integration.yml').read_text())
    assert workflow['permissions'] == {'contents': 'read'}
    jobs = workflow['jobs']
    regression = jobs['contract-regressions']
    native = jobs['owned-project-integration']
    assert native['needs'] == ['contract-regressions']
    assert all(jobs[name]['timeout-minutes'] == 5 for name in (
        'contract-regressions', 'owned-project-integration', 'exact-source', 'llvm-toolchain-inventory'))
    assert set(jobs) == {'contract-regressions', 'owned-project-integration', 'exact-source',
                         'llvm-toolchain-inventory', 'project-baseline-qualification'}
    assert jobs['project-baseline-qualification']['timeout-minutes'] == 40
    assert 'if' not in native and native.get('continue-on-error', False) is False
    assert 'services' not in regression
    commands = '\n'.join(step.get('run', '') for step in regression['steps'])
    for test in REQUIRED_TEST_FILES:
        assert test in commands
    assert ' -k ' not in commands and '|| true' not in commands
    native_commands = '\n'.join(step.get('run', '') for step in native['steps'])
    assert 'pytest' not in native_commands
    assert '--generated-headers --bounded-fuzz' in native_commands
    assert 'docker build --network=none' in native_commands
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
