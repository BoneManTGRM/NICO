from copy import deepcopy
from functools import wraps
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from nico.spanish_retained_candidate_contracts import translate_retained_candidate_contract


def _isolated_preflight_test(check):
    """Do not let real installer mutations change unrelated locale test contracts."""
    @wraps(check)
    def isolated(*args, **kwargs):
        from tests.owned_worker_environment import owned_worker_environment
        root = Path(__file__).resolve().parents[1]
        arguments = json.dumps([args, kwargs])
        code = (
            'import json; from tests.' + check.__module__.removeprefix('tests.') + ' import '
            + check.__name__ + '; args, kwargs = json.loads(' + repr(arguments) + '); '
            + check.__name__ + '.__wrapped__(*args, **kwargs)'
        )
        with tempfile.TemporaryDirectory(prefix='nico-candidate-locale-') as temp:
            result = subprocess.run([sys.executable, '-c', code], cwd=root,
                env=owned_worker_environment(root, Path(temp), os.environ),
                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
    return isolated


def _installed_preflight(record):
    from nico.comprehensive_spanish_publication_preflight_v93 import (
        inspect_spanish_canonical_publication_preflight,
        install_spanish_publication_preflight_v93,
    )
    install_spanish_publication_preflight_v93()
    return inspect_spanish_canonical_publication_preflight({
        'report_language': 'es-MX', 'findings_register': [record],
    })


@pytest.mark.parametrize('category', ['dependency', 'secret', 'static', 'code'])
@pytest.mark.parametrize('samples', [False, True])
@_isolated_preflight_test
def test_real_candidate_group_preflights_without_changing_evidence(category, samples):
    from nico.comprehensive_assessment_hardening_v1 import _candidate_group
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    records = [{'finding_id': 'OWNED-1'}]
    if samples:
        records[0].update(location='src/owned.py:17', package='@owned/package', rule_id='B608')
    group = _candidate_group(category, 'bandit', records)
    original = deepcopy(group)
    manifest = _installed_preflight(group)
    assert manifest['status'] == 'complete', manifest
    localized = _localize_tree({'findings_register': [group]})['findings_register'][0]
    assert group == original
    assert localized['finding_id'] == group['finding_id']
    assert localized['candidate_count'] == 1
    assert localized['material'] is False and localized['review_required'] is True
    assert 'bandit' in localized['fact']
    if samples:
        for literal in ('src/owned.py:17', '@owned/package', 'B608'):
            assert literal in localized['fact']


@_isolated_preflight_test
def test_real_sql_source_review_fact_and_criteria_preflight():
    from nico.phase6_canonical_truth_v2 import _source_review_sql_records
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    records = _source_review_sql_records({'scan': {'tool': 'bandit', 'findings': [
        {'rule_id': 'B608', 'file_path': 'nico/comprehensive_run_store.py', 'line': 17},
    ]}})
    assert len(records) == 1
    record = records[0]
    original = deepcopy(record)
    assert _installed_preflight(record)['status'] == 'complete'
    localized = _localize_tree({'findings_register': records})['findings_register'][0]
    assert record == original
    assert 'Bandit B608' in localized['fact']
    assert 'sin afirmar que la explotación estuviera verificada' in localized['fact']
    assert localized['file_path'] == original['file_path'] and localized['line'] == 17
    assert localized['human_review_required'] is True


@pytest.mark.parametrize('text', [
    '1 unverified static candidate(s) were retained from bandit. Candidate count is confirmed defect count.',
    '1 unverified static candidate(s) were retained from bandit. Candidate count is not confirmed defect count. Unreviewed new prose.',
    'The originating analyzer is never rerun after any SQL construction change.',
])
@_isolated_preflight_test
def test_unknown_or_changed_prose_still_fails_closed(text):
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    _installed_preflight({})
    assert translate_retained_candidate_contract(text) is None
    with pytest.raises(ValueError):
        _translate_presentation_field(text, 'fact')


def test_unknown_category_is_not_recognized_by_new_helper():
    assert translate_retained_candidate_contract('Unknown review candidates from bandit (1 candidates)') is None
