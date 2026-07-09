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
