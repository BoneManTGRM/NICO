"""Scores must disclose the source-evidence limit at the same reading point."""
from copy import deepcopy

import pytest

from nico.v2_authoritative_premium_report import _html_from_markdown
from nico.v2_premium_report_renderer import _score_summary_markdown


@pytest.mark.parametrize("spanish", [False, True])
def test_headline_scores_disclose_both_source_populations_in_markdown_and_html(spanish):
    assessment = {
        "technical_score": 93,
        "canonical_evidence_adjusted_score": 93,
        "source_security_assurance": {
            "status": "limited",
            "coverage_metrics": {
                "eligible_source_analysis": {"numerator": 14, "denominator": 1140, "percentage": 1.23},
                "observed_supported_source_analysis": {"numerator": 14, "denominator": 2401, "percentage": 0.58},
            },
            "unsampled_eligible_source_files": 1126,
        },
    }
    before = deepcopy(assessment)
    markdown = _score_summary_markdown(assessment, spanish=spanish)
    html = _html_from_markdown(markdown, "Report", spanish=spanish)
    for rendered in (markdown, html):
        assert "93/100" in rendered
        assert "14 / 1140 (1.23%)" in rendered
        assert "14 / 2401 (0.58%)" in rendered
        assert "1126" in rendered
        assert (
            "La madurez técnica no es una calificación de seguridad del repositorio en su conjunto."
            if spanish else "Technical maturity is not a repository-wide security rating."
        ) in rendered
        assert ("seguridad: limitada." if spanish else "assurance: limited.") in rendered
    assert assessment == before


@pytest.mark.parametrize("spanish", [False, True])
def test_high_maturity_does_not_supply_missing_source_assurance(spanish):
    assessment = {"technical_score": 100, "canonical_evidence_adjusted_score": 100}
    before = deepcopy(assessment)
    summary = _score_summary_markdown(assessment, spanish=spanish)
    assert "100/100" in summary
    assert ("seguridad: no verificada." if spanish else "assurance: unverified.") in summary
    assert ("Código elegible analizado" if spanish else "Eligible source analyzed") not in summary
    assert assessment == before


@pytest.mark.parametrize("spanish", [False, True])
def test_supported_scope_is_not_downgraded_or_presented_as_repository_wide_security(spanish):
    assessment = {
        "technical_score": 60,
        "canonical_evidence_adjusted_score": 60,
        "source_security_assurance": {"status": "supported_scope"},
    }
    summary = _score_summary_markdown(assessment, spanish=spanish)
    assert "60/100" in summary
    assert ("disponible para el alcance compatible" if spanish else "available for the supported scope") in summary
    assert ("no es una calificación de seguridad" if spanish else "not a repository-wide security rating") in summary


@pytest.mark.parametrize("spanish", [False, True])
def test_missing_measurement_and_incomplete_execution_remain_distinct(spanish):
    assessment = {
        "source_security_assurance": {
            "status": "limited",
            "incomplete_required_scanner_count": 1,
        },
    }
    summary = _score_summary_markdown(assessment, spanish=spanish)
    assert ("SIN PUNTUACIÓN" if spanish else "NOT SCORED") in summary
    assert ("La ejecución de analizadores está incompleta." if spanish else "Scanner execution is incomplete.") in summary
    assert "0/100" not in summary
