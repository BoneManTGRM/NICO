from copy import deepcopy

import pytest

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v4 as v4
from nico import comprehensive_native_providers_v5 as v5
from nico import comprehensive_spanish_canonical_report_v87 as spanish
from test_comprehensive_native_providers_v4 import _context, _repo, _scan


@pytest.mark.parametrize('provider', [v4, v5])
@pytest.mark.parametrize('status,completed,verified,en,es', [
    ('completed', True, True, 'completed with verified retained evidence', 'se completó con evidencia conservada verificada'),
    ('completed_with_findings', True, True, 'completed with verified retained evidence', 'se completó con evidencia conservada verificada'),
    ('unavailable', False, False, 'was unavailable', 'no estuvo disponible'),
    ('failed', False, False, 'failed; no completed analysis is claimed', 'falló; no se afirma que el análisis se haya completado'),
    ('not_run', False, False, 'was not run', 'no se ejecutó'),
    ('completed', True, False, 'completion is not verified', 'finalización no está verificada'),
    (None, False, False, 'was not run', 'no se ejecutó'),
])
def test_active_provider_typescript_execution_wording(monkeypatch, provider, status, completed, verified, en, es):
    scan = _scan()
    if status is None:
        scan['scanner_results'] = [r for r in scan['scanner_results'] if r['tool'] != 'typescript']
    else:
        record = next(r for r in scan['scanner_results'] if r['tool'] == 'typescript')
        record.update(status=status, completed=completed, verified=verified,
                      reason='NICO_ALLOW_PROJECT_COMMANDS is not enabled')
    original = deepcopy(scan)
    monkeypatch.setattr(legacy, '_repo', lambda context: _repo())
    monkeypatch.setattr(legacy, '_scan', lambda context: scan)
    result = provider.canonical_scoring_provider(_context())
    assert result['status'] == 'complete'
    section = next(s for s in result['assessment']['sections'] if s['id'] == 'static_analysis')
    summary = section['summary']
    assert en in summary
    translated = spanish._translate_presentation(summary)
    assert es in translated
    assert 'evidence were evaluated independently' not in summary
    assert 'se evaluó de forma independiente' not in translated
    assert scan == original
    expected_incomplete = [] if completed and verified else ['typescript']
    assert section['score_contract']['incomplete_analyzers'] == expected_incomplete
    assert section['presented_score'] == (96 if not expected_incomplete else 88)
    # Compare the complete provider result with its old prose: only this
    # section summary may change, including all numeric and coverage fields.
    monkeypatch.setattr(v4, '_static_analysis_summary', lambda scan:
        'Bandit, Semgrep, ESLint, and TypeScript evidence were evaluated independently against the exact immutable commit.')
    baseline = provider.canonical_scoring_provider(_context())
    candidate = deepcopy(result)
    candidate_section = next(s for s in candidate['assessment']['sections'] if s['id'] == 'static_analysis')
    baseline_section = next(s for s in baseline['assessment']['sections'] if s['id'] == 'static_analysis')
    candidate_section['summary'] = baseline_section['summary']
    assert candidate == baseline


@pytest.mark.parametrize('field', ['completed', 'verified', 'exact_commit_match', 'raw_artifact_retention_complete'])
def test_completion_requires_every_existing_evidence_guard(field):
    scan = _scan()
    record = next(r for r in scan['scanner_results'] if r['tool'] == 'typescript')
    record[field] = False
    summary = v4._static_analysis_summary(scan)
    assert 'completion is not verified' in summary
    assert 'finalización no está verificada' in spanish._translate_presentation(summary)


def test_proven_inapplicability_receives_no_execution_claim(tmp_path):
    from test_native_scoring_applicability import absent_scan
    scan = absent_scan(tmp_path)
    summary = v4._static_analysis_summary(scan)
    assert 'proven not applicable; no execution credit' in summary
    assert 'no se atribuye crédito de ejecución' in spanish._translate_presentation(summary)
    scan['actual_commit_sha'] = 'b' * 40
    assert 'completion is not verified' in v4._static_analysis_summary(scan)
