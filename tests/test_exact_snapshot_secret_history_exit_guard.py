from __future__ import annotations

from pathlib import Path

import nico.exact_snapshot_secret_history as history
import nico.exact_snapshot_secret_history_exit_guard as guard


def test_nonzero_empty_history_result_is_not_treated_as_clean(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        guard,
        "_ORIGINAL_RUN_HISTORY_TOOL",
        lambda *args, **kwargs: {
            "scanner": "trufflehog",
            "status": "passed",
            "execution_status": "completed_clean",
            "execution_completed": True,
            "exit_code": 1,
            "finding_count": 0,
            "unavailable_data_notes": [],
        },
    )

    result = guard.guarded_run_history_tool(
        "trufflehog",
        {"binary": "trufflehog"},
        tmp_path,
        {},
        1.0,
    )

    assert result["status"] == "failed"
    assert result["execution_status"] == "execution_failed"
    assert result["execution_completed"] is False
    assert "not clean evidence" in result["evidence_summary"]
    assert any("cannot support a clean" in item for item in result["unavailable_data_notes"])


def test_zero_exit_empty_history_result_remains_clean(monkeypatch, tmp_path: Path) -> None:
    clean = {
        "scanner": "gitleaks",
        "status": "passed",
        "execution_status": "completed_clean",
        "execution_completed": True,
        "exit_code": 0,
        "finding_count": 0,
        "unavailable_data_notes": [],
    }
    monkeypatch.setattr(guard, "_ORIGINAL_RUN_HISTORY_TOOL", lambda *args, **kwargs: dict(clean))

    result = guard.guarded_run_history_tool("gitleaks", {"binary": "gitleaks"}, tmp_path, {}, 1.0)

    assert result == clean


def test_exit_guard_installer_is_idempotent() -> None:
    first = guard.install_secret_history_exit_guard()
    second = guard.install_secret_history_exit_guard()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert history._run_history_tool is guard.guarded_run_history_tool
