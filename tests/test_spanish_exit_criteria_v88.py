from __future__ import annotations

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_presentation_parity_v1 as presentation
from nico.comprehensive_spanish_exit_criteria_v88 import (
    install_comprehensive_spanish_exit_criteria_v88,
)


@pytest.mark.parametrize(("source", "expected"), [
    ("Reconcile each required disposition with the retained candidate population and preserve independent QC where required.", "Conciliar cada disposición requerida con la población de candidatos conservada y mantener el control de calidad independiente donde corresponda."),
    ("Bind the supplied evidence to its source and run, check its adequacy, and retain the revised limitation and review decision.", "Vincular la evidencia aportada con su fuente y ejecución, comprobar su suficiencia y conservar la limitación revisada y la decisión de revisión."),
    ("Work packages are provisional and bound to retained findings or evidence gaps. The 0-30/31-90/91-180 windows are illustrative; no owner, capacity, cost, date, approval, or delivery commitment is created.", "Los paquetes de trabajo son provisionales y están vinculados a hallazgos conservados o brechas de evidencia. Las ventanas 0-30/31-90/91-180 son ilustrativas; no se crea compromiso de responsable, capacidad, costo, fecha, aprobación ni entrega."),
])
def test_completed_review_roadmap_verification_translates_without_weakening_gate(source: str, expected: str) -> None:
    install_comprehensive_spanish_exit_criteria_v88()
    translated = canonical._translate_presentation_field(source, "verification")
    assert translated == expected


def _criterion(tail: str) -> str:
    return (
        "All listed verification requirements pass on the exact remediation commit, "
        "the exact-SHA rerun no longer reports the condition as unresolved material risk, "
        f"{tail}."
    )


def test_production_remediation_exit_criteria_localizes_without_english_leakage() -> None:
    result = install_comprehensive_spanish_exit_criteria_v88()

    assert result["bound"] is True
    assert result["targeted_fast_path"] is True
    for tail, expected in (
        (
            "and no new material regression is introduced",
            "no se introduce ninguna nueva regresión material",
        ),
        (
            "and no new material regressions are introduced",
            "no se introducen nuevas regresiones materiales",
        ),
        (
            "and no new material regression is observed",
            "no se observa ninguna nueva regresión material",
        ),
        (
            "and no new material regressions are observed",
            "no se observan nuevas regresiones materiales",
        ),
    ):
        source = _criterion(tail)
        translated = canonical._translate_presentation_field(source, "exit_criteria")

        assert "Todos los requisitos de verificación enumerados" in translated
        assert "nueva ejecución sobre el SHA exacto" in translated
        assert "riesgo material sin resolver" in translated
        assert expected in translated
        assert "All listed verification requirements" not in translated
        assert "unresolved material risk" not in translated
        assert "new material regression" not in translated
        assert canonical._looks_like_untranslated_english(translated) is False

        detached = presentation._safe_es(source)
        assert "All listed verification requirements" not in detached
        assert "unresolved material risk" not in detached
        assert "new material regression" not in detached


def test_exit_criteria_hotfix_is_idempotent_and_does_not_expand_global_loops() -> None:
    canonical_replacements = canonical._PRESENTATION_REPLACEMENTS
    presentation_phrases = dict(presentation._ES_PHRASES)

    first = install_comprehensive_spanish_exit_criteria_v88()
    canonical_translator = canonical._translate_presentation_field
    presentation_translator = presentation._safe_es
    second = install_comprehensive_spanish_exit_criteria_v88()

    assert first["bound"] is True
    assert second["bound"] is True
    assert canonical._translate_presentation_field is canonical_translator
    assert presentation._safe_es is presentation_translator
    assert canonical._PRESENTATION_REPLACEMENTS is canonical_replacements
    assert presentation._ES_PHRASES == presentation_phrases


def test_roadmap_line_preserves_package_and_source_anchors() -> None:
    install_comprehensive_spanish_exit_criteria_v88()
    prefix = "NICO-WORK-06B8E8AC460ADC6B | review_candidate_summary | "
    source = "Review the retained scanner candidates and record evidence-linked dispositions; candidate counts are not confirmed defect counts."
    translated = canonical._translate_presentation_field(prefix + source, "evidence")
    assert translated == prefix + (
        "Revisar los candidatos conservados de los analizadores y registrar disposiciones "
        "vinculadas a evidencia; los recuentos de candidatos no son recuentos de defectos confirmados."
    )


@pytest.mark.parametrize("prefix", [
    "NICO-WORK-06B8E8AC460ADC6B | review_candidate_summary | ",
    "NICO-WORK-invalid | review_candidate_summary | ",
])
def test_roadmap_unknown_prose_still_fails_closed(prefix: str) -> None:
    install_comprehensive_spanish_exit_criteria_v88()
    with pytest.raises(ValueError, match="missing Spanish presentation translation"):
        canonical._translate_presentation_field(
            prefix + "The unexplained future workflow requires an unsupported review decision.",
            "evidence",
        )
