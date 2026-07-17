from __future__ import annotations

from nico.report_markup_safety_v2 import _clean_markup


def test_clean_markup_removes_visible_presentation_tags() -> None:
    assert _clean_markup("<b>Proceed</b> — review required") == "Proceed — review required"
    assert _clean_markup("<strong>Risk</strong>: high") == "Risk: high"


def test_clean_markup_preserves_non_markup_comparisons() -> None:
    assert _clean_markup("score < 80 and confidence > 0.5") == "score < 80 and confidence > 0.5"


def test_clean_markup_preserves_non_strings() -> None:
    assert _clean_markup(None) is None
    assert _clean_markup(73) == 73
