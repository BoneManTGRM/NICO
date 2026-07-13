from __future__ import annotations

from nico import scanner_history_truth
from nico.hosted_scanner_artifacts import attach_scanner_worker_artifacts
from nico.scanner_tool_runners import ScannerToolSpec, run_scanner_tool
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def test_trufflehog_git_command_targets_repo_history(monkeypatch, tmp_path):
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(scanner_history_truth, "_ensure_full_history", lambda _workspace: (True, "verified full history"))
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    workspace = WorkerWorkspace(root=tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_runner(args, *, cwd, limits):
        calls.append(tuple(args))
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout='{"SourceMetadata": {}}', stderr="")

    spec = ScannerToolSpec(
        "trufflehog",
        ("trufflehog", "git", "file://{repo_dir}", "--json", "--no-update", "--no-verification"),
        "secret",
        scans_git_history=True,
    )

    result = run_scanner_tool(spec, workspace, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["scans_git_history"] is True
    assert result["history_depth_verified"] is True
    assert result["history_scope"] == "full_git_history"
    assert calls[0][0:2] == ("trufflehog", "git")
    assert calls[0][2] == f"file://{repo_dir}"


def test_gitleaks_history_metadata_is_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(scanner_history_truth, "_ensure_full_history", lambda _workspace: (True, "verified full history"))
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    workspace = WorkerWorkspace(root=tmp_path)

    def fake_runner(args, *, cwd, limits):
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="[]", stderr="")

    spec = ScannerToolSpec(
        "gitleaks",
        ("gitleaks", "detect", "--no-banner", "--redact", "--report-format", "json", "--source", "."),
        "secret",
        scans_git_history=True,
    )

    result = run_scanner_tool(spec, workspace, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["scans_git_history"] is True
    assert result["history_depth_verified"] is True
    assert result["full_history_verified"] is True
    assert result["findings"] == []


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
