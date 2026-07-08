from pathlib import Path

from nico import scanner_tool_runners
from nico.scanner_tool_runners import TOOL_SPECS, run_scanner_tool
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _spec(name: str):
    return next(item for item in TOOL_SPECS if item.name == name)


def test_eslint_slot_uses_project_lint_script_when_no_eslint_config(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    web = repo / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"lint":"tsc --noEmit"}}', encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")
    monkeypatch.setattr(scanner_tool_runners.shutil, "which", lambda _: "/usr/bin/tool")
    captured: dict[str, object] = {}

    def runner(args, *, cwd: Path, limits):
        captured["args"] = tuple(args)
        captured["cwd"] = cwd
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="", stderr="")

    result = run_scanner_tool(_spec("eslint"), WorkerWorkspace(root=tmp_path), runner=runner)

    assert result["status"] == "completed"
    assert result["findings"] == []
    assert captured["args"] == ("npm", "run", "lint")
    assert captured["cwd"] == web


def test_project_command_tools_stay_unavailable_without_authorized_env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    web = repo / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"lint":"tsc --noEmit"}}', encoding="utf-8")
    monkeypatch.delenv("NICO_ALLOW_PROJECT_COMMANDS", raising=False)

    result = run_scanner_tool(_spec("typescript"), WorkerWorkspace(root=tmp_path))

    assert result["status"] == "unavailable"
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in result["reason"]


def test_eslint_text_failure_becomes_static_finding():
    result = WorkerCommandResult(args=("npm", "run", "lint"), returncode=2, stdout="type error", stderr="")

    findings = scanner_tool_runners.parse_tool_findings("eslint", result)

    assert findings == [{"message": "type error"}]
