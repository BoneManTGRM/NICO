from copy import deepcopy
import base64
import io

import pytest
from pypdf import PdfReader

from nico.report_score_explanation import score_explanation, LABELS_ES, UNAVAILABLE
from nico import comprehensive_report_package as report
from nico import comprehensive_spanish_canonical_report_v87 as spanish


def assessment(values=(0, 0, 4, 0), technical=92):
    candidate, payload, analyzer, other = values
    adjusted = max(0, technical - sum(values))
    return {'technical_score': technical, 'canonical_evidence_adjusted_score': adjusted,
            'maturity_signal': {'score': technical, 'presented_score': technical, 'evidence_readiness_score': adjusted},
            'score_contract': {'scoring_model_version': 'technical-minus-named-assurance-deductions.v1',
                'technical_score': technical, 'evidence_adjusted_score': adjusted,
                'candidate_volume_penalty': candidate, 'missing_raw_payload_penalty': payload,
                'incomplete_analyzer_penalty': analyzer, 'other_assurance_penalties': {'synthetic_other': other},
                'other_assurance_penalty_total': other, 'assurance_penalty': sum(values),
                'incomplete_analyzers': ['typescript'],
                'score_formula': ' - '.join(map(str, [technical, *values])) + f' = {adjusted}'}}


@pytest.mark.parametrize('values', [(0,0,0,0), (0,0,4,0), (2,3,4,1), (0,0,0,5)])
@pytest.mark.parametrize('locale', ['en','es-MX'])
def test_explicit_deductions_and_no_mutation(values, locale):
    a = assessment(values); before = deepcopy(a)
    tr = spanish._translate_presentation if locale == 'es-MX' else lambda s:s
    lines = score_explanation(a, tr)
    assert f'{tr("Retained formula")}: {a["score_contract"]["score_formula"]}' in lines
    assert f'{tr("Incomplete-analyzer deduction")}: {values[2]}' in lines
    assert f'{tr("Candidate-volume deduction")}: {values[0]}' in lines
    assert a == before


@pytest.mark.parametrize('change', ['missing', 'unsupported', 'missing_penalty', 'negative', 'bool',
                                  'bad_formula', 'bad_total', 'alias', 'bad_other', 'bad_score'])
def test_missing_or_inconsistent_contract_is_not_inferred(change):
    a = assessment(); c = a['score_contract']
    if change == 'missing': del a['score_contract']
    elif change == 'unsupported': c['scoring_model_version'] = 'unknown'
    elif change == 'missing_penalty': del c['missing_raw_payload_penalty']
    elif change == 'negative': c['candidate_volume_penalty'] = -1
    elif change == 'bool': c['candidate_volume_penalty'] = False
    elif change == 'bad_formula': c['score_formula'] = '92 - 0 = 88'
    elif change == 'bad_total': c['assurance_penalty'] = 3
    elif change == 'alias': a['maturity_signal']['evidence_readiness_score'] = 89
    elif change == 'bad_other': c['other_assurance_penalties'] = {'hidden': 8}
    elif change == 'bad_score': c['technical_score'] = 101
    before = deepcopy(a)
    assert score_explanation(a) == [UNAVAILABLE]
    assert score_explanation(a, spanish._translate_presentation) == [LABELS_ES[UNAVAILABLE]]
    assert a == before


def test_current_model_and_no_inferred_analyzer_names():
    a = assessment(); c = a['score_contract']
    c.update(scoring_model_version='technical-minus-evidence-completeness-deductions.v1',
             score_formula='92 - 0 - 4 = 88', other_assurance_penalties={})
    del c['incomplete_analyzers']
    assert 'Analyzer names unavailable in the retained contract' in score_explanation(a)
    assert not any('Candidate-volume' in line for line in score_explanation(a))
    c['candidate_volume_penalty'] = 1
    assert score_explanation(a) == [UNAVAILABLE]


@pytest.mark.parametrize('locale', ['en','es-MX'])
def test_synthetic_markdown_and_pdf_contain_named_explanation_without_mutation(tmp_path, locale):
    a = assessment(); before = deepcopy(a)
    identity = {'run_id':'comprun_synthetic_score','repository':'owned/synthetic','commit_sha':'a'*40}
    tr = spanish._translate_presentation if locale == 'es-MX' else lambda s:s
    md = report._markdown(identity, a, [], '2026-01-01', localize_presentation=tr)
    encoded, error, pages = report._pdf(identity, a, [], '2026-01-01', localize_presentation=tr)
    assert error is None and pages > 0
    pdf = base64.b64decode(encoded)
    text = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    for label in ['Technical-to-adjusted score explanation', 'Incomplete-analyzer deduction', 'Evidence-adjusted score']:
        assert tr(label) in md and tr(label) in text
    assert '92 - 0 - 0 - 4 - 0 = 88' in md and '92 - 0 - 0 - 4 - 0 = 88' in text
    assert 'typescript' in text
    assert a == before
    (tmp_path / f'score-explanation-{locale}.pdf').write_bytes(pdf)


@pytest.mark.parametrize("field", ["assurance_penalty", "other_assurance_penalty_total"])
def test_boolean_totals_are_not_numeric_contracts(field):
    a = assessment((0, 0, 0, 0))
    a["score_contract"][field] = False
    assert score_explanation(a) == [UNAVAILABLE]


def test_explicit_deductions_can_exceed_technical_with_zero_floor():
    a = assessment((0, 3, 4, 0), technical=2)
    assert "Retained formula: 2 - 0 - 3 - 4 - 0 = 0" in score_explanation(a)
    assert "Evidence-adjusted score: 0/100" in score_explanation(a)
