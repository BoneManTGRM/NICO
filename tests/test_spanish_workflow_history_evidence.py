import pytest
from tests.test_spanish_retained_candidate_contracts import _isolated_preflight_test
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88


@_isolated_preflight_test
def test_authored_workflow_history_evidence_translates_on_strict_boundary():
    v88.install_comprehensive_spanish_exit_criteria_v88()
    from nico.comprehensive_decision_grade_report_v5 import _phase5_outcome_rows
    rows = _phase5_outcome_rows({'phase5_verified_outcomes': {'ci_history_classification_visible': True}})
    source = next(row['evidence'] for row in rows if row['category'] == 'ci_history')
    value = canonical._translate_presentation_field(source, 'evidence')
    assert value == 'historial acotado conservado de ejecuciones de flujos de trabajo'
    assert not canonical._looks_like_untranslated_english(value)


@_isolated_preflight_test
def test_unknown_workflow_history_prose_stays_rejected():
    v88.install_comprehensive_spanish_exit_criteria_v88()
    with pytest.raises(ValueError, match='missing Spanish presentation translation'):
        canonical._translate_presentation_field('The unapproved workflow history proves a verified production outage.', 'evidence')
