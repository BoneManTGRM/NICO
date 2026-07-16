from pathlib import Path

from nico import scanner_tool_runners
from nico.scanner_tool_runners import TOOL_SPECS, run_scanner_tool
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _spec(name: str):
    return next(item for item in TOOL_SPECS if item.name == name)


def test_eslint_slot_rejects_typescript_only_lint_script(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    web = repo / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"lint":"tsc --noEmit"}}', encoding="utf-8")
    (web / "tsconfig.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")
    monkeypatch.setattr(scanner_tool_runners.shutil, "which", lambda _: "/usr/bin/tool")
    captured: list[tuple[object, object]] = []

    def runner(args, *, cwd: Path, limits):
        captured.append((tuple(args), cwd))
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="[]", stderr="")

    result = run_scanner_tool(_spec("eslint"), WorkerWorkspace(root=tmp_path), runner=runner)

    assert result["status"] == "unavailable"
    assert result["verified_for_this_report"] is False
    assert "does not execute ESLint" in result["failure_or_unavailable_reason"]
    assert captured == []


def test_typescript_slot_uses_typescript_only_lint_script(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    web = repo / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"scripts":{"lint":"tsc --noEmit"}}', encoding="utf-8")
    (web / "tsconfig.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")
    captured: dict[str, object] = {}

    def runner(args, *, cwd: Path, limits):
        captured["args"] = tuple(args)
        captured["cwd"] = cwd
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="", stderr="")

    result = run_scanner_tool(_spec("typescript"), WorkerWorkspace(root=tmp_path), runner=runner)

    assert result["status"] == "completed"
    assert result["verified_for_this_report"] is True
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
