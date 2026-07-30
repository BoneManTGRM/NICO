from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

from nico.authoritative_scanner_execution_v3 import (
    _normalize_record,
    _run_gitleaks,
    install_authoritative_scanner_execution_v3,
)
from nico.scanner_tool_runners import TOOL_SPECS
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _workspace(tmp_path: Path) -> WorkerWorkspace:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace.repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "nico@example.invalid"], cwd=workspace.repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "NICO Test"], cwd=workspace.repo_dir, check=True)
    (workspace.repo_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=workspace.repo_dir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "test"], cwd=workspace.repo_dir, check=True)
    return workspace


def _spec(name: str):
    return next(item for item in TOOL_SPECS if item.name == name)


def test_completed_exact_sha_record_requires_retained_artifact(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    completed = _normalize_record(
        {
            "tool": "bandit",
            "status": "completed",
            "output_capture_complete": True,
            "raw_artifact_capture_complete": True,
            "artifact_hash": "a" * 64,
            "findings": [],
            "verified_for_this_report": True,
        },
        workspace,
    )
    missing_artifact = _normalize_record(
        {
            "tool": "bandit",
            "status": "completed",
            "output_capture_complete": True,
            "findings": [],
            "verified_for_this_report": True,
        },
        workspace,
    )

    assert completed["completed"] is True
    assert completed["verified"] is True
    assert completed["exact_commit_match"] is True
    assert completed["state"] == "completed"
    assert missing_artifact["completed"] is False
    assert missing_artifact["verified"] is False


def test_clean_gitleaks_run_materializes_verified_empty_json(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    monkeypatch.setattr(
        "nico.authoritative_scanner_execution_v3.shutil.which",
        lambda name: f"/virtual/{name}" if name == "gitleaks" else None,
    )

    def fake_runner(command, *, cwd, limits, stdout_path=None, extra_env=None):
        command = tuple(command)
        report_index = command.index("--report-path")
        report_path = Path(command[report_index + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("[]\n", encoding="utf-8")
        if stdout_path is not None:
            Path(stdout_path).parent.mkdir(parents=True, exist_ok=True)
            Path(stdout_path).write_text("", encoding="utf-8")
        return WorkerCommandResult(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
            stdout_path=str(stdout_path) if stdout_path is not None else None,
        )

    record = _run_gitleaks(_spec("gitleaks"), workspace, fake_runner)

    assert record["state"] == "completed"
    assert record["completed"] is True
    assert record["verified"] is True
    assert record["full_history_verified"] is True
    assert record["findings"] == []
    assert record["artifact_hash"]
    assert record["raw_artifact_retention_complete"] is True


def test_final_scanner_wrapper_accepts_project_preparation() -> None:
    install_authoritative_scanner_execution_v3()
    from nico import scanner_tool_runners

    parameters = inspect.signature(scanner_tool_runners.run_scanner_tool).parameters
    assert "preparation" in parameters
