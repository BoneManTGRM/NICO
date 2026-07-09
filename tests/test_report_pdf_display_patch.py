from nico.report_pdf_display_patch import apply_pdf_display_patch


def test_pdf_display_patch_does_not_truncate_executive_summary_limit():
    from nico import assessment_quality

    apply_pdf_display_patch()
    long_text = "Executive summary detail. " * 80

    rendered = assessment_quality._clean_text(long_text, limit=900)

    assert "[truncated]" not in rendered
    assert rendered == " ".join(long_text.split())


def test_pdf_display_patch_keeps_short_table_cell_limits():
    from nico import assessment_quality

    apply_pdf_display_patch()
    long_text = "Scorecard table detail. " * 40

    rendered = assessment_quality._clean_text(long_text, limit=190)

    assert "[truncated]" in rendered
    assert len(rendered) <= 190
