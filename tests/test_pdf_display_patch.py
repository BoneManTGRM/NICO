from nico.report_pdf_display_patch import apply_pdf_display_patch


def test_pdf_display_patch_preserves_long_narrative_text():
    from nico import assessment_quality

    apply_pdf_display_patch()
    long_summary = "Executive summary sentence. " * 120

    rendered = assessment_quality._clean_text(long_summary, limit=900)
    short_cell = assessment_quality._clean_text(long_summary, limit=80)

    assert "[truncated]" not in rendered
    assert rendered == " ".join(long_summary.split())
    assert "[truncated]" in short_cell
