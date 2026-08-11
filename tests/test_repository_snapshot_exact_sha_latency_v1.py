from __future__ import annotations

import nico.repository_snapshot as snapshot


class AlwaysFailCommitClient:
    def __init__(self) -> None:
        self.commit_calls = 0

    def get_commit(self, repository: str, ref: str):
        self.commit_calls += 1
        return None, "simulated GitHub commit timeout"


class MetadataClient(AlwaysFailCommitClient):
    def __init__(self, *, private: bool = False) -> None:
        super().__init__()
        self.private = private

    def get_repo(self, repository: str):
        return {
            "full_name": repository,
            "default_branch": "main",
            "private": self.private,
            "visibility": "private" if self.private else "public",
        }, None


def _context(expected: str) -> dict[str, object]:
    return {
        "repository": "BoneManTGRM/NICO",
        "expected_commit_sha": expected,
        "authorized_by": "production_acceptance",
    }


def _public_resolution(expected: str) -> dict[str, object]:
    return {
        "sha": expected,
        "commit": {
            "committer": {"date": "2026-08-11T00:00:00Z"},
            "author": {"date": "2026-08-11T00:00:00Z"},
            "tree": {"sha": "b" * 40},
            "message": "Exact deployed release",
        },
    }


def test_exact_sha_commit_lookup_spends_one_api_attempt_before_fallback() -> None:
    expected = "a" * 40
    client = AlwaysFailCommitClient()
    sleeps: list[float] = []

    commit, error, attempts = snapshot._retry_commit_lookup(
        client,
        "BoneManTGRM/NICO",
        expected,
        sleep=sleeps.append,
    )

    assert commit is None
    assert error == "simulated GitHub commit timeout"
    assert attempts == 1
    assert client.commit_calls == 1
    assert sleeps == []


def test_default_branch_commit_lookup_keeps_three_attempt_resilience_budget() -> None:
    client = AlwaysFailCommitClient()
    sleeps: list[float] = []

    commit, error, attempts = snapshot._retry_commit_lookup(
        client,
        "BoneManTGRM/NICO",
        "main",
        sleep=sleeps.append,
    )

    assert commit is None
    assert error == "simulated GitHub commit timeout"
    assert attempts == snapshot._API_COMMIT_ATTEMPTS == 3
    assert client.commit_calls == 3
    assert sleeps == list(snapshot._API_RETRY_DELAYS_SECONDS)


def test_public_exact_sha_resolution_falls_back_after_one_api_failure(monkeypatch) -> None:
    expected = "c" * 40
    client = MetadataClient(private=False)
    fallback_calls: list[tuple[str, str]] = []

    def public_git(repository: str, sha: str):
        fallback_calls.append((repository, sha))
        return _public_resolution(sha), None

    monkeypatch.setattr(snapshot, "_public_git_exact_commit", public_git)

    result = snapshot.resolve_repository_commit(_context(expected), client=client)

    assert result["status"] == "attached"
    assert result["commit_sha"] == expected
    assert result["exact_commit_verified"] is True
    assert result["commit_capture_method"] == "public_git_exact_sha"
    assert result["api_commit_lookup_attempts"] == 1
    assert result["public_git_fallback_used"] is True
    assert client.commit_calls == 1
    assert fallback_calls == [("BoneManTGRM/NICO", expected)]


def test_private_exact_sha_failure_remains_fail_closed_without_public_fallback(monkeypatch) -> None:
    expected = "d" * 40
    client = MetadataClient(private=True)
    fallback_called = False

    def public_git(repository: str, sha: str):
        nonlocal fallback_called
        fallback_called = True
        return _public_resolution(sha), None

    monkeypatch.setattr(snapshot, "_public_git_exact_commit", public_git)

    result = snapshot.resolve_repository_commit(_context(expected), client=client)

    assert result["status"] == "unavailable"
    assert result["resolution_failure_code"] == "private_repository_api_commit_unavailable"
    assert result["api_commit_lookup_attempts"] == 1
    assert result["public_git_fallback_attempted"] is False
    assert client.commit_calls == 1
    assert fallback_called is False
