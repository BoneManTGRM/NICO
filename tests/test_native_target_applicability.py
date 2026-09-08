from copy import deepcopy
from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical as normalize


def source(prior=False, exact=True, count=1):
    return {'scanner_execution_records': [
        {'scanner_name': 'eslint', 'completed': True, 'state': 'completed',
         'exact_commit_match': exact, 'execution_provenance': {'coverage': {
             'status': 'reported_native_targets', 'reported_target_count': count}}},
        {'scanner_name': 'npm-audit', 'completed': False,
         'state': 'not_applicable' if prior else 'unavailable',
         'failure_reason': 'No package-lock.json with an adjacent package.json was found.'}
    ]}


def test_native_eslint_targets_prevent_missing_lockfile_from_hiding_npm_audit():
    value = source()
    before = deepcopy(value)
    result = normalize(value)
    assert not result['not_applicable_scanner_records']
    npm = result['scanner_execution_records'][1]
    assert npm['state'] == 'unavailable' and npm['completed'] is False
    assert value == before


def test_positive_target_evidence_corrects_a_stale_inapplicable_projection():
    value = source(prior=True)
    before = deepcopy(value)
    result = normalize(value)
    npm = result['scanner_execution_records'][1]
    assert npm['state'] == 'unavailable' and npm['applicable'] is True
    assert npm['verified'] is False and npm['evidence_required'] is True
    assert npm['prior_applicability_reason']
    assert normalize(result)['scanner_execution_records'] == result['scanner_execution_records']
    assert value == before


def test_unverified_or_empty_target_evidence_does_not_invent_node_sources():
    for value in (source(exact=False), source(count=0)):
        result = normalize(value)
        assert result['assessment']['scanner_applicability_summary']['repository_signals']['node_source'] is False
