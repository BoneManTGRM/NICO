from nico.no_server_assessment import AuthorizationError, run_local_assessment


def test_local_assessment_requires_authorization(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("print('hello')\n", encoding="utf-8")
    try:
        run_local_assessment(str(project), authorized=False)
        assert False, "expected authorization gate to block"
    except AuthorizationError as exc:
        assert "--authorized" in str(exc)


def test_local_assessment_generates_report(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("# TODO: add rate limiting\n", encoding="utf-8")
    (project / "requirements.txt").write_text("requests>=2.31\n", encoding="utf-8")
    (project / "README.md").write_text("# Test project\n", encoding="utf-8")

    result = run_local_assessment(str(project), authorized=True)

    assert result["status"] == "completed"
    assert result["mode"] == "no-server-local-first"
    assert result["target_type"] == "local"
    assert "Code Audit" in result["maturity_semaphore"]
    assert result["evidence_log"]
