from __future__ import annotations

from nico.express_glyph_score_leakage_patch import _apply_in_place, normalize_express_glyph_score_truth


def test_text_glyph_score_bars_are_removed_but_numeric_geometry_is_retained() -> None:
    result = normalize_express_glyph_score_truth(
        {
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code Audit",
                    "score": 86,
                    "bar": "■■■■■■■■■■■■■■■■■□□□",
                    "glyph_bar": "■■■■■■■■■■■■■■■■■□□□",
                    "contribution_bar": "■■■■■■■■■■■■■■■■■□□□",
                    "bar_geometry": {"value": 86, "ratio": 0.86, "width": 103.2},
                }
            ]
        }
    )
    section = result["sections"][0]
    assert "bar" not in section
    assert "glyph_bar" not in section
    assert "contribution_bar" not in section
    assert section["bar_geometry"]["ratio"] == 0.86
    assert result["express_glyph_score_truth"]["status"] == "complete"


def test_scanner_worker_is_supplemental_and_has_no_score() -> None:
    result = normalize_express_glyph_score_truth(
        {
            "sections": [
                {
                    "id": "scanner_worker_evidence",
                    "label": "Scanner Worker Evidence",
                    "score": 27,
                    "status": "red",
                    "bar": "■■■■■□□□□□□□□□□□□□□□",
                }
            ]
        }
    )
    section = result["sections"][0]
    assert section["status"] == "SUPPLEMENTAL"
    assert section["display_status"] == "SUPPLEMENTAL · NOT SCORED"
    assert section["score"] is None
    assert section["diagnostic_finding_count"] == 27
    assert section["directly_scored"] is False
    assert "bar" not in section


def test_nested_glyph_fields_are_removed_without_mutating_input() -> None:
    source = {
        "express_score_transparency": {
            "records": [
                {"section_id": "ci_cd", "presented_score": 95, "glyph_bar": "■■■■■■■■■■■■■■■■■■■□"}
            ]
        }
    }
    result = normalize_express_glyph_score_truth(source)
    assert "glyph_bar" in source["express_score_transparency"]["records"][0]
    assert "glyph_bar" not in result["express_score_transparency"]["records"][0]


def test_in_place_application_preserves_report_dictionary_identity() -> None:
    result = {
        "reports": {"markdown": "# Express", "html": "<h1>Express</h1>"},
        "sections": [{"id": "code_audit", "bar": "■■■", "score": 86}],
    }
    reports_reference = result["reports"]
    normalized = normalize_express_glyph_score_truth(result)

    _apply_in_place(result, normalized)
    reports_reference["pdf_style"] = "professional_report_v12_decision_ready"

    assert result["reports"] is reports_reference
    assert result["reports"]["pdf_style"] == "professional_report_v12_decision_ready"
    assert "bar" not in result["sections"][0]
