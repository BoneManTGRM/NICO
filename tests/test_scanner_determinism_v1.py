from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from nico import scanner_tool_runners as runners
from nico import snapshot_scanner_worker as snapshot
from nico.scanner_determinism_v1 import (
    VERSION,
    _replace_specs,
    canonicalize_findings,
    clone_repository_at_snapshot,
    install_scanner_determinism,
)


def test_canonical_findings_ignore_runtime_timestamps_and_temp_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    finding = {
        "path": str(repo / "src" / "service.py"),
        "line": 10,
        "message": "review exact call",
        "observed_at": "2026-07-31T10:00:00Z",
    }
    later = {
        **finding,
        "observed_at": "2026-07-31T11:00:00Z",
    }

    canonical, summary = canonicalize_findings([finding, later], repo)

    assert canonical == [
        {
            "line": 10,
            "message": "review exact call",
            "path": "src/service.py",
        }
    ]
    assert summary["raw_count"] == 2
    assert summary["canonical_count"] == 1
    assert summary["duplicates_removed"] == 1


def test_history_scanners_and_semgrep_are_bound_to_immutable_inputs() -> None:
    specs = {spec.name: spec for spec in _replace_specs(runners.TOOL_SPECS)}

    assert "auto" not in specs["semgrep"].command
    assert "semgrep_rules_v1.yml" in " ".join(specs["semgrep"].command)
    assert specs["gitleaks"].command[-2:] == ("--log-opts", "HEAD")
    assert "--branch" in specs["trufflehog"].command
    assert specs["trufflehog"].command[-1] == "HEAD"
    assert "--no-verification" in specs["trufflehog"].command


def test_exact_snapshot_clone_uses_fetch_head_and_rejects_retained_refs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(command, *, cwd, env, timeout=90):
        calls.append(tuple(command))
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="a" * 40 + "\n", stderr="")
        if command[:2] == ["git", "for-each-ref"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(snapshot, "_git", fake_git)
    monkeypatch.setattr("nico.scanner_worker.directory_size", lambda path: 1)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git" if name == "git" else None)

    repo, actual, notes = clone_repository_at_snapshot(
        "example/repository",
        "a" * 40,
        tmp_path,
        {},
    )

    assert repo == tmp_path / "repo"
    assert actual == "a" * 40
    assert notes == []
    fetch = next(command for command in calls if "fetch" in command)
    assert "--no-tags" in fetch
    assert fetch[-1] == "a" * 40
    assert ("git", "checkout", "--detach", "--force", "FETCH_HEAD") in calls
    assert any("for-each-ref" in command for command in calls)


def test_retained_branch_or_tag_ref_blocks_snapshot_scan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_git(command, *, cwd, env, timeout=90):
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="b" * 40 + "\n", stderr="")
        if command[:2] == ["git", "for-each-ref"]:
            return SimpleNamespace(
                returncode=0,
                stdout="refs/remotes/origin/main\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(snapshot, "_git", fake_git)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git" if name == "git" else None)

    repo, actual, notes = clone_repository_at_snapshot(
        "example/repository",
        "b" * 40,
        tmp_path,
        {},
    )

    assert repo is None
    assert actual == "b" * 40
    assert any("retained mutable" in note for note in notes)


def test_installer_is_idempotent_and_updates_runtime_modules() -> None:
    first = install_scanner_determinism()
    second = install_scanner_determinism()
    specs = {spec.name: spec for spec in runners.TOOL_SPECS}

    assert first == second
    assert first["version"] == VERSION
    assert first["exact_commit_ancestry_clone_bound"] is True
    assert snapshot.clone_repository_at_snapshot is clone_repository_at_snapshot
    assert specs["gitleaks"].command[-1] == "HEAD"
    assert specs["trufflehog"].command[-1] == "HEAD"
    assert getattr(runners.run_scanner_tool, "__nico_deterministic_runner__") is True
