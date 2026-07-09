from pathlib import Path

from nico import scanner_tool_runners
from nico.hosted_secret_scanner_execution_patch import (
    _gitleaks_command,
    _history_metadata,
    _trufflehog_command,
    _unavailable,
    install_hosted_secret_scanner_execution_patch,
)
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def workspace(tmp_path: Path) -> WorkerWorkspace:
    repo = tmp_path / "repo"
    repo.mkdir()
    return WorkerWorkspace(root=tmp_path)


def test_secret_unavailable_records_full_history_status():
    spec = ScannerToolSpec("gitleaks", ("gitleaks",), "secret", scans_git_history=True)
    history = {"history_depth": "full", "full_history_verified": True, "commit_count": 3, "head_sha": "abc"}

    result = _unavailable(spec, "gitleaks missing", history=history)

    assert result["status"] == "unavailable"
    assert result["current_run"] is True
    assert result["verified_for_this_report"] is False
    assert result["full_history_verified"] is True
    assert result["history_depth"] == "full"


def test_gitleaks_command_requires_binary(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    monkeypatch.setattr("nico.hosted_secret_scanner_execution_patch.shutil.which", lambda name: None)

    command, cwd, reason = _gitleaks_command(ws)

    assert command is None
    assert cwd == ws.repo_dir
    assert "gitleaks is not installed" in reason


def test_trufflehog_command_uses_file_url(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    monkeypatch.setattr("nico.hosted_secret_scanner_execution_patch.shutil.which", lambda name: "/usr/bin/trufflehog" if name == "trufflehog" else None)

    command, cwd, reason = _trufflehog_command(ws)

    assert reason is None
    assert cwd == ws.repo_dir
    assert command[:2] == ("trufflehog", "git")
    assert command[2] == f"file://{ws.repo_dir}"


def test_history_metadata_detects_full_history(monkeypatch, tmp_path):
    ws = workspace(tmp_path)

    def fake_git(workspace, *args):
        joined = " ".join(args)
        if "--is-shallow-repository" in joined:
            return WorkerCommandResult(args=("git", *args), returncode=0, stdout="false\n", stderr="")
        if "--count" in joined:
            return WorkerCommandResult(args=("git", *args), returncode=0, stdout="9\n", stderr="")
        return WorkerCommandResult(args=("git", *args), returncode=0, stdout="abc123\n", stderr="")

    monkeypatch.setattr("nico.hosted_secret_scanner_execution_patch._git_result", fake_git)
    result = _history_metadata(ws)

    assert result["full_history_verified"] is True
    assert result["history_depth"] == "full"
    assert result["commit_count"] == 9
    assert result["head_sha"] == "abc123"


def test_patched_gitleaks_completed_requires_full_history(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    monkeypatch.setattr("nico.hosted_secret_scanner_execution_patch.shutil.which", lambda name: "/usr/bin/gitleaks" if name == "gitleaks" else None)
    monkeypatch.setattr(
        "nico.hosted_secret_scanner_execution_patch._history_metadata",
        lambda workspace: {"history_depth": "full", "full_history_verified": True, "commit_count": 5, "head_sha": "abc", "reason": ""},
    )
    install_hosted_secret_scanner_execution_patch()

    def fake_runner(command, *, cwd, limits):
        assert command[0] == "gitleaks"
        return WorkerCommandResult(args=tuple(command), returncode=0, stdout="[]", stderr="")

    spec = ScannerToolSpec("gitleaks", ("gitleaks",), "secret", timeout_seconds=120, scans_git_history=True)
    result = scanner_tool_runners.run_scanner_tool(spec, ws, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["verified_for_this_report"] is True
    assert result["findings_count"] == 0
    assert result["full_history_verified"] is True
    assert result["execution_source"] == "gitleaks_full_history"


def test_patched_trufflehog_shallow_history_not_verified(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    monkeypatch.setattr("nico.hosted_secret_scanner_execution_patch.shutil.which", lambda name: "/usr/bin/trufflehog" if name == "trufflehog" else None)
    monkeypatch.setattr(
        "nico.hosted_secret_scanner_execution_patch._history_metadata",
        lambda workspace: {"history_depth": "shallow_or_unverified", "full_history_verified": False, "commit_count": 1, "head_sha": "abc", "reason": "Checkout is shallow."},
    )
    install_hosted_secret_scanner_execution_patch()

    def fake_runner(command, *, cwd, limits):
        assert command[0] == "trufflehog"
        return WorkerCommandResult(args=tuple(command), returncode=0, stdout="", stderr="")

    spec = ScannerToolSpec("trufflehog", ("trufflehog",), "secret", timeout_seconds=120, scans_git_history=True)
    result = scanner_tool_runners.run_scanner_tool(spec, ws, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["verified_for_this_report"] is False
    assert result["full_history_verified"] is False
    assert result["history_depth"] == "shallow_or_unverified"
