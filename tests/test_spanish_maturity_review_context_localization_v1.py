from nico.comprehensive_spanish_current_copy_worker_v98 import (
    localize_current_report_copy_v98,
)


def test_production_maturity_review_context_sentence_localizes_with_dynamic_truth_preserved() -> None:
    source = (
        "Technical maturity remains based on exact-commit technical controls. "
        "Evidence-Adjusted readiness is 93/100 versus technical maturity 93/100. "
        "NICO retains 691 review-required candidates and 0 confirmed material findings as explicit review context. "
        "Candidate volume and reviewer workload are operational review metrics and have no numeric technical-maturity or Evidence-Adjusted score effect."
    )

    localized = localize_current_report_copy_v98(source)

    assert "Technical maturity remains based on exact-commit technical controls" not in localized
    assert "Evidence-Adjusted readiness is" not in localized
    assert "review-required candidates" not in localized
    assert "Candidate volume and reviewer workload" not in localized
    assert "La madurez técnica sigue basándose en controles técnicos del commit exacto." in localized
    assert "La preparación ajustada por evidencia es 93/100 frente a una madurez técnica de 93/100." in localized
    assert "NICO conserva 691 candidatos que requieren revisión y 0 hallazgos materiales confirmados" in localized
    assert "El volumen de candidatos y la carga de trabajo del revisor" in localized


def test_legacy_maturity_review_context_tail_localizes_without_changing_counts() -> None:
    source = (
        "Technical maturity remains based on exact-commit technical controls. "
        "Evidence-Adjusted readiness is 91/100 versus technical maturity 94/100. "
        "NICO retains 27 review-required candidates and 2 confirmed material findings as explicit review context. "
        "Candidate volume, clustering and reviewer workload do not change numeric security or readiness scores."
    )

    localized = localize_current_report_copy_v98(source)

    assert "Technical maturity remains based on exact-commit technical controls" not in localized
    assert "Candidate volume, clustering and reviewer workload" not in localized
    assert "91/100" in localized
    assert "94/100" in localized
    assert "27 candidatos que requieren revisión" in localized
    assert "2 hallazgos materiales confirmados" in localized
    assert "El volumen de candidatos, la agrupación y la carga de trabajo de revisión" in localized
