from nico.comprehensive_decision_grade_report_v5 import (
    APPENDIX_HEADING,
    REVIEW_HEADING,
    VERSION,
    build_comprehensive_report_package,
)


def test_decision_grade_report_import_surface() -> None:
    assert VERSION == "nico.comprehensive_decision_grade.v5"
    assert APPENDIX_HEADING == "## Evidence Appendix"
    assert REVIEW_HEADING == "## Human Review and Acceptance Gate"
    assert callable(build_comprehensive_report_package)
