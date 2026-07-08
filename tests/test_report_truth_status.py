from nico.build_marker import BUILD_COMMIT, BUILD_MARKER
from nico.diagnostics import diagnostics
from nico.report_truth_status import REPORT_TRUTH_GUARD_EXPECTED_BUILD_COMMIT, REPORT_TRUTH_GUARD_VERSION, build_report_truth_status


def test_build_marker_points_to_pr145_truth_guard_merge():
    assert BUILD_MARKER == "nico-main-pr145-report-truth-guard"
    assert BUILD_COMMIT == "4395fe0744c4219d4f27a1d80c53ca18886420f1"


def test_report_truth_guard_status_is_deploy_visible():
    status = build_report_truth_status()

    assert status["version"] == REPORT_TRUTH_GUARD_VERSION
    assert status["expected_build_commit"] == REPORT_TRUTH_GUARD_EXPECTED_BUILD_COMMIT
    assert status["guard_active"] is True
    assert status["status"] == "ok"
    assert status["checks"]["dependency_score_consistency_guard_available"] is True
    assert status["checks"]["malformed_python_extra_osv_guard_available"] is True


def test_diagnostics_include_report_truth_guard_status():
    payload = diagnostics()

    assert payload["version"] == "0.8.2-report-truth-status"
    assert payload["deployment"]["build_marker"] == "nico-main-pr145-report-truth-guard"
    assert payload["report_truth_guard"]["version"] == REPORT_TRUTH_GUARD_VERSION
    assert "If this status is missing" in payload["report_truth_guard"]["rule"]
