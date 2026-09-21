from copy import deepcopy

import pytest

from nico.complete_assessment_gate_v1 import scanner_execution_summary
from tests.test_scanner_completion_gate import good, SHA, RUN


def summary(value):
    return scanner_execution_summary(value, expected_commit=SHA, expected_run=RUN)


def test_completed_stage_does_not_hide_missing_native_execution():
    data = good()
    data['repository_evidence'] = {'file_evidence': {'sampled_paths': ['package.json', 'src/index.ts']}}
    for item in data['requested_scanner_records']:
        if item['scanner_name'] in {'npm-audit', 'typescript'}:
            item.update(state='unavailable', completed=False, verified=False,
                        raw_artifact_retention_complete=False, raw_artifact_sha256='')
    before = deepcopy(data)
    result = summary(data)
    assert result['status'] == 'partial'
    assert result['completed_count'] == 7
    assert result['execution_required_count'] == 9
    assert result['percent'] == 78
    assert result['incomplete_tools'] == ['npm-audit', 'typescript']
    assert data == before


def test_valid_native_evidence_is_complete_without_approval_credit():
    result = summary(good())
    assert result['status'] == 'complete'
    assert result['applicable_count'] == 2  # exact Git snapshot establishes the two history scanners
    assert result['completed_count'] == result['execution_required_count'] == 9
    assert result['applicability_unproven_count'] == 7
    assert result['percent'] == 100
    assert result['human_approval_proven'] is False
    assert result['client_delivery_allowed'] is False


def retained_source_stage():
    # The source-text sample is JS/TS; the observed Python paths were excluded
    # from complexity measurement, not from scanner applicability.
    return {
        'stage_id': 'architecture_and_data_flow',
        'profile_coverage': {
            'version': 'nico.repository_profile_coverage.v1',
            'inventory_complete': True,
            'sampled_paths': ['pyproject.toml', 'requirements.txt', 'apps/web/package.json',
                              'apps/web/tsconfig.json', 'apps/web/app/page.tsx'],
            'complexity_excluded_paths': ['tests/test_widget.py'],
            'analyzed_source_files': 1,
            'eligible_source_files': 100,
        },
        'coverage_reconciliation': {
            'version': 'nico.report-coverage-reconciliation.v1',
            'assessed_commit': SHA,
        },
    }


@pytest.mark.parametrize('nested', [False, True])
def test_retained_report_source_inventory_preserves_applicability(nested):
    data = good()
    target = data.setdefault('assessment', {}) if nested else data
    target['stage_summaries'] = [retained_source_stage()]
    before = deepcopy(data)
    result = summary(data)
    assert result['applicable_count'] == 9
    assert result['applicability_unproven_count'] == 0
    assert result['completed_count'] == result['execution_required_count'] == 9
    assert result['human_approval_proven'] is False
    assert result['client_delivery_allowed'] is False
    assert data == before


@pytest.mark.parametrize('change', ['wrong_commit', 'missing_binding', 'wrong_profile_schema',
                                   'wrong_stage', 'prose_only', 'malformed_paths'])
def test_unbound_or_noninventory_report_paths_do_not_establish_applicability(change):
    data = good()
    stage = retained_source_stage()
    if change == 'wrong_commit':
        stage['coverage_reconciliation']['assessed_commit'] = 'c' * 40
    elif change == 'missing_binding':
        stage.pop('coverage_reconciliation')
    elif change == 'wrong_profile_schema':
        stage['profile_coverage']['version'] = 'unverified'
    elif change == 'wrong_stage':
        stage['stage_id'] = 'six_month_roadmap'
    elif change == 'prose_only':
        stage['recommendation'] = stage.pop('profile_coverage')
        stage['evidence'] = ['Add package.json, src/index.ts, and requirements.txt.']
    else:
        stage['profile_coverage']['sampled_paths'] = {'path': 'package.json'}
        stage['profile_coverage']['complexity_excluded_paths'] = [None, {'path': 'src/core.py'}]
    data['stage_summaries'] = [stage]
    result = summary(data)
    assert result['applicable_count'] == 2
    assert result['applicability_unproven_count'] == 7
    assert result['completed_count'] == 9


def test_source_inventory_does_not_grant_missing_execution_credit():
    data = good()
    data['stage_summaries'] = [retained_source_stage()]
    data['requested_scanner_records'][0].update(state='failed', completed=False, verified=False)
    result = summary(data)
    assert result['applicable_count'] == 9
    assert result['completed_count'] == 8
    assert result['status'] == 'partial'


@pytest.mark.parametrize('field,value', [('run_id', 'another_run'), ('commit_sha', 'c' * 40)])
def test_retained_source_paths_cannot_rebind_another_assessment(field, value):
    data = good()
    data['stage_summaries'] = [retained_source_stage()]
    data['identity'][field] = value
    result = summary(data)
    assert result['status'] == 'unknown'
    assert result['applicable_count'] == result['completed_count'] == 0


@pytest.mark.parametrize('change', [
    {'raw_artifact_sha256': ''}, {'raw_artifact_retention_complete': False},
    {'exact_commit_match': False}, {'commit_sha': 'c'*40}, {'timed_out': True},
    {'output_capture_complete': False}, {'run_id': 'another_run'},
])
def test_failed_record_cannot_receive_completed_count(change):
    data = good()
    data['requested_scanner_records'][0].update(change)
    result = summary(data)
    assert result['status'] == 'partial'
    assert result['completed_count'] == 8


def test_empty_or_wrong_source_never_claims_complete():
    assert summary({})['status'] == 'unknown'
    data = good()
    data['identity']['run_id'] = 'another_run'
    assert summary(data)['status'] == 'unknown'
    assert summary(data)['completed_count'] == 0


def test_verified_inapplicability_is_separate_from_completed():
    from tests.test_scanner_completion_gate import observed_no_packages
    data = good()
    item = next(r for r in data['requested_scanner_records'] if r['scanner_name'] == 'osv-scanner')
    item.update(state='not_applicable', applicable=False, completed=False, verified=False,
                applicability_reason='Complete exact-source package inventory has no inputs.',
                applicability_evidence=observed_no_packages())
    result = summary(data)
    assert result['status'] == 'complete'
    assert result['completed_count'] == result['execution_required_count'] == 8
    assert result['not_applicable_tools'] == ['osv-scanner']
    item['applicability_evidence']['inventory_complete'] = False
    result = summary(data)
    assert result['status'] == 'partial'
    assert result['execution_required_count'] == 9


def test_terminal_browser_response_uses_gate_and_preserves_record():
    from fastapi.testclient import TestClient
    from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
    from tests.test_comprehensive_mobile_recovery_v1 import _record, _app, BROWSER_PROJECTION_HEADER, BROWSER_PROJECTION_VALUE

    record = _record()
    report = record['stage_results']['final_comprehensive_report_generation']['report_package']
    records = good()['requested_scanner_records']
    for item in records:
        item.update(commit_sha=record['identity']['commit_sha'], run_id=record['identity']['run_id'])
    report['json']['requested_scanner_records'] = records
    records[-1].update(state='failed', verified=False)
    report['canonical_truth_sha256'] = canonical_sha256(report['json'])
    before = deepcopy(record)
    response = TestClient(_app(record)).get(
        '/assessment/comprehensive-run/' + record['identity']['run_id'],
        headers={BROWSER_PROJECTION_HEADER: BROWSER_PROJECTION_VALUE},
    )
    assert response.status_code == 200
    result = response.json()['scanner_execution_summary']
    assert result['status'] == 'partial'
    # This fixture retains report metadata only, without any native scan or bytes.
    assert result['completed_count'] == 0
    assert len(result['incomplete_tools']) == 9
    assert result['run_id'] == record['identity']['run_id']
    assert result['commit_sha'] == record['identity']['commit_sha']
    assert record == before
