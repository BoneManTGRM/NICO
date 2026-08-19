from __future__ import annotations

import pytest

from nico import comprehensive_native_providers as providers
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_client_surface_localization_v85 as client_v85
from nico import comprehensive_spanish_presentation_parity_v1 as presentation
from nico import comprehensive_spanish_exit_criteria_v88 as v88


_ROLLBACK_EN = (
    "Revert the isolated remediation change if targeted or full verification fails; "
    "retain the failed evidence and keep client delivery blocked."
)
_ROLLBACK_ES = (
    "Revierta el cambio aislado de remediación si falla la verificación dirigida o "
    "completa; conserve la evidencia del fallo y mantenga bloqueada la entrega al cliente."
)
_SCORE_SUMMARY_EN_SOFT_WRAPPED = (
    "Technical maturity remains based on exact-commit technical controls.\n"
    "Evidence-Adjusted readiness is 93/100 versus technical maturity 93/100. "
    "NICO retains 639 review-required candidates and 0 confirmed material\n"
    "findings as explicit review context. Candidate volume, clustering and reviewer "
    "workload do not change numeric security or readiness scores."
)
_SCORE_SUMMARY_ES = (
    "La madurez técnica sigue basándose en controles técnicos del commit exacto. "
    "La preparación ajustada por evidencia es 93/100 frente a una madurez técnica de "
    "93/100. NICO conserva 639 candidatos que requieren revisión y 0 hallazgos "
    "materiales confirmados como contexto explícito de revisión. El volumen de "
    "candidatos, la agrupación y la carga de trabajo de revisión no modifican las "
    "puntuaciones numéricas de seguridad ni de preparación."
)


def test_v88_binds_shared_report_execution_boundary() -> None:
    result = v88.install_comprehensive_spanish_exit_criteria_v88()

    assert result["bound"] is True
    assert result["direct_canonical_presentation_bound"] is True
    assert result["terminal_client_surface_soft_wrap_repair"] is True
    assert result["report_runtime_boundary_bound"] is True
    assert result["detached_decision_report_reassertion"] is True
    assert result["targeted_rollback_translation"] is True
    assert result["structured_soft_whitespace_repair"] is True
    assert result["ci_pdf_control_safety_deferred_to_native_report_boundary"] is True
    assert canonical._translate_presentation is v88._translate_presentation_v88
    assert providers._build_report is v88._native_build_report_v88


def test_exact_production_rollback_literal_translates_on_canonical_surface(monkeypatch) -> None:
    observed: dict[str, str] = {}

    def validated(value: str, key: str) -> str:
        observed["value"] = value
        observed["key"] = key
        return value

    monkeypatch.setattr(v88, "_ORIGINAL_CANONICAL_TRANSLATE_FIELD", validated)

    assert v88._translate_canonical_field_v88(_ROLLBACK_EN, "rollback") == _ROLLBACK_ES
    assert observed == {"value": _ROLLBACK_ES, "key": "rollback"}


def test_exact_production_rollback_literal_translates_on_presentation_surface(monkeypatch) -> None:
    observed: list[str] = []

    def validated(value: object) -> str:
        text = str(value)
        observed.append(text)
        return text

    monkeypatch.setattr(v88, "_ORIGINAL_PRESENTATION_SAFE_ES", validated)

    assert v88._presentation_safe_es_v88(_ROLLBACK_EN) == _ROLLBACK_ES
    assert observed == [_ROLLBACK_ES]


def test_soft_wrapped_production_score_summary_normalizes_before_v87_validation(
    monkeypatch,
) -> None:
    observed: dict[str, str] = {}

    def validated(value: str, key: str) -> str:
        observed["value"] = value
        observed["key"] = key
        return canonical._translate_presentation(value)

    monkeypatch.setattr(v88, "_ORIGINAL_CANONICAL_TRANSLATE_FIELD", validated)

    translated = v88._translate_canonical_field_v88(
        _SCORE_SUMMARY_EN_SOFT_WRAPPED,
        "summary",
    )

    assert translated == _SCORE_SUMMARY_ES
    assert "\n" not in observed["value"]
    assert observed["value"].startswith(
        "Technical maturity remains based on exact-commit technical controls."
    )
    assert observed["key"] == "summary"


def test_soft_wrapped_production_score_summary_translates_on_presentation_surface(
    monkeypatch,
) -> None:
    observed: list[str] = []

    def validated(value: object) -> str:
        text = str(value)
        observed.append(text)
        return text

    monkeypatch.setattr(v88, "_ORIGINAL_PRESENTATION_SAFE_ES", validated)

    assert v88._presentation_safe_es_v88(_SCORE_SUMMARY_EN_SOFT_WRAPPED) == _SCORE_SUMMARY_ES
    assert observed == [_SCORE_SUMMARY_ES]


def test_soft_wrapped_production_score_summary_translates_on_direct_canonical_surface(
    monkeypatch,
) -> None:
    observed: list[str] = []

    def validated(value: object) -> str:
        text = str(value)
        observed.append(text)
        translated = canonical._structured_presentation_es(text)
        if translated is None:
            raise ValueError(f"unrecognized Spanish presentation contract: {text}")
        return translated

    monkeypatch.setattr(v88, "_ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION", validated)

    assert v88._translate_presentation_v88(_SCORE_SUMMARY_EN_SOFT_WRAPPED) == _SCORE_SUMMARY_ES
    assert len(observed) == 1
    assert "\n" not in observed[0]
    assert observed[0].startswith(
        "Technical maturity remains based on exact-commit technical controls."
    )


def test_terminal_client_surface_uses_direct_soft_wrap_repair() -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()

    translated = client_v85._localize_presentation_text(_SCORE_SUMMARY_EN_SOFT_WRAPPED)

    assert translated == _SCORE_SUMMARY_ES
    assert "Technical maturity remains based" not in translated


def test_unknown_soft_wrapped_structured_contract_still_fails_closed(monkeypatch) -> None:
    unknown = (
        "Technical maturity remains based on exact-commit technical controls.\n"
        "This changed contract has no approved Spanish translation."
    )

    def fail_closed(value: str, key: str) -> str:
        del key
        return canonical._translate_presentation(value)

    monkeypatch.setattr(v88, "_ORIGINAL_CANONICAL_TRANSLATE_FIELD", fail_closed)

    with pytest.raises(ValueError, match="unrecognized Spanish presentation contract"):
        v88._translate_canonical_field_v88(unknown, "summary")


def test_unknown_soft_wrapped_direct_contract_still_fails_closed(monkeypatch) -> None:
    unknown = (
        "Technical maturity remains based on exact-commit technical controls.\n"
        "This changed contract has no approved Spanish translation and still says "
        "readiness scores."
    )

    def fail_closed(value: object) -> str:
        raise ValueError(f"unrecognized Spanish presentation contract: {str(value)[:180]}")

    monkeypatch.setattr(v88, "_ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION", fail_closed)

    with pytest.raises(ValueError, match="unrecognized Spanish presentation contract"):
        v88._translate_presentation_v88(unknown)


def test_unknown_rollback_literal_still_uses_fail_closed_canonical_validator(monkeypatch) -> None:
    unknown = "Revert some other remediation behavior without an approved translation."

    def fail_closed(value: str, key: str) -> str:
        raise ValueError(f"missing Spanish presentation translation for {key}: {value}")

    monkeypatch.setattr(v88, "_ORIGINAL_CANONICAL_TRANSLATE_FIELD", fail_closed)

    with pytest.raises(ValueError, match="missing Spanish presentation translation for rollback"):
        v88._translate_canonical_field_v88(unknown, "rollback")


def test_exit_criteria_fast_path_remains_separate_from_rollback_literal() -> None:
    source = (
        "All listed verification requirements pass on the exact remediation commit; "
        "and no new material regression is introduced"
    )
    translated = v88._translate_known_exit_criteria(source)

    assert "Todos los requisitos de verificación enumerados" in translated
    assert "y no se introduce ninguna nueva regresión material" in translated
    assert _ROLLBACK_ES not in translated


def test_captured_decision_report_provider_reasserts_spanish_translation_at_call_time(
    monkeypatch,
) -> None:
    # Production binds the capability executor before the detached worker eventually
    # invokes it. Capture that same provider function before installing the runtime
    # guard to prove its global _build_report lookup still reaches the guarded boundary.
    captured_provider = providers.report_generation_provider
    v88.install_comprehensive_spanish_exit_criteria_v88()

    original_direct = v88._ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION
    original_canonical = v88._ORIGINAL_CANONICAL_TRANSLATE_FIELD
    original_presentation = v88._ORIGINAL_PRESENTATION_SAFE_ES
    assert original_direct is not None
    assert original_canonical is not None
    assert original_presentation is not None

    # Model a late compatibility installer replacing the three translator aliases after
    # application startup but before detached decision-report execution begins.
    monkeypatch.setattr(canonical, "_translate_presentation", original_direct)
    monkeypatch.setattr(canonical, "_translate_presentation_field", original_canonical)
    monkeypatch.setattr(presentation, "_safe_es", original_presentation)

    observed: dict[str, object] = {}

    def fake_build_report(context: dict[str, object], final: bool) -> dict[str, object]:
        observed["direct_reasserted"] = (
            canonical._translate_presentation is v88._translate_presentation_v88
        )
        observed["canonical_reasserted"] = (
            canonical._translate_presentation_field is v88._translate_canonical_field_v88
        )
        observed["presentation_reasserted"] = (
            presentation._safe_es is v88._presentation_safe_es_v88
        )
        observed["final"] = final
        return {"status": "complete", "runtime_guard": True}

    monkeypatch.setattr(v88, "_ORIGINAL_NATIVE_BUILD_REPORT", fake_build_report)

    result = captured_provider({"report_language": "es-MX"})

    assert result == {"status": "complete", "runtime_guard": True}
    assert observed == {
        "direct_reasserted": True,
        "canonical_reasserted": True,
        "presentation_reasserted": True,
        "final": False,
    }


def test_english_report_path_does_not_rebind_spanish_translators(monkeypatch) -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()
    original_direct = v88._ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION
    original_canonical = v88._ORIGINAL_CANONICAL_TRANSLATE_FIELD
    original_presentation = v88._ORIGINAL_PRESENTATION_SAFE_ES
    assert original_direct is not None
    assert original_canonical is not None
    assert original_presentation is not None

    monkeypatch.setattr(canonical, "_translate_presentation", original_direct)
    monkeypatch.setattr(canonical, "_translate_presentation_field", original_canonical)
    monkeypatch.setattr(presentation, "_safe_es", original_presentation)

    observed: dict[str, object] = {}

    def fake_build_report(context: dict[str, object], final: bool) -> dict[str, object]:
        observed["direct_unchanged"] = canonical._translate_presentation is original_direct
        observed["canonical_unchanged"] = (
            canonical._translate_presentation_field is original_canonical
        )
        observed["presentation_unchanged"] = presentation._safe_es is original_presentation
        observed["final"] = final
        return {"status": "complete", "english_path": True}

    monkeypatch.setattr(v88, "_ORIGINAL_NATIVE_BUILD_REPORT", fake_build_report)

    result = v88._native_build_report_v88({"report_language": "en"}, False)

    assert result == {"status": "complete", "english_path": True}
    assert observed == {
        "direct_unchanged": True,
        "canonical_unchanged": True,
        "presentation_unchanged": True,
        "final": False,
    }
