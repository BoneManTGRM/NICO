from __future__ import annotations

from nico import comprehensive_native_providers as providers
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_presentation_parity_v1 as presentation
from nico import comprehensive_spanish_exit_criteria_v88 as v88


def test_v88_binds_shared_report_execution_boundary() -> None:
    result = v88.install_comprehensive_spanish_exit_criteria_v88()

    assert result["bound"] is True
    assert result["report_runtime_boundary_bound"] is True
    assert result["detached_decision_report_reassertion"] is True
    assert providers._build_report is v88._native_build_report_v88


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
