from __future__ import annotations

import json

import pytest

import nico.no_server_assessment as no_server


@pytest.mark.parametrize(
    "report,verification,status",
    [
        ({"status": "completed"}, {"passed": True}, "verified"),
        ({"status": "completed"}, {"passed": False, "checks": ["scan_missing"]}, "verification_failed"),
        ({"status": "completed"}, {}, "verification_failed"),
        ({"status": "completed"}, {"passed": "false"}, "verification_failed"),
        ({"status": "empty"}, {"passed": False}, "no_assessment_report"),
        ({"status": "empty"}, {"passed": True}, "no_assessment_report"),
    ],
)
def test_verification_status_and_cli_exit(monkeypatch, capsys, report, verification, status):
    report = {**report, "scan_id": "scan_synthetic", "assessment_id": "synthetic", "authorization_scope": "synthetic only", "evidence_log": ["fixture"]}
    verification = {**verification, "scan_id": "scan_synthetic"}
    # Artifact integrity is exercised separately with real persisted reports.
    monkeypatch.setattr(no_server, "_publication_check", lambda _report: "assessment_artifacts_verified")
    monkeypatch.setattr(no_server, "_read_latest_report_unchecked", lambda: report)
    monkeypatch.setattr(no_server, "verify_latest", lambda: verification)
    available = report["status"] == "completed"
    expected = {
        "status": status,
        "assessment_id": "synthetic",
        "scan_id": "scan_synthetic",
        "report_available": available,
        "nico_verification": verification,
        "checks": [
            "no_server_report_available" if available else "no_server_report_missing",
            "raw_secret_masking_checked",
            "authorization_scope_recorded",
            "evidence_log_present",
            "assessment_scan_matches_verification",
            "assessment_artifacts_verified",
        ],
    }
    assert no_server.verify_latest_assessment() == expected
    if status == "verified":
        assert no_server.main(["verify", "latest"]) is None
    else:
        with pytest.raises(SystemExit) as caught:
            no_server.main(["verify", "latest"])
        assert caught.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == json.dumps(expected, indent=2, sort_keys=True) + "\n"
    assert captured.err == ""


def test_empty_latest_query_compatibility(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(no_server, "REPORT_DIR", tmp_path)
    assert no_server.main(["latest"]) is None
    assert json.loads(capsys.readouterr().out) == {
        "status": "empty", "message": "No no-server assessment has been run yet.",
    }


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_missing_report_query_compatibility(tmp_path, monkeypatch, capsys, fmt):
    monkeypatch.setattr(no_server, "REPORT_DIR", tmp_path)
    assert no_server.main(["report", "latest", "--format", fmt]) is None
    assert capsys.readouterr().out == "No no-server assessment report exists yet.\n"
