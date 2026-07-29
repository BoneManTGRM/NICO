from __future__ import annotations

from nico.v2_premium_pdf_finality import install_v2_premium_pdf_finality


def test_decision_grade_pdf_delegates_are_rebound_to_final_source_renderer():
    from nico import comprehensive_decision_grade_pdf_v5 as decision_grade
    from nico import comprehensive_premium_pdf_v6 as premium

    status = install_v2_premium_pdf_finality()

    assert status["status"] == "installed"
    assert status["decision_grade_cached_delegates_rebound"] is True
    assert status["pdf_text_extraction_contains_no_legacy_draft_footer"] is True
    assert decision_grade._premium_build_pdf is premium._build_pdf
    assert decision_grade._premium_pdf_with_final_count is premium._pdf_with_final_count
    assert getattr(premium._build_pdf, "__nico_v2_premium_pdf_build_finality_v3__", False) is True
