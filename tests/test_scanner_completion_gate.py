from __future__ import annotations
from copy import deepcopy
import pytest
from nico.complete_assessment_gate_v1 import REQUIRED_TOOLS, complete_assessment_evidence, require_complete_assessment
SHA = 'a' * 40
RUN = 'comprun_scanner_gate_test'


def good():
    return {'identity': {'commit_sha': SHA, 'run_id': RUN}, 'requested_scanner_records': [
        {'scanner_name': name, 'commit_sha': SHA, 'run_id': RUN, 'state': 'completed',
         'exact_commit_match': True, 'completed': True, 'verified': True,
         'raw_artifact_retention_complete': True, 'raw_artifact_sha256': 'b'*64}
        for name in REQUIRED_TOOLS]}


def check(value):
    return complete_assessment_evidence(value, expected_commit=SHA, expected_run=RUN)


def test_complete_execution_is_not_human_approval_or_clean_claim():
    result = require_complete_assessment(good(), expected_commit=SHA, expected_run=RUN)
    assert result['passed'] and len(result['completed_tools']) == 9
    assert result['client_delivery_allowed'] is False
    assert result['human_approval_proven'] is False
    assert result['no_vulnerabilities_claimed'] is False


@pytest.mark.parametrize('state', ['failed', 'timeout', 'queued', 'running', 'missing', 'unavailable', 'malformed', ''])
def test_renderable_report_with_an_incomplete_scanner_fails(state):
    data = good(); data['pdf_available'] = True
    data['requested_scanner_records'][-1]['state'] = state
    assert check(data)['passed'] is False


@pytest.mark.parametrize('change', [
    {'raw_artifact_retention_complete': False}, {'raw_artifact_sha256': ''},
    {'verified': False}, {'commit_sha': 'c'*40}, {'run_id': 'another_run'},
    {'exact_commit_match': False}, {'output_capture_complete': False}, {'timed_out': True},
    {'returncode_valid': False}, {'applicable': False},
])
def test_incomplete_or_contradictory_evidence_cannot_be_promoted(change):
    data = good(); data['requested_scanner_records'][0].update(change)
    assert not check(data)['passed']


def test_missing_and_duplicate_records_fail():
    data = good(); data['requested_scanner_records'].pop()
    assert not check(data)['passed']
    data = good(); data['requested_scanner_records'].append(deepcopy(data['requested_scanner_records'][0]))
    assert not check(data)['passed']
    assert not check({'identity': {'run_id': RUN, 'commit_sha': SHA}})['passed']


def test_observed_no_package_sources_is_not_completed():
    data = good(); rec = next(r for r in data['requested_scanner_records'] if r['scanner_name'] == 'osv-scanner')
    rec.update(state='not_applicable', applicable=False, completed=False, verified=False,
               applicability_reason='No declared package sources at the inspected revision.',
               applicability_evidence={'schema': 'nico.osv-package-inventory.v1',
                  'inventory_complete': True, 'no_declared_package_sources': True,
                  'package_source_paths': [], 'inventory_sha256': 'c'*64})
    result = check(data)
    assert result['passed'] and len(result['completed_tools']) == 8
    assert result['not_applicable_tools'] == ['osv-scanner']
    rec['applicability_evidence']['package_source_paths'] = ['Gemfile']
    assert not check(data)['passed']
