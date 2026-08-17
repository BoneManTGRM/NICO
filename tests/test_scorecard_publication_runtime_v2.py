from __future__ import annotations

from pathlib import Path

import pytest

import nico.scorecard_extraction_validation_v1 as validation


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "nico" / "api" / "terminal_authority_bootstrap.py"
DOCKERFILE = ROOT / "Dockerfile"


def _canonical() -> dict:
    return {
        "assessment": {
            "sections": [
                {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "presented_score": 88},
                {"id": "static_analysis", "label": "Static Analysis", "presented_score": 79},
            ]
        }
    }


def test_scorecard_validation_is_independent_of_column_extraction_order(monkeypatch) -> None:
    canonical = _canonical()
    monkeypatch.setattr(
        validation,
        "_scorecard_window",
        lambda _pdf, _canonical: (
            "Canonical Technical Scorecard\n"
            "Dependency Strong 88 / 100 Library Ecosystem\n"
            "Static Moderate 79 / 100 Analysis"
        ),
    )
    validation._verify_all_rows(b"%PDF-synthetic", canonical, canonical["assessment"]["sections"])


@pytest.mark.parametrize("spanish", [False, True])
def test_publication_fallback_preserves_all_non_scorecard_gates(monkeypatch, spanish: bool) -> None:
    canonical = _canonical()

    def brittle_validator(*_args, **_kwargs):
        raise ValueError("scorecard omitted canonical control row: Dependency / Library Ecosystem")

    monkeypatch.setattr(validation, "_ORIGINAL_VALIDATE", brittle_validator)
    monkeypatch.setattr(
        validation,
        "_scorecard_window",
        lambda _pdf, _canonical: (
            "Canonical Technical Scorecard\n"
            "Dependency /\nLibrary Ecosystem\n88 / 100\n"
            "Static Analysis\n79 / 100"
        ),
    )
    validation.validate_final_pdf(
        b"%PDF-synthetic",
        canonical,
        expected_sections=canonical["assessment"]["sections"],
        spanish=spanish,
    )


def test_production_api_bootstrap_keeps_scorecard_validator_after_report_compatibility() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert 'VERSION = "nico.api.terminal_authority_bootstrap.v26"' in source
    assert "install_scorecard_extraction_validation" in source
    assert "SCORECARD_EXTRACTION_VALIDATION = install_scorecard_extraction_validation()" in source
    assert source.index("SCORECARD_EXTRACTION_VALIDATION =") > source.index("EXPRESS_FAILURE_STAGE_TRUTH =")
    assert source.index("TERMINAL_REPORT_LANGUAGE_AUTHORITY =") > source.index(
        "SCORECARD_EXTRACTION_VALIDATION ="
    )
    assert "install_comprehensive_spanish_client_surface_localization_v86" in source
    assert source.index("SPANISH_CLIENT_SURFACE_LOCALIZATION =") > source.index(
        "TERMINAL_REPORT_LANGUAGE_AUTHORITY ="
    )
    assert '"column_extraction_order_independent"' in source
    assert '"multi_page_scorecard_supported"' in source
    assert '"all_canonical_rows_and_scores_required"' in source
    assert '"spanish_and_english_supported"' in source
    assert '"persisted_run_identity_outranks_root_projection"' in source
    assert '"specific_scanner_label_precedence"' in source
    assert '"wrapped_pdf_heading_validation"' in source
    assert "uvicorn nico.api.terminal_authority_bootstrap:app" in dockerfile
