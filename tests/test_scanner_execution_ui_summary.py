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
    assert result['applicable_count'] == 9
    assert result['percent'] == 78
    assert result['incomplete_tools'] == ['npm-audit', 'typescript']
    assert data == before


def test_valid_native_evidence_is_complete_without_approval_credit():
    result = summary(good())
    assert result['status'] == 'complete'
    assert result['completed_count'] == result['applicable_count'] == 9
    assert result['percent'] == 100
    assert result['human_approval_proven'] is False
    assert result['client_delivery_allowed'] is False


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
    assert result['completed_count'] == result['applicable_count'] == 8
    assert result['not_applicable_tools'] == ['osv-scanner']
    item['applicability_evidence']['inventory_complete'] = False
    result = summary(data)
    assert result['status'] == 'partial'
    assert result['applicable_count'] == 9


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
