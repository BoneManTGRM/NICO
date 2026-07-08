from pathlib import Path

from nico.scanner_tool_runners import ScannerToolSpec, run_scanner_tool
from nico.worker_execution import WorkerWorkspace


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"results": [{"vulns": []}, {"vulns": []}]}


def test_osv_scanner_falls_back_to_current_run_osv_api_without_fake_cli(monkeypatch, tmp_path):
    root = tmp_path
    repo = root / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("uvicorn==0.50.2\n", encoding="utf-8")
    (repo / "package-lock.json").write_text(
        '{"packages":{"node_modules/react":{"version":"18.3.1"}}}',
        encoding="utf-8",
    )

    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda executable: None)
    seen = {}

    def fake_post(url, json, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("nico.scanner_tool_runners.requests.post", fake_post)

    result = run_scanner_tool(
        ScannerToolSpec("osv-scanner", ("osv-scanner", "--format", "json", "."), "dependency"),
        WorkerWorkspace(root=Path(root)),
    )

    assert result["tool"] == "osv-scanner"
    assert result["status"] == "completed"
    assert result["execution_source"] == "osv_api_fallback"
    assert result["findings"] == []
    assert result["returncode"] == 0
    assert seen["json"]["queries"][0]["package"] == {"name": "uvicorn", "ecosystem": "PyPI"}
    assert seen["json"]["queries"][0]["version"] == "0.50.2"
    assert "[standard]" not in str(seen["json"])


def test_project_static_tools_run_from_frontend_package_when_enabled(monkeypatch, tmp_path):
    root = tmp_path
    repo = root / "repo"
    web = repo / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda executable: "/usr/bin/npx")

    calls = []

    def fake_runner(args, *, cwd, limits):
        calls.append((tuple(args), cwd))
        from nico.worker_execution import WorkerCommandResult

        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="[]", stderr="")

    result = run_scanner_tool(
        ScannerToolSpec("eslint", ("npx", "eslint", ".", "--format", "json"), "static", requires_project_commands=True),
        WorkerWorkspace(root=Path(root)),
        runner=fake_runner,
    )

    assert result["status"] == "completed"
    assert calls[0][1] == web
