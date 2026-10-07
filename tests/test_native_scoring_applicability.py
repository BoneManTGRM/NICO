"""Source-bound inapplicability affects obligations, never execution credit."""
from copy import deepcopy
import pytest

from nico import comprehensive_native_providers_v4 as scoring
from nico.node_scanner_applicability_v1 import inspect_node_inputs
from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical

SHA = 'a' * 40

def absent_scan(tmp_path):
    inventory = inspect_node_inputs(tmp_path, SHA)
    canonical = normalize_scanner_applicability_canonical({
        'identity': {'commit_sha': SHA},
        'requested_scanner_records': [{'scanner_name': 'typescript', 'commit_sha': SHA,
            'status': 'not_applicable', 'execution_observed_for_this_report': False,
            'applicability_evidence': inventory}],
    })
    return {'actual_commit_sha': SHA, 'scanner_results': canonical['requested_scanner_records']}

def static(scan):
    return scoring._scanner_section('static', 'Static', scan, ('typescript',),
        summary='Owned applicability control', material_weight=16, material_cap=64)

def test_proven_absence_has_no_incomplete_applicable_penalty_or_execution_credit(tmp_path):
    scan = absent_scan(tmp_path)
    before = deepcopy(scan)
    assert scan['scanner_results'][0]['applicable'] is False
    assert scoring._tool_complete(scan['scanner_results'][0]) is False
    assert scoring._incomplete_tools(scan, ('typescript',)) == []
    assert static(scan)['presented_score'] == 96
    assert scan == before
    assert static(scan) == static(scan)

@pytest.mark.parametrize('change', ['missing_inventory', 'wrong_commit', 'asserted_flags', 'positive_source',
                                   'stale_scan', 'missing_target', 'wrong_context'])
def test_unproven_or_conflicting_absence_keeps_penalty(tmp_path, change):
    scan = absent_scan(tmp_path);record = scan['scanner_results'][0]
    if change == 'missing_inventory': record.pop('applicability_evidence')
    if change == 'wrong_commit': record['commit_sha'] = 'b' * 40
    if change == 'asserted_flags': record.clear();record.update(scanner_name='typescript', applicable=False, evidence_required=False)
    if change == 'positive_source': scan['repository'] = {'files': ['src/main.ts']}
    if change == 'stale_scan': scan['actual_commit_sha'] = 'b' * 40
    if change == 'missing_target': scan.pop('actual_commit_sha')
    if change == 'wrong_context': scan['_scoring_target_commit_sha'] = 'b' * 40
    assert scoring._incomplete_tools(scan, ('typescript',)) == ['typescript']
    assert static(scan)['presented_score'] == 88

def test_missing_timeout_and_failed_evidence_remain_incomplete():
    for status in ('timed_out', 'failed', 'malformed', 'unauthenticated'):
        scan = {'scanner_results': [{'scanner_name': 'typescript', 'status': status}]}
        assert scoring._incomplete_tools(scan, ('typescript',)) == ['typescript']
    assert scoring._incomplete_tools({}, ('typescript',)) == ['typescript']

def test_provider_coverage_counts_only_completed_required_tools(tmp_path, monkeypatch):
    scan = absent_scan(tmp_path)
    scan['scanner_results'].extend({'scanner_name': tool, 'status': 'completed',
        'completed': True, 'verified': True, 'exact_commit_match': True,
        'raw_artifact_retention_complete': True, 'commit_sha': SHA}
        for tool in scoring._ALL_TOOLS if tool != 'typescript')
    baseline = {'status': 'complete', 'assessment': {'sections': []}}
    monkeypatch.setattr(scoring.v3, 'canonical_scoring_provider', lambda context: deepcopy(baseline))
    monkeypatch.setattr(scoring.legacy, '_scan', lambda context: deepcopy(scan))
    monkeypatch.setattr(scoring.legacy, '_repo', lambda context: {})
    result = scoring.canonical_scoring_provider({'commit_sha': SHA, 'repository': 'owned/control',
        'run_id': 'owned-scoring', 'evidence_ledger_id': 'owned-ledger', 'customer_id': 'owned', 'project_id': 'owned'})
    coverage = result['assessment']['evidence_coverage']
    assert coverage['not_applicable_analyzers'] == ['typescript']
    assert 'typescript' not in coverage['completed_analyzers']
    assert 'typescript' not in coverage['required_analyzers']
    assert len(coverage['completed_analyzers']) == len(coverage['required_analyzers']) == 8
    assert coverage['percent'] == 100
    assert coverage['incomplete_analyzers'] == []
    assert coverage['not_applicable_receives_completion_credit'] is False
