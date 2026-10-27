"""Synthetic retained scanner populations; no private report or score changes."""
from copy import deepcopy
import io

import pytest
from pypdf import PdfReader

from nico.client_report_completion_v1 import scanner_provenance_markdown, _provenance_pdf
from nico.comprehensive_authoritative_scanner_truth_v62 import reconcile_authoritative_scanner_truth
from tests.test_analyzer_not_applicable_execution_credit import canonical_na


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('shape', ['full', 'requested_root', 'requested_assessment', 'unsplit_execution', 'split_only'])
def test_retained_provenance_keeps_authoritative_exclusion_and_no_execution_credit(tmp_path, spanish, shape):
    canonical = reconcile_authoritative_scanner_truth(canonical_na(tmp_path))
    assert len(canonical['not_applicable_scanner_records']) == 1
    rows = deepcopy(canonical['requested_scanner_records'])
    if shape != 'full':
        for owner in (canonical, canonical['assessment']):
            for key in ('requested_scanner_records', 'scanner_execution_records', 'not_applicable_scanner_records'):
                owner.pop(key, None)
        if shape == 'requested_root':
            canonical['requested_scanner_records'] = rows
        elif shape == 'requested_assessment':
            canonical['assessment']['requested_scanner_records'] = rows
        elif shape == 'unsplit_execution':
            canonical['scanner_execution_records'] = rows
        else:
            canonical['not_applicable_scanner_records'] = rows
    before = deepcopy(canonical)
    markdown = scanner_provenance_markdown(canonical, spanish=spanish)
    pdf = _provenance_pdf(canonical, spanish=spanish)
    extracted = ' '.join((page.extract_text() or '') for page in PdfReader(io.BytesIO(pdf)).pages)
    expected = (['Analizadores solicitados: 1', 'No aplicables: 1',
                 'Ejecuciones requeridas completadas: 0', 'Ejecuciones requeridas incompletas: 0']
                if spanish else ['Requested analyzers: 1', 'Not-applicable analyzers: 1',
                                 'Completed required executions: 0', 'Incomplete required executions: 0'])
    for literal in expected:
        assert literal in markdown
        assert literal in extracted
    assert 'pip-audit' in markdown and 'pip-audit' in extracted
    assert rows[0]['applicability_reason'] in markdown
    assert canonical == before  # Includes scores, evidence, lifecycle and raw records.


def test_requested_population_overrides_stale_split_aliases_without_granting_credit():
    canonical = {'requested_scanner_records': [
        {'scanner_name': 'unproven', 'applicable': None, 'completed': False},
        {'scanner_name': 'excluded', 'applicable': False, 'completed': True,
         'applicability_reason': 'Retained exclusion reason.'},
    ], 'scanner_execution_records': [{'scanner_name': 'stale', 'applicable': True, 'completed': True}],
        'not_applicable_scanner_records': [{'scanner_name': 'stale-exclusion'}]}
    before = deepcopy(canonical)
    markdown = scanner_provenance_markdown(canonical, spanish=False)
    for literal in ('Requested analyzers: 2', 'Applicability unproven: 1',
                    'Completed required executions: 0', 'Incomplete required executions: 1',
                    'Not-applicable analyzers: 1'):
        assert literal in markdown
    assert 'stale' not in markdown
    assert canonical == before


def test_empty_authoritative_population_does_not_revive_stale_aliases():
    canonical = {'requested_scanner_records': [], 'assessment': {
        'requested_scanner_records': [{'scanner_name': 'stale', 'applicable': False}]}}
    markdown = scanner_provenance_markdown(canonical, spanish=False)
    assert 'Requested analyzers: 0' in markdown
    assert 'Not-applicable analyzers: 0' in markdown
    assert 'stale' not in markdown


def test_legacy_inline_and_split_exclusion_is_not_double_counted():
    row = {'scanner_name': 'excluded', 'applicable': False, 'completed': False}
    canonical = {'scanner_execution_records': [row], 'not_applicable_scanner_records': [deepcopy(row)]}
    before = deepcopy(canonical)
    markdown = scanner_provenance_markdown(canonical, spanish=False)
    assert 'Requested analyzers: 1' in markdown
    assert 'Not-applicable analyzers: 1' in markdown
    assert 'Incomplete required executions: 0' in markdown
    assert canonical == before
