from __future__ import annotations

from nico import scanner_history_truth
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerWorkspace


def test_history_scanner_is_unavailable_when_full_depth_cannot_be_verified(monkeypatch, tmp_path) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    spec = ScannerToolSpec("gitleaks", ("gitleaks", "git", "."), "secret", scans_git_history=True)

    monkeypatch.setattr(scanner_history_truth, "_ensure_full_history", lambda _workspace: (False, "history unavailable"))
    result = scanner_history_truth.run_scanner_tool_with_history_truth(spec, workspace)

    assert result["status"] == "unavailable"
    assert result["history_depth_verified"] is False
    assert result["history_scope"] == "unavailable"
    assert result["reason"] == "history unavailable"


def test_verified_history_is_attached_to_history_scanner_result(monkeypatch, tmp_path) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    spec = ScannerToolSpec("trufflehog", ("trufflehog", "git", "."), "secret", scans_git_history=True)

    monkeypatch.setattr(
        scanner_history_truth,
        "_ensure_full_history",
        lambda _workspace: (True, "verified full history"),
    )
    monkeypatch.setattr(
        scanner_history_truth,
        "_ORIGINAL_RUN_SCANNER_TOOL",
        lambda _spec, _workspace, runner=None: {
            "tool": "trufflehog",
            "status": "completed",
            "findings": [],
            "scans_git_history": True,
        },
    )

    result = scanner_history_truth.run_scanner_tool_with_history_truth(spec, workspace)

    assert result["status"] == "completed"
    assert result["history_depth_verified"] is True
    assert result["history_scope"] == "full_git_history"
    assert result["history_verification_note"] == "verified full history"


def test_current_tree_scanner_does_not_require_history_probe(monkeypatch, tmp_path) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    spec = ScannerToolSpec("bandit", ("bandit", "-r", "."), "static", scans_git_history=False)

    monkeypatch.setattr(
        scanner_history_truth,
        "_ensure_full_history",
        lambda _workspace: (_ for _ in ()).throw(AssertionError("history probe should not run")),
    )
    monkeypatch.setattr(
        scanner_history_truth,
        "_ORIGINAL_RUN_SCANNER_TOOL",
        lambda _spec, _workspace, runner=None: {"tool": "bandit", "status": "completed", "findings": []},
    )

    result = scanner_history_truth.run_scanner_tool_with_history_truth(spec, workspace)

    assert result == {"tool": "bandit", "status": "completed", "findings": []}


def test_installer_is_idempotent() -> None:
    first = scanner_history_truth.install_scanner_history_truth()
    second = scanner_history_truth.install_scanner_history_truth()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert "non-shallow git history" in second["rule"]
