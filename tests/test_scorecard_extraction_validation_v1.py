from __future__ import annotations

import io

from pypdf import PdfReader

import nico.scorecard_extraction_validation_v1 as validation
import nico.v2_report_quality_repairs as quality
import nico.v2_report_quality_runtime_compat as runtime_compat


def _canonical() -> dict:
    return {
        "assessment": {
            "sections": [
                {
                    "id": "dependency_health",
                    "label": "Dependency / Library Ecosystem",
                    "presented_status": "STRONG",
                    "presented_score": 88,
                    "summary": (
                        "Exact-SHA dependency evidence and disposition records were "
                        "retained for the assessed repository snapshot."
                    ),
                },
                {
                    "id": "static_analysis",
                    "label": "Static Analysis",
                    "presented_status": "MODERATE",
                    "presented_score": 79,
                    "summary": "Static analyzer evidence was retained.",
                },
            ]
        }
    }


def test_generated_scorecard_verifies_wrapped_dependency_control_row() -> None:
    canonical = _canonical()
    pdf = quality._scorecard_page(canonical)

    validation._verify_all_rows(
        pdf,
        canonical,
        canonical["assessment"]["sections"],
    )

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    assert "88/100" in extracted
    assert validation._normalized("Dependency / Library Ecosystem") in validation._normalized(
        extracted
    )


def test_line_break_and_slash_spacing_do_not_create_false_missing_row(monkeypatch) -> None:
    canonical = _canonical()
    monkeypatch.setattr(
        validation,
        "_scorecard_window",
        lambda _pdf, _canonical: (
            "Canonical Technical Scorecard\n"
            "Dependency /\nLibrary Ecosystem\nStrong\n88 / 100\n"
            "Static Analysis\nModerate\n79/100"
        ),
    )

    validation._verify_all_rows(
        b"%PDF-synthetic",
        canonical,
        canonical["assessment"]["sections"],
    )


def test_real_missing_control_row_still_fails_closed(monkeypatch) -> None:
    canonical = _canonical()
    monkeypatch.setattr(
        validation,
        "_scorecard_window",
        lambda _pdf, _canonical: (
            "Canonical Technical Scorecard\nStatic Analysis\nModerate\n79/100"
        ),
    )

    try:
        validation._verify_all_rows(
            b"%PDF-synthetic",
            canonical,
            canonical["assessment"]["sections"],
        )
    except ValueError as exc:
        assert str(exc) == (
            "scorecard omitted canonical control row: Dependency / Library Ecosystem"
        )
    else:
        raise AssertionError("a genuinely missing canonical control row must block publication")


def test_install_rebinds_both_english_runtime_validation_paths() -> None:
    contract = validation.install_scorecard_extraction_validation()

    assert contract["all_canonical_rows_and_scores_required"] is True
    assert quality._validate_final_pdf is validation.validate_final_pdf
    assert runtime_compat._validate_final_pdf is validation.validate_final_pdf
