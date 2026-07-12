from __future__ import annotations

from copy import deepcopy

import nico.assessment_required_tools as policy
import nico.snapshot_assessment_handlers as snapshot_handlers
import nico.snapshot_scanner_worker as snapshot_worker


def test_complete_assessment_tools_repairs_stale_client_list_without_duplicates() -> None:
    tools = policy.complete_assessment_tools(["pip-audit", "bandit", "eslint", "bandit"])

    assert tools[: len(policy.REQUIRED_EXACT_SNAPSHOT_TOOLS)] == list(policy.REQUIRED_EXACT_SNAPSHOT_TOOLS)
    assert tools.count("bandit") == 1
    assert tools.count("eslint") == 1
    assert "pip-audit" in tools
    assert "gitleaks" in tools
    assert "trufflehog" in tools
    assert "nico-secrets" in tools
    assert "nico-static" in tools
    assert policy.REQUIRED_DEPENDENCY_TOOL == "osv-scanner"
    assert tools.count("osv-scanner") == 1


def test_complete_assessment_tools_handles_missing_or_invalid_lists() -> None:
    assert policy.complete_assessment_tools(None) == list(policy.REQUIRED_EXACT_SNAPSHOT_TOOLS)
    assert policy.complete_assessment_tools("bandit") == list(policy.REQUIRED_EXACT_SNAPSHOT_TOOLS)
    assert "osv-scanner" in policy.complete_assessment_tools(None)


def test_dependency_baseline_is_added_to_stale_ecosystem_specific_list() -> None:
    tools = policy.complete_assessment_tools(["pip-audit", "npm-audit", "bandit", "semgrep"])

    assert "pip-audit" in tools
    assert "npm-audit" in tools
    assert "osv-scanner" in tools
    assert tools.index("osv-scanner") < tools.index("pip-audit")


def test_snapshot_wrapper_repairs_stale_client_payload_without_mutating_input(monkeypatch) -> None:
    captured: dict = {}

    def fake_start(payload: dict) -> dict:
        captured.update(deepcopy(payload))
        return {
            "status": "queued",
            "scan_id": "scan_required_tools",
            "tools_requested": list(payload.get("tools") or []),
        }

    monkeypatch.setattr(policy, "_ORIGINAL_START_SNAPSHOT_SCAN", fake_start)
    original = {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "tools": ["pip-audit", "npm-audit", "bandit", "semgrep", "eslint"],
    }
    untouched = deepcopy(original)

    result = policy.start_snapshot_scan_with_required_tools(original)

    assert original == untouched
    assert set(policy.REQUIRED_EXACT_SNAPSHOT_TOOLS).issubset(captured["tools"])
    assert "osv-scanner" in captured["tools"]
    assert result["tools_requested"] == captured["tools"]
    assert result["tool_policy"]["version"] == policy.TOOL_POLICY_VERSION
    assert result["tool_policy"]["required_dependency_tool"] == "osv-scanner"
    assert result["tool_policy"]["stale_client_tools_repaired"] is True


def test_snapshot_wrapper_reports_complete_client_without_false_repair(monkeypatch) -> None:
    monkeypatch.setattr(
        policy,
        "_ORIGINAL_START_SNAPSHOT_SCAN",
        lambda payload: {"status": "queued", "tools_requested": list(payload.get("tools") or [])},
    )
    requested = [*policy.REQUIRED_EXACT_SNAPSHOT_TOOLS, "pip-audit", "eslint"]

    result = policy.start_snapshot_scan_with_required_tools({"authorized": True, "tools": requested})

    assert result["tools_requested"] == requested
    assert result["tool_policy"]["required_dependency_tool"] == "osv-scanner"
    assert result["tool_policy"]["stale_client_tools_repaired"] is False


def test_installer_patches_snapshot_entry_points_idempotently() -> None:
    first = policy.install_required_assessment_tools()
    second = policy.install_required_assessment_tools()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert first["required_tools"] == list(policy.REQUIRED_EXACT_SNAPSHOT_TOOLS)
    assert first["required_dependency_tool"] == "osv-scanner"
    assert snapshot_worker.start_snapshot_scan is policy.start_snapshot_scan_with_required_tools
    assert snapshot_handlers.start_snapshot_scan is policy.start_snapshot_scan_with_required_tools
