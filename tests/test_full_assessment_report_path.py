from __future__ import annotations

from nico.full_assessment_api import _with_report_path


def test_with_report_path_marks_top_level_reports_and_assessment() -> None:
    payload = {
        "reports": {
            "markdown": "# Full report",
            "html": "<html><body><h1>Full report</h1></body></html>",
        },
        "assessment": {},
    }

    result = _with_report_path(payload)

    assert result["report_path"] == "full_run"
    assert result["report_path_label"] == "Full Assessment"
    assert result["reports"]["report_path"] == "full_run"
    assert result["reports"]["report_path_label"] == "Full Assessment"
    assert result["reports"]["markdown"].startswith("> Report path: Full Assessment (`full_run`).")
    assert 'data-nico-report-path="full_run"' in result["reports"]["html"]
    assert result["assessment"]["report_path"] == "full_run"
    assert result["assessment"]["report_path_label"] == "Full Assessment"


def test_with_report_path_is_idempotent_for_visible_labels() -> None:
    payload = {
        "reports": {
            "markdown": "# Full report",
            "html": "<html><body><h1>Full report</h1></body></html>",
        },
        "assessment": {},
    }

    once = _with_report_path(payload)
    twice = _with_report_path(once)

    assert twice["reports"]["markdown"].count("Report path: Full Assessment") == 1
    assert twice["reports"]["html"].count('data-nico-report-path="full_run"') == 1


def test_with_report_path_does_not_create_report_or_assessment_objects() -> None:
    payload = {"status": "planned"}

    result = _with_report_path(payload)

    assert result["report_path"] == "full_run"
    assert result["report_path_label"] == "Full Assessment"
    assert "reports" not in result
    assert "assessment" not in result
