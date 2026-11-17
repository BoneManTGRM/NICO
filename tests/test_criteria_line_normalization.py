from copy import deepcopy

from nico.report_valid_complexity_reconciliation import (
    STALE_INVALID_COMPLEXITY_FRAGMENTS, _remove_stale_invalid_lines,
)
from nico.v2_pipeline_adapter import _clean_criterion, _repair_client_criteria


def test_invalid_complexity_normalization_keeps_filtering_aliases_and_scores():
    keys = ('evidence', 'findings', 'unavailable', 'verified_claims', 'unverified_claims')
    cases = [None, False, 0, '', 'retained', ('retained',), {'retained': True},
             ['retained', None, False, 4, {'nested': True}]]
    for value in cases:
        section = {'score': 29, 'status': 'gray', **{key: deepcopy(value) for key in keys}}
        expected = deepcopy(section)
        for key in keys:
            original = expected[key] or []
            expected[key] = original if isinstance(original, list) else [original]
        _remove_stale_invalid_lines(section)
        assert section == expected
        _remove_stale_invalid_lines(section)
        assert section == expected
    for fragment in STALE_INVALID_COMPLEXITY_FRAGMENTS:
        original = ['retained', fragment.upper()]
        section = {key: original for key in keys}
        section['unrelated'] = original
        _remove_stale_invalid_lines(section)
        assert all(section[key] == ['retained'] for key in keys)
        assert section['unrelated'] is original
        assert original == ['retained', fragment.upper()]
    section = {'score': 29}
    _remove_stale_invalid_lines(section)
    assert section == {'score': 29, **{key: [] for key in keys}}


def test_acceptance_criteria_normalization_preserves_order_counts_and_copies():
    cases = [None, False, 0, '', 'Run the checks', ('ignored tuple',), {'ignored': True},
             ['Run the checks', 'run the checks', '', None, 0, {'nested': True}, 'Review evidence']]
    for value in cases:
        raw = {'id': 'finding-1', 'acceptance_criteria': deepcopy(value), 'nested': {'preserved': True}}
        canonical = {'canonical_findings': [None, 'ignored', raw], 'score': 29,
                     'v2_pipeline_contract': {'existing': 'retained'}}
        original = deepcopy(raw)
        values = value
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            values = []
        selected = {}
        for item in values:
            cleaned = _clean_criterion(item)
            if cleaned and cleaned.casefold() not in selected:
                selected[cleaned.casefold()] = cleaned
        expected = {**original, 'acceptance_criteria': list(selected.values())}
        _repair_client_criteria(canonical)
        surfaces = ('canonical_findings', 'findings_register', 'findings',
                    'decision_grade_findings_register', 'executive_risk_register', 'priority_findings')
        assert all(canonical[surface] == [expected] for surface in surfaces)
        assert raw == original
        assert canonical['score'] == 29
        assert canonical['v2_pipeline_contract'] == {
            'existing': 'retained', 'malformed_legacy_acceptance_metadata_repaired': True,
            'client_acceptance_criteria_count': len(selected)}
        once = deepcopy(canonical)
        _repair_client_criteria(canonical)
        assert canonical == once
        canonical['findings'][0]['nested']['preserved'] = False
        assert canonical['canonical_findings'][0]['nested']['preserved'] is True
        assert raw['nested']['preserved'] is True


def test_acceptance_criteria_normalization_preserves_register_limits():
    canonical = {'canonical_findings': [{'id': str(i), 'acceptance_criteria': 'Review evidence'} for i in range(9)]}
    _repair_client_criteria(canonical)
    assert len(canonical['canonical_findings']) == 9
    assert canonical['executive_risk_register'] == canonical['canonical_findings'][:7]
    assert canonical['priority_findings'] == canonical['canonical_findings'][:5]
    assert canonical['v2_pipeline_contract']['client_acceptance_criteria_count'] == 9
