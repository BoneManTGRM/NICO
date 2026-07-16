from __future__ import annotations

import time

from nico import scanner_tool_runners, snapshot_scanner_worker
from nico.mid_status_read_path import _active_status_response
from nico.snapshot_scanner_heartbeat_patch import (
    SNAPSHOT_SCANNER_HEARTBEAT_VERSION,
    _effective_timeout_seconds,
    _heartbeat_patch,
)
from nico.scanner_tool_runners import ScannerToolSpec


def test_snapshot_heartbeat_patch_is_bound_to_live_scanner_runner() -> None:
    runner = snapshot_scanner_worker.tool_runners.run_scanner_tool
    assert runner is scanner_tool_runners.run_scanner_tool
    assert getattr(runner, "_nico_snapshot_scanner_heartbeat_tool_v3", False) is True
    assert SNAPSHOT_SCANNER_HEARTBEAT_VERSION == "nico.snapshot_scanner_heartbeat.v4"


def test_heartbeat_persists_effective_gitleaks_countdown(monkeypatch) -> None:
    monkeypatch.setenv("NICO_HISTORY_TOOL_TIMEOUT_SECONDS", "420")
    monkeypatch.setenv("NICO_GITLEAKS_TIMEOUT_SECONDS", "900")
    spec = ScannerToolSpec(
        "gitleaks",
        ("gitleaks",),
        "secret",
        timeout_seconds=900,
        scans_git_history=True,
    )
    timeout = _effective_timeout_seconds(spec)
    patch = _heartbeat_patch("gitleaks", time.monotonic() - 25, timeout)

    assert timeout == 120
    assert patch["tool_timeout_seconds"] == 120
    assert 94 <= patch["tool_timeout_remaining_seconds"] <= 96
    assert 24 <= patch["tool_elapsed_seconds"] <= 26
    assert patch["tool_watchdog_policy"] == "hard_timeout_then_continue"
    assert patch["active_tool"] == "gitleaks"


def test_mid_live_status_shows_countdown_and_intra_tool_progress() -> None:
    record = {
        "run_id": "midrun_watchdog_test",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "response": {
            "status": "running",
            "run_id": "midrun_watchdog_test",
            "progress_percent": 43,
            "progress": [],
        },
    }
    scan = {
        "scan_id": "scan_watchdog_test",
        "run_id": "midrun_watchdog_test",
        "repository": "BoneManTGRM/NICO",
        "status": "running",
        "current_stage": "scanner_suite",
        "progress_percent": 43,
        "active_tool": "gitleaks",
        "tools_requested": [
            "pip-audit",
            "npm-audit",
            "osv-scanner",
            "bandit",
            "semgrep",
            "eslint",
            "typescript",
            "gitleaks",
            "trufflehog",
        ],
        "tools_run": [],
        "tool_elapsed_seconds": 60,
        "tool_timeout_seconds": 120,
        "tool_timeout_remaining_seconds": 60,
        "tool_watchdog_policy": "hard_timeout_then_continue",
        "heartbeat_at": "2099-01-01T00:00:00Z",
        "heartbeat_sequence": 4,
    }

    result = _active_status_response(record, scan)
    progress = next(item for item in result["progress"] if item["step"] == "scanner_worker")

    assert result["status"] == "running"
    assert result["progress_percent"] > 43
    assert result["scanner"]["record_progress_percent"] == 43
    assert result["scanner"]["progress_percent"] > 43
    assert "60s elapsed" in progress["message"]
    assert "60s remaining" in progress["message"]
    assert progress["evidence"]["tool_timeout_seconds"] == 120
    assert progress["evidence"]["tool_watchdog_policy"] == "hard_timeout_then_continue"
