from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import nico.exact_snapshot_full_history_checkout as checkout
import nico.snapshot_scanner_worker as snapshot_worker


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_full_checkout_is_reused_without_fetch(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(checkout, "_ORIGINAL_CLONE", lambda *args, **kwargs: (repo, "a" * 40, []))
    calls: list[list[str]] = []

    def fake_git(command, **kwargs):
        calls.append(command)
        return _completed(stdout="false\n")

    monkeypatch.setattr(snapshot_worker, "_git", fake_git)

    result = checkout.clone_repository_with_full_history("owner/repo", "a" * 40, tmp_path, {})

    assert result == (repo, "a" * 40, [])
    assert calls == [["git", "rev-parse", "--is-shallow-repository"]]


def test_shallow_checkout_is_unshallowed_without_changing_snapshot(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    commit = "b" * 40
    monkeypatch.setattr(checkout, "_ORIGINAL_CLONE", lambda *args, **kwargs: (repo, commit, []))
    shallow_values = iter(["true\n", "false\n"])
    commands: list[list[str]] = []

    def fake_git(command, **kwargs):
        commands.append(command)
        if command[1:] == ["rev-parse", "--is-shallow-repository"]:
            return _completed(stdout=next(shallow_values))
        if command[1:] == ["fetch", "--unshallow", "--no-tags", "origin"]:
            return _completed()
        if command[1:] == ["rev-parse", "HEAD"]:
            return _completed(stdout=commit + "\n")
        raise AssertionError(command)

    monkeypatch.setattr(snapshot_worker, "_git", fake_git)

    repo_path, actual, notes = checkout.clone_repository_with_full_history("owner/repo", commit, tmp_path, {})

    assert repo_path == repo
    assert actual == commit
    assert any("verified full git history" in note for note in notes)
    assert ["git", "fetch", "--unshallow", "--no-tags", "origin"] in commands


def test_failed_unshallow_keeps_current_tree_but_discloses_history_limitation(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    commit = "c" * 40
    monkeypatch.setattr(checkout, "_ORIGINAL_CLONE", lambda *args, **kwargs: (repo, commit, []))

    def fake_git(command, **kwargs):
        if command[1:] == ["rev-parse", "--is-shallow-repository"]:
            return _completed(stdout="true\n")
        if command[1:] == ["fetch", "--unshallow", "--no-tags", "origin"]:
            return _completed(returncode=1, stderr="network unavailable")
        raise AssertionError(command)

    monkeypatch.setattr(snapshot_worker, "_git", fake_git)

    repo_path, actual, notes = checkout.clone_repository_with_full_history("owner/repo", commit, tmp_path, {})

    assert repo_path == repo
    assert actual == commit
    assert any("remained shallow" in note for note in notes)
    assert any("network unavailable" in note for note in notes)


def test_unshallow_identity_mismatch_is_disclosed(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    commit = "d" * 40
    monkeypatch.setattr(checkout, "_ORIGINAL_CLONE", lambda *args, **kwargs: (repo, commit, []))

    def fake_git(command, **kwargs):
        if command[1:] == ["rev-parse", "--is-shallow-repository"]:
            return _completed(stdout="true\n")
        if command[1:] == ["fetch", "--unshallow", "--no-tags", "origin"]:
            return _completed()
        if command[1:] == ["rev-parse", "HEAD"]:
            return _completed(stdout="e" * 40 + "\n")
        raise AssertionError(command)

    monkeypatch.setattr(snapshot_worker, "_git", fake_git)

    _repo_path, _actual, notes = checkout.clone_repository_with_full_history("owner/repo", commit, tmp_path, {})

    assert any("changed or obscured" in note for note in notes)


def test_full_history_checkout_installer_is_idempotent() -> None:
    first = checkout.install_exact_snapshot_full_history_checkout()
    second = checkout.install_exact_snapshot_full_history_checkout()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert snapshot_worker.clone_repository_at_snapshot is checkout.clone_repository_with_full_history
