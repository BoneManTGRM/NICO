import subprocess

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.hosted_scanner_runtime_diagnostics import (
    REQUIRED_RUNTIME_TOOLS,
    hosted_scanner_runtime_diagnostics,
    register_hosted_scanner_runtime_diagnostics_routes,
)


def test_hosted_scanner_runtime_diagnostics_reports_required_tools(monkeypatch):
    monkeypatch.setattr("nico.hosted_scanner_runtime_diagnostics.shutil.which", lambda binary: f"/usr/bin/{binary}" if binary in {"python", "git", "npm"} else None)
    monkeypatch.setattr(
        "nico.hosted_scanner_runtime_diagnostics._safe_version",
        lambda tool, binary: {"status": "installed", "returncode": 0, "version": f"{tool} test-version", "reason": ""},
    )

    result = hosted_scanner_runtime_diagnostics()
    tools = {item["tool"]: item for item in result["tools"]}

    assert result["status"] == "ok"
    assert len(result["tools"]) == len(REQUIRED_RUNTIME_TOOLS)
    assert tools["npm-audit"]["installed"] is True
    assert tools["pip-audit"]["installed"] is False
    assert "pip-audit" in result["summary"]["scanner_tools_missing"]
    assert result["summary"]["runtime_ready"] is False
    assert result["blockers"]


def test_hosted_scanner_runtime_route_registers_once(monkeypatch):
    monkeypatch.setattr("nico.hosted_scanner_runtime_diagnostics.shutil.which", lambda binary: None)
    app = FastAPI()

    register_hosted_scanner_runtime_diagnostics_routes(app)
    register_hosted_scanner_runtime_diagnostics_routes(app)
    client = TestClient(app)
    response = client.get("/diagnostics/hosted-scanner-runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["summary"]["missing_count"] >= 1
    matching_routes = [route for route in app.routes if getattr(route, "path", "") == "/diagnostics/hosted-scanner-runtime"]
    assert len(matching_routes) == 1


def test_runtime_diagnostics_keeps_scoring_guardrail(monkeypatch):
    monkeypatch.setattr("nico.hosted_scanner_runtime_diagnostics.shutil.which", lambda binary: None)

    result = hosted_scanner_runtime_diagnostics()

    assert "never converts" in result["guardrail"]
    assert "Scanner binaries missing from PATH" in "\n".join(result["blockers"])


@pytest.mark.parametrize("outcome", ["success", "command_failed", "not_installed", "timeout", "failed", "missing_path"])
@pytest.mark.parametrize("target", ["all", "git"])
def test_runtime_readiness_requires_successful_version_probes(monkeypatch, outcome, target):
    for name in ("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "NICO_ALLOW_PROJECT_COMMANDS", "NICO_ENABLE_FULL_HISTORY_SECRET_SCAN"):
        monkeypatch.setenv(name, "true")

    def affected(binary):
        return target == "all" or binary == target

    def which(binary):
        return None if outcome == "missing_path" and affected(binary) else f"/mock/{binary}"

    def run(command, **kwargs):
        assert kwargs["timeout"] == 12
        assert kwargs["check"] is False
        assert set(kwargs["env"]) == {"PATH", "HOME", "LANG", "LC_ALL"}
        if affected(command[0]):
            if outcome == "not_installed":
                raise FileNotFoundError()
            if outcome == "timeout":
                raise subprocess.TimeoutExpired(command, 12)
            if outcome == "failed":
                raise OSError("cannot execute")
            if outcome == "command_failed":
                return subprocess.CompletedProcess(command, 2, "", "probe failed")
            assert outcome != "missing_path", "Missing binaries must not be executed"
        return subprocess.CompletedProcess(command, 0, "mock version 1", "")

    monkeypatch.setattr("nico.hosted_scanner_runtime_diagnostics.shutil.which", which)
    monkeypatch.setattr("nico.hosted_scanner_runtime_diagnostics.subprocess.run", run)
    result = hosted_scanner_runtime_diagnostics()
    ready = outcome == "success"
    assert result["summary"]["runtime_ready"] is ready
    assert bool(result["blockers"]) is not ready
    for item in result["tools"]:
        expected_ready = ready or not affected(item["binary"])
        assert item["installed"] is expected_ready
        if not expected_ready:
            assert item["status"] == ("not_installed" if outcome == "missing_path" else outcome)
            assert item["reason"]
            assert item["tool"] in " ".join(result["blockers"])
        if item["category"] != "runtime":
            key = "scanner_tools_installed" if expected_ready else "scanner_tools_missing"
            assert item["tool"] in result["summary"][key]
    if not ready:
        missing_message = "missing from PATH" in " ".join(result["blockers"])
        assert missing_message is (outcome in {"not_installed", "missing_path"})


@pytest.mark.parametrize("disabled", ["NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "NICO_ALLOW_PROJECT_COMMANDS", "NICO_ENABLE_FULL_HISTORY_SECRET_SCAN"])
def test_successful_probes_do_not_override_disabled_execution(monkeypatch, disabled):
    for name in ("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "NICO_ALLOW_PROJECT_COMMANDS", "NICO_ENABLE_FULL_HISTORY_SECRET_SCAN"):
        monkeypatch.setenv(name, "false" if name == disabled else "true")
    monkeypatch.setattr("nico.hosted_scanner_runtime_diagnostics.shutil.which", lambda binary: f"/mock/{binary}")
    monkeypatch.setattr("nico.hosted_scanner_runtime_diagnostics.subprocess.run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "mock version", ""))
    result = hosted_scanner_runtime_diagnostics()
    assert result["summary"]["runtime_ready"] is False
    assert any(disabled in blocker for blocker in result["blockers"])
