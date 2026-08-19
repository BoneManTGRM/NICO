from __future__ import annotations

import pytest

from nico import comprehensive_native_providers as providers
from nico import comprehensive_spanish_canonical_report_v87 as canonical
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


def test_v88_binds_shared_report_execution_boundary() -> None:
    result = v88.install_comprehensive_spanish_exit_criteria_v88()

    assert result["bound"] is True
    assert result["report_runtime_boundary_bound"] is True
    assert result["detached_decision_report_reassertion"] is True
    assert result["targeted_rollback_translation"] is True
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

    original_canonical = v88._ORIGINAL_CANONICAL_TRANSLATE_FIELD
    original_presentation = v88._ORIGINAL_PRESENTATION_SAFE_ES
    assert original_canonical is not None
    assert original_presentation is not None

    # Model a late compatibility installer replacing the two translator aliases after
    # application startup but before detached decision-report execution begins.
    monkeypatch.setattr(canonical, "_translate_presentation_field", original_canonical)
    monkeypatch.setattr(presentation, "_safe_es", original_presentation)

    observed: dict[str, object] = {}

    def fake_build_report(context: dict[str, object], final: bool) -> dict[str, object]:
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
        "canonical_reasserted": True,
        "presentation_reasserted": True,
        "final": False,
    }


def test_english_report_path_does_not_rebind_spanish_translators(monkeypatch) -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()
    original_canonical = v88._ORIGINAL_CANONICAL_TRANSLATE_FIELD
    original_presentation = v88._ORIGINAL_PRESENTATION_SAFE_ES
    assert original_canonical is not None
    assert original_presentation is not None

    monkeypatch.setattr(canonical, "_translate_presentation_field", original_canonical)
    monkeypatch.setattr(presentation, "_safe_es", original_presentation)

    observed: dict[str, object] = {}

    def fake_build_report(context: dict[str, object], final: bool) -> dict[str, object]:
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
        "canonical_unchanged": True,
        "presentation_unchanged": True,
        "final": False,
    }
