from pathlib import Path

from nico import scanner_tool_runners
from nico.hosted_static_scanner_execution_patch import (
    _bandit_command,
    _eslint_command,
    _semgrep_command,
    _typescript_command,
    _unavailable,
    install_hosted_static_scanner_execution_patch,
)
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def workspace(tmp_path: Path) -> WorkerWorkspace:
    repo = tmp_path / "repo"
    repo.mkdir()
    return WorkerWorkspace(root=tmp_path)


def test_static_unavailable_records_are_current_run():
    spec = ScannerToolSpec("semgrep", ("semgrep",), "static")

    result = _unavailable(spec, "semgrep missing")

    assert result["status"] == "unavailable"
    assert result["current_run"] is True
    assert result["verified_for_this_report"] is False
    assert result["failure_or_unavailable_reason"] == "semgrep missing"


def test_bandit_missing_binary_is_explicit(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    (ws.repo_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda name: None)

    command, cwd, reason, source = _bandit_command(ws)

    assert command is None
    assert cwd == ws.repo_dir
    assert "bandit is not installed" in reason
    assert source == "bandit_cli"


def test_semgrep_missing_binary_is_explicit(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    (ws.repo_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda name: None)

    command, cwd, reason, source = _semgrep_command(ws)

    assert command is None
    assert cwd == ws.repo_dir
    assert "semgrep is not installed" in reason
    assert source == "semgrep_cli"


def test_eslint_requires_project_commands(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    web = ws.repo_dir / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"lint":"next lint"}}', encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "false")

    command, cwd, reason, source = _eslint_command(ws)

    assert command is None
    assert cwd == web
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in reason
    assert source == "eslint_project_commands_disabled"


def test_eslint_lint_script_uses_existing_contract(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    web = ws.repo_dir / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"lint":"next lint"}}', encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")

    command, cwd, reason, source = _eslint_command(ws)

    assert command == ("npm", "run", "lint")
    assert cwd == web
    assert reason is None
    assert source == "eslint_npm_script"


def test_typescript_prefers_typecheck_script_when_project_commands_allowed(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    web = ws.repo_dir / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"typecheck":"tsc --noEmit"}}', encoding="utf-8")
    (web / "tsconfig.json").write_text('{"compilerOptions":{}}', encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")

    command, cwd, reason, source = _typescript_command(ws)

    assert command == ("npm", "run", "typecheck")
    assert cwd == web
    assert reason is None
    assert source == "typescript_npm_script"


def test_patched_bandit_completed_payload(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    (ws.repo_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda name: "/usr/bin/bandit" if name == "bandit" else None)
    install_hosted_static_scanner_execution_patch()

    def fake_runner(command, *, cwd, limits):
        assert command[0] == "bandit"
        return WorkerCommandResult(args=tuple(command), returncode=0, stdout='{"results":[]}', stderr="")

    spec = ScannerToolSpec("bandit", ("bandit",), "static", timeout_seconds=120)
    result = scanner_tool_runners.run_scanner_tool(spec, ws, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["verified_for_this_report"] is True
    assert result["findings_count"] == 0
    assert result["execution_source"] == "bandit_cli"


def test_patched_typescript_disabled_project_commands_is_unavailable(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    web = ws.repo_dir / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"typecheck":"tsc --noEmit"}}', encoding="utf-8")
    (web / "tsconfig.json").write_text('{"compilerOptions":{}}', encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "false")
    install_hosted_static_scanner_execution_patch()

    spec = ScannerToolSpec("typescript", ("tsc",), "static", timeout_seconds=120)
    result = scanner_tool_runners.run_scanner_tool(spec, ws)

    assert result["status"] == "unavailable"
    assert result["verified_for_this_report"] is False
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in result["failure_or_unavailable_reason"]
