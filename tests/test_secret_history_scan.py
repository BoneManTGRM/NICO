from __future__ import annotations

import subprocess

from nico import scanner_tool_runners
from nico.hosted_scanner_artifacts import attach_scanner_worker_artifacts
from nico.scanner_determinism_v1 import install_scanner_determinism
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _initialize_repository(repo_dir) -> None:
    (repo_dir / "README.md").write_text("history scanner fixture\n", encoding="utf-8")
    commands = (
        ("git", "init", "--quiet"),
        ("git", "config", "user.email", "nico-test@example.invalid"),
        ("git", "config", "user.name", "NICO Test"),
        ("git", "add", "README.md"),
        ("git", "commit", "--quiet", "-m", "history scanner fixture"),
    )
    for command in commands:
        subprocess.run(command, cwd=repo_dir, check=True, capture_output=True, text=True)


def test_trufflehog_git_command_targets_repo_history(monkeypatch, tmp_path):
    install_scanner_determinism()
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda executable: f"/usr/bin/{executable}")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _initialize_repository(repo_dir)
    workspace = WorkerWorkspace(root=tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_runner(args, *, cwd, limits, **kwargs):
        calls.append(tuple(args))
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout='{"SourceMetadata": {}}', stderr="")

    spec = ScannerToolSpec(
        "trufflehog",
        ("trufflehog", "git", "file://{repo_dir}", "--json", "--no-update", "--no-verification", "--branch", "HEAD"),
        "secret",
        scans_git_history=True,
    )

    result = scanner_tool_runners.run_scanner_tool(spec, workspace, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["scans_git_history"] is True
    assert result["history_depth_verified"] is True
    assert result["full_history_verified"] is True
    assert result["history_scope"] == "reachable_ancestry_at_assessed_commit"
    assert result["descendant_refs_scanned"] is False
    scanner_call = next(call for call in calls if call[0:2] == ("trufflehog", "git"))
    assert scanner_call[2] == f"file://{repo_dir}"
    assert scanner_call[scanner_call.index("--branch") + 1] == "HEAD"


def test_gitleaks_history_metadata_is_preserved(monkeypatch, tmp_path):
    install_scanner_determinism()
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda executable: f"/usr/bin/{executable}")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _initialize_repository(repo_dir)
    workspace = WorkerWorkspace(root=tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_runner(args, *, cwd, limits, **kwargs):
        calls.append(tuple(args))
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="[]", stderr="")

    spec = ScannerToolSpec(
        "gitleaks",
        ("gitleaks", "detect", "--no-banner", "--redact", "--report-format", "json", "--source", ".", "--log-opts", "HEAD"),
        "secret",
        scans_git_history=True,
    )

    result = scanner_tool_runners.run_scanner_tool(spec, workspace, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["scans_git_history"] is True
    assert result["history_depth_verified"] is True
    assert result["full_history_verified"] is True
    assert result["history_scope"] == "reachable_ancestry_at_assessed_commit"
    assert result["descendant_refs_scanned"] is False
    assert result["findings"] == []
    scanner_call = next(call for call in calls if call[0] == "gitleaks")
    assert scanner_call[scanner_call.index("--log-opts") + 1] == "HEAD"


def test_secret_history_scan_verification_clears_git_history_unavailable():
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 92,
                "status": "green",
                "summary": "Hosted file scan only.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Full git-history secret scanning requires a sandboxed worker with gitleaks or trufflehog."],
            }
        ],
        "findings": [],
    }
    artifact = {
        "checkout": {"full_history_secret_scan_requested": True, "history_depth": "full", "commit_count": 12},
        "secret_history_scan": {"completed_tools": ["gitleaks"], "history_aware": True},
        "tools": {
            "gitleaks": {"status": "completed", "findings": [], "scans_git_history": True},
            "trufflehog": {"status": "completed", "findings": [], "scans_git_history": True},
        },
    }

    updated = attach_scanner_worker_artifacts(result, {"scanner_worker_artifact": artifact})
    secrets = updated["sections"][0]

    assert secrets["unavailable"] == []
    assert secrets["score"] == 95
    assert any("Full git-history secret scan executed" in item for item in secrets["evidence"])
