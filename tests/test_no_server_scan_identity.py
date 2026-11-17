import json

import pytest

import nico.no_server_assessment as no_server


@pytest.mark.parametrize("report_id,verified_id,expected", [
    ("scan_a", "scan_a", "verified"),
    ("scan_a", "scan_b", "verification_failed"),
    (None, "scan_b", "verification_failed"),
    ("scan_a", None, "verification_failed"),
    (None, None, "verification_failed"),
    ("", "", "verification_failed"),
    ("   ", "   ", "verification_failed"),
    (123, 123, "verification_failed"),
])
def test_report_must_identify_verified_scan(monkeypatch, capsys, report_id, verified_id, expected):
    report = {"status": "completed", "scan_id": report_id}
    verification = {"passed": True, "scan_id": verified_id}
    # Artifact integrity is exercised separately with real persisted reports.
    monkeypatch.setattr(no_server, "_publication_check", lambda _report: "assessment_artifacts_verified")
    monkeypatch.setattr(no_server, "_read_latest_report_unchecked", lambda: report)
    monkeypatch.setattr(no_server, "verify_latest", lambda: verification)
    result = no_server.verify_latest_assessment()
    assert result["status"] == expected
    assert result["nico_verification"] == verification
    assert result["scan_id"] == report_id
    assert ("assessment_scan_matches_verification" in result["checks"]) == (expected == "verified")
    if expected == "verified":
        assert no_server.main(["verify", "latest"]) is None
    else:
        with pytest.raises(SystemExit) as caught:
            no_server.main(["verify", "latest"])
        assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == expected


def test_assessment_persists_its_scan_id(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("print('synthetic')\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(no_server, "REPORT_DIR", tmp_path / "reports")
    result = no_server.run_local_assessment(str(project), authorized=True)
    assert result["scan_id"] == no_server.verify_latest()["scan_id"]
    assert no_server.latest_report()["scan_id"] == result["scan_id"]
    assert no_server.verify_latest_assessment()["status"] == "verified"
