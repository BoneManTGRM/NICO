from __future__ import annotations

from types import SimpleNamespace

import pytest

from nico.scanner_preflight_v1 import ScannerRequirement, require_complete_preflight, run_preflight


def test_missing_required_scanner_blocks_preflight(monkeypatch) -> None:
    monkeypatch.setattr("nico.scanner_preflight_v1.shutil.which", lambda _name: None)
    result = run_preflight((ScannerRequirement("bandit", "bandit"),))
    assert result["complete"] is False
    assert result["incomplete_tools"] == ["bandit"]
    assert result["client_delivery_allowed"] is False
    with pytest.raises(RuntimeError, match="bandit"):
        require_complete_preflight(result)


def test_non_applicable_scanner_does_not_create_fake_failure(monkeypatch) -> None:
    monkeypatch.setattr("nico.scanner_preflight_v1.shutil.which", lambda _name: None)
    result = run_preflight((ScannerRequirement("npm-audit", "npm", applicable=False),))
    assert result["complete"] is True
    assert result["records"] == [{"tool": "npm-audit", "status": "not_applicable"}]


def test_executable_must_return_successful_version_evidence(monkeypatch) -> None:
    monkeypatch.setattr("nico.scanner_preflight_v1.shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(
        "nico.scanner_preflight_v1.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout="", stderr="broken tool"),
    )
    result = run_preflight((ScannerRequirement("semgrep", "semgrep"),))
    assert result["complete"] is False
    assert result["records"][0]["status"] == "unusable"
    assert result["records"][0]["exit_code"] == 2


def test_ready_scanner_retains_executable_version_and_exit_code(monkeypatch) -> None:
    monkeypatch.setattr("nico.scanner_preflight_v1.shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(
        "nico.scanner_preflight_v1.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="tool 1.2.3\n", stderr=""),
    )
    result = run_preflight((ScannerRequirement("gitleaks", "gitleaks"),))
    assert result["complete"] is True
    assert result["records"][0] == {
        "tool": "gitleaks",
        "status": "ready",
        "executable": "/usr/bin/tool",
        "exit_code": 0,
        "version": "tool 1.2.3",
    }
