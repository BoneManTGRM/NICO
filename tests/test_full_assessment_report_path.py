from __future__ import annotations

from nico.full_assessment_api import _with_report_path


def test_with_report_path_marks_top_level_reports_and_assessment() -> None:
    payload = {"reports": {}, "assessment": {}}

    result = _with_report_path(payload)

    assert result["report_path"] == "full_run"
    assert result["reports"]["report_path"] == "full_run"
    assert result["assessment"]["report_path"] == "full_run"


def test_with_report_path_does_not_create_fake_report_or_assessment_objects() -> None:
    payload = {"status": "planned"}

    result = _with_report_path(payload)

    assert result["report_path"] == "full_run"
    assert "reports" not in result
    assert "assessment" not in result
