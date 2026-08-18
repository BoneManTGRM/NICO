from __future__ import annotations

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_presentation_parity_v1 as presentation
from nico.comprehensive_spanish_exit_criteria_v88 import (
    install_comprehensive_spanish_exit_criteria_v88,
)


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
