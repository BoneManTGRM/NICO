from __future__ import annotations

from nico.comprehensive_final_report_filename_v48 import canonical_final_report_filename


def test_final_report_filename_is_idempotent_and_never_draft() -> None:
    expected = "nico-comprehensive-assessment-run-FINAL-PENDING-APPROVAL.pdf"

    assert canonical_final_report_filename("nico-comprehensive-assessment-run-DRAFT.pdf") == expected
    assert canonical_final_report_filename(expected) == expected
    assert canonical_final_report_filename(
        "nico-comprehensive-assessment-run-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf"
    ) == expected
    assert "DRAFT" not in canonical_final_report_filename("report-DRAFT.pdf").upper()
