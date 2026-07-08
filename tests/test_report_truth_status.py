from nico.build_marker import BUILD_COMMIT, BUILD_MARKER
from nico.diagnostics import diagnostics
from nico.report_truth_status import REPORT_TRUTH_GUARD_EXPECTED_BUILD_MARKER, REPORT_TRUTH_GUARD_VERSION, build_report_truth_status

RUNTIME_DEPLOY_COMMIT_SENTINEL = "0000000000000000000000000000000000000000"


def test_build_marker_identifies_final_hosted_truth_gate():
    assert BUILD_MARKER == "nico-final-hosted-truth-gate"
    assert BUILD_COMMIT == RUNTIME_DEPLOY_COMMIT_SENTINEL
    assert len(BUILD_COMMIT) == 40


def test_report_truth_guard_status_is_deploy_visible():
    status = build_report_truth_status()

    assert status["version"] == REPORT_TRUTH_GUARD_VERSION
    assert status["expected_build_marker"] == REPORT_TRUTH_GUARD_EXPECTED_BUILD_MARKER
    assert status["guard_active"] is True
    assert status["status"] == "ok"
    assert status["checks"]["dependency_score_consistency_guard_available"] is True
    assert status["checks"]["malformed_python_extra_osv_guard_available"] is True
    assert status["checks"]["client_acceptance_delivery_gate_installed"] is True


def test_diagnostics_include_report_truth_guard_status():
    payload = diagnostics()

    assert payload["version"] == "0.8.3-final-hosted-truth-gate"
    assert payload["deployment"]["build_marker"] == "nico-final-hosted-truth-gate"
    assert payload["deployment"]["expected_build_commit"] == RUNTIME_DEPLOY_COMMIT_SENTINEL
    assert payload["deployment"]["expected_build_commit_short"] == "runtime"
    assert payload["report_truth_guard"]["version"] == REPORT_TRUTH_GUARD_VERSION
    assert "hosted backend has not loaded" in payload["report_truth_guard"]["rule"]
