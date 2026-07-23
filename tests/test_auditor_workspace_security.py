from __future__ import annotations

from pathlib import Path

import pytest

from nico import auditor


@pytest.mark.parametrize(
    ("value", "repository"),
    [
        ("BoneManTGRM/NICO", "BoneManTGRM/NICO"),
        ("https://github.com/BoneManTGRM/NICO", "BoneManTGRM/NICO"),
        ("https://github.com/BoneManTGRM/NICO.git", "BoneManTGRM/NICO"),
    ],
)
def test_canonical_github_repository_accepts_only_explicit_github_identity(
    value: str,
    repository: str,
) -> None:
    clone_url, observed = auditor._canonical_github_repository(value)
    assert clone_url == f"https://github.com/{repository}.git"
    assert observed == repository


@pytest.mark.parametrize(
    "value",
    [
        "",
        "file:///tmp/repository",
        "ssh://git@github.com/BoneManTGRM/NICO.git",
        "https://example.com/BoneManTGRM/NICO",
        "https://token@github.com/BoneManTGRM/NICO",
        "https://github.com/BoneManTGRM/NICO/issues",
        "../NICO",
        "BoneManTGRM/../../escape",
    ],
)
def test_canonical_github_repository_rejects_local_credentials_and_path_traversal(value: str) -> None:
    with pytest.raises(ValueError):
        auditor._canonical_github_repository(value)


def test_audit_uses_isolated_workspace_and_removes_it(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "nico-audit-random"
    observed: dict[str, object] = {}

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "nico-audit-"
        workspace.mkdir()
        return str(workspace)

    def fake_run(command: list[str], **kwargs: object) -> object:
        observed["command"] = command
        observed["kwargs"] = kwargs
        destination = Path(command[-1])
        assert destination == workspace / "repo"
        destination.mkdir()
        return object()

    def fake_scan(path: str, *, kind: str) -> dict[str, object]:
        assert Path(path) == workspace / "repo"
        assert kind == "url_audit"
        return {"scan": {"id": "scan-1", "findings": []}, "repairs": []}

    monkeypatch.setattr(auditor.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(auditor.subprocess, "run", fake_run)
    monkeypatch.setattr(auditor, "run_scan", fake_scan)
    monkeypatch.setattr(auditor, "generate_reports", lambda: [])

    result = auditor.audit("https://github.com/BoneManTGRM/NICO.git")

    assert result["status"] == "complete"
    assert result["repo"] == "BoneManTGRM/NICO"
    assert result["client_delivery_allowed"] is False
    assert observed["command"] == [
        "git",
        "clone",
        "--depth",
        "1",
        "--",
        "https://github.com/BoneManTGRM/NICO.git",
        str(workspace / "repo"),
    ]
    assert not workspace.exists()


def test_invalid_repository_is_rejected_before_clone(monkeypatch) -> None:
    monkeypatch.setattr(
        auditor.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("clone must not run"),
    )
    result = auditor.audit("file:///etc")
    assert result["status"] == "failed"
    assert "validation failed" in result["error"].lower()
    assert result["client_delivery_allowed"] is False
