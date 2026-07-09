import sys
from pathlib import Path

from nico import scanner_tool_runners
from nico.hosted_dependency_scanner_execution_patch import (
    _npm_audit_commands,
    _pip_audit_command,
    _unavailable,
    install_hosted_dependency_scanner_execution_patch,
)
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def workspace(tmp_path: Path) -> WorkerWorkspace:
    repo = tmp_path / "repo"
    repo.mkdir()
    return WorkerWorkspace(root=tmp_path)


def test_pip_audit_falls_back_to_python_module_when_binary_missing(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    (ws.repo_dir / "requirements.txt").write_text("fastapi==0.111.0\n", encoding="utf-8")
    monkeypatch.setattr("nico.hosted_dependency_scanner_execution_patch.shutil.which", lambda name: None)

    command, cwd, reason, source = _pip_audit_command(ws.repo_dir)

    assert command is not None
    assert command[:3] == (sys.executable, "-m", "pip_audit")
    assert cwd == ws.repo_dir
    assert reason is None
    assert source == "python_module_pip_audit"


def test_npm_audit_finds_nested_lockfile_with_package_json(tmp_path):
    ws = workspace(tmp_path)
    app_dir = ws.repo_dir / "apps" / "web"
    app_dir.mkdir(parents=True)
    (app_dir / "package.json").write_text('{"dependencies":{"next":"latest"}}', encoding="utf-8")
    (app_dir / "package-lock.json").write_text('{"lockfileVersion":3,"packages":{}}', encoding="utf-8")

    commands, reason = _npm_audit_commands(ws.repo_dir)

    assert reason is None
    assert commands
    assert commands[0][1] == app_dir
    assert commands[0][0][0:2] == ("npm", "audit")


def test_dependency_unavailable_records_are_current_run():
    spec = ScannerToolSpec("pip-audit", ("pip-audit",), "dependency")

    result = _unavailable(spec, "not installed")

    assert result["status"] == "unavailable"
    assert result["current_run"] is True
    assert result["verified_for_this_report"] is False
    assert result["failure_or_unavailable_reason"] == "not installed"


def test_patched_pip_audit_returns_completed_payload(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    (ws.repo_dir / "requirements.txt").write_text("fastapi==0.111.0\n", encoding="utf-8")
    monkeypatch.setattr("nico.hosted_dependency_scanner_execution_patch.shutil.which", lambda name: "/usr/bin/pip-audit" if name == "pip-audit" else None)
    install_hosted_dependency_scanner_execution_patch()

    def fake_runner(command, *, cwd, limits):
        assert command[0] == "pip-audit"
        return WorkerCommandResult(args=tuple(command), returncode=0, stdout='{"dependencies":[]}', stderr="")

    spec = ScannerToolSpec("pip-audit", ("pip-audit", "-r", "requirements.txt", "-f", "json"), "dependency")
    result = scanner_tool_runners.run_scanner_tool(spec, ws, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["verified_for_this_report"] is True
    assert result["findings_count"] == 0
    assert result["execution_source"] == "pip_audit_cli"


def test_osv_api_fallback_marks_current_run(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    (ws.repo_dir / "requirements.txt").write_text("fastapi==0.111.0\n", encoding="utf-8")
    monkeypatch.setattr("nico.hosted_dependency_scanner_execution_patch.shutil.which", lambda name: None)

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"results": [{}]}

    monkeypatch.setattr("nico.scanner_tool_runners.requests.post", lambda *args, **kwargs: Response())
    install_hosted_dependency_scanner_execution_patch()

    spec = ScannerToolSpec("osv-scanner", ("osv-scanner", "--format", "json", "."), "dependency")
    result = scanner_tool_runners.run_scanner_tool(spec, ws)

    assert result["status"] == "completed"
    assert result["execution_source"] == "osv_api_fallback"
    assert result["current_run"] is True
    assert result["verified_for_this_report"] is True
