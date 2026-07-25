from __future__ import annotations

from nico.comprehensive_decision_grade_markdown_v5 import _markdown_table
from nico.comprehensive_decision_grade_model_v5 import _score_band, _text


def test_text_preserves_zero_false_and_empty_none() -> None:
    assert _text(0) == "0"
    assert _text(0.0) == "0.0"
    assert _text(False) == "False"
    assert _text(None) == ""


def test_markdown_table_renders_zero_counts_instead_of_blank_cells() -> None:
    lines = _markdown_table(
        ["Metric", "Count", "Definition"],
        [["Informational records", 0, "Disclosures that do not independently change a technical score"]],
    )

    assert lines[-1].startswith("| Informational records | 0 |")
    assert "| Informational records |  |" not in lines[-1]


def test_zero_score_remains_a_scored_critical_value() -> None:
    band = _score_band(0)

    assert band["score_band"] == "critical"
    assert band["score_band_label"] == "CRITICAL"
    assert band["score_tone"] == "red"
