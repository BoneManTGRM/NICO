from copy import deepcopy
import json
import math
import pytest
from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v2 as v2, comprehensive_native_providers_v3 as v3, comprehensive_native_providers_v4 as v4, comprehensive_native_providers_v5 as v5
from nico.full_assessment_complexity_evidence import collect_complexity_evidence
from tests.test_comprehensive_native_providers_v2 import _context, _repo, _scan


@pytest.mark.parametrize('provider', [v2, v3, v4, v5])
@pytest.mark.parametrize('value', [None, True, False, float('nan'), float('inf'), float('-inf'), -1, 101, 10**400, '78', 0, 0.0, 78, 78.25])
def test_score_input_validity_and_unknown_propagation(monkeypatch, provider, value):
    context = _context()
    evidence = {**context, 'snapshot_commit_sha': context['commit_sha'], 'evidence_id': 'complexity-test', 'files_analyzed': 1}
    evidence.pop('prior_stage_results')
    if value is not None:
        evidence['complexity_score'] = value
    before = deepcopy(evidence)
    monkeypatch.setattr(legacy, '_repo', lambda _: _repo())
    monkeypatch.setattr(legacy, '_scan', lambda _: _scan())
    monkeypatch.setattr(legacy, '_complexity', lambda _: evidence)
    result = provider.canonical_scoring_provider(context)
    sections = {s['id']:s for s in result['assessment']['sections']}
    valid = type(value) in (int, float) and 0 <= value <= 100 and math.isfinite(value)
    architecture = sections['architecture_debt']
    assert architecture['presented_score'] == (int(value) if valid else None)
    if not valid:
        assert architecture['exclude_from_maturity'] is True
        if provider is not v2:
            assert sections['velocity_complexity']['presented_score'] is None
    assert json.dumps(evidence, sort_keys=True) == json.dumps(before, sort_keys=True)
    assert result['client_delivery_allowed'] is False


def test_unknown_architecture_does_not_become_ci_only_forty():
    score, _, _, _ = v3._immutable_delivery_score(None, 100, {}, {})
    assert score is None


@pytest.mark.parametrize('field', ['run_id', 'repository', 'snapshot_commit_sha', 'commit_sha', 'evidence_ledger_id', 'customer_id', 'project_id'])
def test_mismatched_score_evidence_not_scored(monkeypatch, field):
    context = _context()
    evidence = {**context, 'snapshot_commit_sha': context['commit_sha'], 'evidence_id': 'complexity-test', 'complexity_score': 78}
    evidence[field] = 'wrong'
    monkeypatch.setattr(legacy, '_repo', lambda _: _repo())
    monkeypatch.setattr(legacy, '_scan', lambda _: _scan())
    monkeypatch.setattr(legacy, '_complexity', lambda _: evidence)
    sections = v5.canonical_scoring_provider(context)['assessment']['sections']
    assert next(s for s in sections if s['id']=='architecture_debt')['score'] is None


def test_actual_collector_evidence_is_not_an_architecture_score(monkeypatch):
    evidence = collect_complexity_evidence({'sample.py':'def f(x):\n    return x\n'})
    assert 'complexity_score' not in evidence
    monkeypatch.setattr(legacy, '_repo', lambda _: _repo())
    monkeypatch.setattr(legacy, '_scan', lambda _: _scan())
    monkeypatch.setattr(legacy, '_complexity', lambda _: evidence)
    for provider in (v2,v3,v4,v5):
        sections = provider.canonical_scoring_provider(_context())['assessment']['sections']
        assert next(s for s in sections if s['id']=='architecture_debt')['score'] is None


def test_reconciliation_does_not_restore_stale_section_scores(monkeypatch):
    from nico.comprehensive_decision_grade_markdown_v5 import _decorate_assessment
    from nico.comprehensive_report_scanner_scoring_v51 import _normalize_assessment
    from nico.comprehensive_premium_synthesis_v6 import polish_assessment
    monkeypatch.setattr(legacy, '_repo', lambda _: _repo())
    monkeypatch.setattr(legacy, '_scan', lambda _: _scan())
    monkeypatch.setattr(legacy, '_complexity', lambda _: {})
    assessment = v5.canonical_scoring_provider(_context())['assessment']
    population = assessment['score_contract']['scored_population']
    assert population['scored_section_count'] == population['total_section_count'] - 2
    assert population['population_change_is_quality_improvement'] is False
    for section in assessment['sections']:
        if section['id'] in ('architecture_debt','velocity_complexity'):
            section.update(score=78, source_score=78, presented_score=87, score_value=87, technical_score=87)
    for normalize in (_decorate_assessment, lambda a: _normalize_assessment(a, {}), polish_assessment, _decorate_assessment):
        assessment = normalize(assessment)
        for section in assessment['sections']:
            if section['id'] in ('architecture_debt','velocity_complexity'):
                assert all(section.get(key) is None for key in ('score','source_score','presented_score','score_value','technical_score'))
                assert section['exclude_from_maturity'] is True
                assert section['technical_score_display'] == 'NOT SCORED'


def test_unproven_numeric_input_is_excluded():
    score, receipt = v2._architecture_score_input(_context(), {'complexity_score': 0})
    assert score is None
    assert receipt['reason'] == 'score_input_identity_unproven'


def test_unknown_score_copy_has_deterministic_spanish_translation():
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    strings = [
        'Unscored controls are excluded from maturity; any resulting mean change is not evidence of improved source quality.',
        'Architecture is not scored because a valid exact-source score input is unavailable; measured complexity evidence remains retained.',
        'Delivery capacity is not scored because architecture has no valid exact-source score input.',
        'Architecture and technical-debt score: not scored.',
    ]
    assert all(_localize_tree({'summary': value})['summary'] != value for value in strings)


def test_unknown_and_zero_are_distinct_in_delivery_formula():
    assert v3._immutable_delivery_score(0, 100, {}, {})[0] == 40
    assert v3._immutable_delivery_score(None, 100, {}, {})[0] is None


def test_unscored_values_remain_absent_from_rendered_scorecards(monkeypatch):
    import io
    from pypdf import PdfReader
    from nico.comprehensive_decision_grade_markdown_v5 import _decorate_assessment, _scorecard_and_risk_lines
    from nico.comprehensive_decision_grade_html_v6 import _scorecard_html
    from nico.comprehensive_premium_pdf_v6 import _build_pdf
    monkeypatch.setattr(legacy, '_repo', lambda _: _repo())
    monkeypatch.setattr(legacy, '_scan', lambda _: _scan())
    monkeypatch.setattr(legacy, '_complexity', lambda _: {})
    assessment = _decorate_assessment(v5.canonical_scoring_provider(_context())['assessment'])
    sections = [s for s in assessment['sections'] if s['id'] in ('architecture_debt','velocity_complexity')]
    markdown = '\n'.join(_scorecard_and_risk_lines({'sections':sections,'executive':[]}))
    html = _scorecard_html(sections)
    limitations = {key:0 for key in ('stages_with_limitations','individual_limitation_records','score_affecting_records','informational_records')}
    # Keep this a bounded rendering check: only the two affected scorecard rows.
    assessment['sections'] = sections
    from nico.comprehensive_premium_synthesis_v6 import polish_assessment
    assessment = polish_assessment(assessment)
    pdf = _build_pdf(_context(), assessment, [], [], [], limitations, '2026-10-19T00:00:00Z')
    text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    for surface in (markdown, html, text):
        assert 'NOT SCORED' in ' '.join(surface.split()), surface
        assert '78/100' not in surface and '87/100' not in surface
    assert _context()['commit_sha'] in text
