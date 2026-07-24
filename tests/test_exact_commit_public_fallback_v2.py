from __future__ import annotations

from typing import Any

import nico.exact_commit_binding as binding
import nico.hosted_assessment as hosted
import nico.repository_snapshot as snapshot
from nico.exact_commit_public_fallback_v2 import (
    install_exact_commit_public_fallback_v2,
    resolve_commit_with_public_fallback,
)


class FakeClient:
    def __init__(self, *, private: bool = False) -> None:
        self.private = private

    def get_repo(self, repository: str):
        return {
            "full_name": repository,
            "default_branch": "main",
            "private": self.private,
            "visibility": "private" if self.private else "public",
        }, None


def _payload(expected: str) -> dict[str, Any]:
    return {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "authorization_confirmed": True,
        "authorized_by": f"production_acceptance;expected_commit_sha={expected}",
    }


def test_api_exact_commit_remains_primary(monkeypatch) -> None:
    expected = "a" * 40
    fallback_called = False
    monkeypatch.setattr(hosted, "GitHubAssessmentClient", lambda: FakeClient())
    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: ({"sha": expected}, None, 1),
    )

    def fallback(repository: str, sha: str):
        nonlocal fallback_called
        fallback_called = True
        return None, "should_not_run"

    monkeypatch.setattr(snapshot, "_public_git_exact_commit", fallback)

    repository, resolved, error = resolve_commit_with_public_fallback(_payload(expected))

    assert repository == "BoneManTGRM/NICO"
    assert resolved == expected
    assert error == ""
    assert fallback_called is False


def test_public_exact_sha_uses_bounded_git_fallback_after_api_failure(monkeypatch) -> None:
    expected = "b" * 40
    monkeypatch.setattr(hosted, "GitHubAssessmentClient", lambda: FakeClient())
    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: (None, "GitHub API rate limit exceeded", 3),
    )
    monkeypatch.setattr(
        snapshot,
        "_public_git_exact_commit",
        lambda repository, sha: ({"sha": sha, "commit": {"tree": {"sha": "c" * 40}}}, None),
    )

    repository, resolved, error = resolve_commit_with_public_fallback(_payload(expected))

    assert repository == "BoneManTGRM/NICO"
    assert resolved == expected
    assert error == ""


def test_private_repository_remains_api_only(monkeypatch) -> None:
    expected = "b" * 40
    fallback_called = False
    monkeypatch.setattr(hosted, "GitHubAssessmentClient", lambda: FakeClient(private=True))
    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: (None, "GitHub API unavailable", 3),
    )

    def fallback(repository: str, sha: str):
        nonlocal fallback_called
        fallback_called = True
        return {"sha": sha}, None

    monkeypatch.setattr(snapshot, "_public_git_exact_commit", fallback)

    _repository, resolved, error = resolve_commit_with_public_fallback(_payload(expected))

    assert resolved == ""
    assert "authorized GitHub API scope" in error
    assert fallback_called is False


def test_api_sha_mismatch_never_falls_back(monkeypatch) -> None:
    expected = "b" * 40
    mismatched = "d" * 40
    fallback_called = False
    monkeypatch.setattr(hosted, "GitHubAssessmentClient", lambda: FakeClient())
    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: ({"sha": mismatched}, None, 1),
    )

    def fallback(repository: str, sha: str):
        nonlocal fallback_called
        fallback_called = True
        return {"sha": sha}, None

    monkeypatch.setattr(snapshot, "_public_git_exact_commit", fallback)

    _repository, resolved, error = resolve_commit_with_public_fallback(_payload(expected))

    assert resolved == ""
    assert "different commit" in error
    assert fallback_called is False


def test_installer_rebinds_existing_exact_commit_wrapper() -> None:
    previous = binding._resolve_commit
    try:
        result = install_exact_commit_public_fallback_v2()
        assert result["status"] in {"installed", "already_installed"}
        assert binding._resolve_commit is resolve_commit_with_public_fallback
        assert result["private_repository_fallback_allowed"] is False
        assert result["api_mismatch_fallback_allowed"] is False
        assert result["client_delivery_allowed"] is False
    finally:
        binding._resolve_commit = previous
