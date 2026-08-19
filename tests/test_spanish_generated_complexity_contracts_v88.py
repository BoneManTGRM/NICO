from __future__ import annotations

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_presentation_parity_v1 as presentation
from nico.comprehensive_decision_content_restoration_v66 import (
    _synthesized_complexity_findings,
)
from nico import comprehensive_spanish_exit_criteria_v88 as v88


_PRODUCTION_SOURCE = (
    "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
    "nico/comprehensive_review_work_v1.py:323."
)
_PRODUCTION_ES = (
    "La nueva ejecución sobre el SHA exacto ya no informa una complejidad ciclomática "
    "superior a 30 en nico/comprehensive_review_work_v1.py:323."
)


def test_production_complexity_acceptance_contract_translates_on_all_runtime_surfaces() -> None:
    result = v88.install_comprehensive_spanish_exit_criteria_v88()

    assert result["generated_complexity_contract_translation"] is True
    assert result["parametric_acceptance_criteria_translation"] is True
    assert result["generated_complexity_fact_evidence_translation"] is True
    assert result["generated_complexity_machine_tokens_preserved"] is True

    canonical_value = canonical._translate_presentation_field(
        _PRODUCTION_SOURCE,
        "acceptance_criteria",
    )
    presentation_value = presentation._safe_es(_PRODUCTION_SOURCE)
    direct_value = canonical._translate_presentation(_PRODUCTION_SOURCE)

    assert canonical_value == _PRODUCTION_ES
    assert presentation_value == _PRODUCTION_ES
    assert direct_value == _PRODUCTION_ES
    for translated in (canonical_value, presentation_value, direct_value):
        assert "nico/comprehensive_review_work_v1.py:323" in translated
        assert "30" in translated
        assert "The exact-SHA rerun" not in translated
        assert canonical._looks_like_untranslated_english(translated) is False


def test_complexity_acceptance_contract_is_parametric_not_one_literal() -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()

    variants = (
        (
            "The exact-SHA rerun no longer reports cyclomatic complexity above 41 at "
            "src/engine.py:17.",
            "41",
            "src/engine.py:17",
        ),
        (
            "The exact-SHA rerun no longer reports cyclomatic complexity above 55 at "
            "apps/web/report.ts:908.",
            "55",
            "apps/web/report.ts:908",
        ),
    )
    for source, threshold, location in variants:
        translated = canonical._translate_presentation_field(
            source,
            "acceptance_criteria",
        )
        assert "La nueva ejecución sobre el SHA exacto" in translated
        assert f"superior a {threshold}" in translated
        assert location in translated
        assert canonical._looks_like_untranslated_english(translated) is False


def test_generated_complexity_finding_family_and_spanish_publisher_stay_synchronized() -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()
    commit_sha = "a" * 40
    hotspots = [
        {
            "path": "nico/reporting.py",
            "line": 101,
            "name": "build_report",
            "cyclomatic_complexity": 44,
        },
        {
            "path": "nico/collector.py",
            "line": 202,
            "name": "collect_snapshot",
            "cyclomatic_complexity": 45,
        },
        {
            "path": "scripts/scan.py",
            "line": 303,
            "name": "main",
            "cyclomatic_complexity": 46,
        },
        {
            "path": "nico/widget.py",
            "line": 404,
            "name": "process_widget",
            "cyclomatic_complexity": 47,
        },
    ]

    findings = _synthesized_complexity_findings(hotspots, commit_sha)
    assert len(findings) == 4

    strict_fields = (
        "title",
        "fact",
        "evidence",
        "interpretation",
        "technical_impact",
        "business_impact",
        "recommendation",
        "verification",
        "acceptance_criteria",
        "rollback",
        "exit_criteria",
        "cost_of_inaction",
        "residual_risk",
    )
    for source_finding in findings:
        localized = canonical._localize_tree(source_finding)
        path = source_finding["path"]
        line = source_finding["line"]
        symbol = source_finding["symbol"]

        assert localized["path"] == path
        assert localized["line"] == line
        assert localized["symbol"] == symbol
        assert localized["finding_id"] == source_finding["finding_id"]
        assert localized["source_commit_sha"] == commit_sha

        assert "cyclomatic_complexity=" in localized["fact"]
        assert "method=evidencia de complejidad conservada del SHA exacto" in localized["fact"]
        assert "source=evidencia de arquitectura conservada del SHA exacto" in localized["fact"]
        assert "cyclomatic_complexity=" in localized["evidence"]
        assert "method=evidencia de complejidad conservada del SHA exacto" in localized["evidence"]
        assert "exact_commit_match=True" in localized["evidence"]

        criteria = localized["acceptance_criteria"]
        verification = localized["verification"]
        exit_criteria = localized["exit_criteria"]
        assert criteria == verification
        assert f"{path}:{line}" in criteria[0]
        assert "La nueva ejecución sobre el SHA exacto" in criteria[0]
        assert "pruebas de caracterización" in criteria[1]
        assert "verificaciones requeridas" in criteria[2]
        assert "coherencia" in criteria[3]
        assert "Todos los requisitos de verificación" in exit_criteria[0]
        assert "riesgo material sin resolver" in exit_criteria[1]
        assert "No se introduce ninguna nueva regresión material" in exit_criteria[2]

        for field in strict_fields:
            values = localized[field]
            if not isinstance(values, list):
                values = [values]
            for value in values:
                assert canonical._looks_like_untranslated_english(str(value)) is False, (
                    field,
                    value,
                )


def test_generated_complexity_machine_method_atoms_are_preserved() -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()
    source = (
        "cyclomatic_complexity=31; method=radon_cc; "
        "source=retained exact-SHA architecture evidence"
    )
    translated = canonical._translate_presentation_field(source, "fact")

    assert translated == (
        "cyclomatic_complexity=31; method=radon_cc; "
        "source=evidencia de arquitectura conservada del SHA exacto"
    )


def test_changed_complexity_contract_is_not_silently_accepted(monkeypatch) -> None:
    source = (
        "The exact-SHA rerun no longer reports cognitive complexity above 30 at "
        "nico/comprehensive_review_work_v1.py:323."
    )

    def fail_closed(value: str, key: str) -> str:
        raise ValueError(f"missing Spanish presentation translation for {key}: {value}")

    monkeypatch.setattr(v88, "_ORIGINAL_CANONICAL_TRANSLATE_FIELD", fail_closed)

    with pytest.raises(ValueError, match="missing Spanish presentation translation"):
        v88._translate_canonical_field_v88(source, "acceptance_criteria")
