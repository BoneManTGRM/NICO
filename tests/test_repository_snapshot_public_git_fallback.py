from __future__ import annotations

import subprocess

import nico.repository_snapshot as snapshot
from nico.storage import MemoryAdapter


class AuditedMemoryStore(MemoryAdapter):
    """Test store that preserves the production snapshot audit contract."""

    def __init__(self) -> None:
        super().__init__()
        self.audit_events: list[dict] = []

    def audit(
        self,
        action: str,
        payload: dict,
        customer_id: str | None = None,
        project_id: str | None = None,
    ) -> dict:
        audit_id = f"audit_test_{len(self.audit_events) + 1}"
        event = {
            "audit_id": audit_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "action": action,
            "payload": payload,
        }
        self.audit_events.append(event)
        return self.put("audit_log", audit_id, event)


class FakeClient:
    def __init__(self, *, private: bool = False, commit: dict | None = None, error: str | None = "rate limited") -> None:
        self.private = private
        self.commit = commit
        self.error = error
        self.commit_calls = 0

    def get_repo(self, repository: str):
        return {
            "full_name": repository,
            "default_branch": "main",
            "private": self.private,
            "visibility": "private" if self.private else "public",
            "pushed_at": "2026-07-23T20:00:00Z",
        }, None

    def get_commit(self, repository: str, ref: str):
        self.commit_calls += 1
        return self.commit, self.error


def _context(expected: str) -> dict:
    return {
        "run_id": "comprun_public_fallback",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_public_fallback",
        "project_id": "project_public_fallback",
        "authorized": True,
        "authorized_by": "production_acceptance",
        "authorization_scope": "authorized defensive repository assessment",
        "expected_commit_sha": expected,
    }


def test_public_git_exact_commit_verifies_requested_sha_and_tree() -> None:
    expected = "a" * 40
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(command)
        if "show" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{expected}\x00{'b' * 40}\x002026-07-23T20:00:00Z\x00Exact release\n",
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    commit, error = snapshot._public_git_exact_commit("BoneManTGRM/NICO", expected, runner=runner)

    assert error is None
    assert commit is not None
    assert commit["sha"] == expected
    assert commit["commit"]["tree"]["sha"] == "b" * 40
    assert commit["commit"]["message"] == "Exact release"
    fetch = next(command for command in calls if "fetch" in command)
    assert expected in fetch
    assert "--depth=1" in fetch
    assert "--no-tags" in fetch
    assert not any("token" in part.casefold() or "authorization" in part.casefold() for part in fetch)


def test_public_git_exact_commit_rejects_sha_mismatch() -> None:
    expected = "a" * 40

    def runner(command, **kwargs):
        if "show" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{'c' * 40}\x00{'b' * 40}\x002026-07-23T20:00:00Z\x00Wrong release\n",
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    commit, error = snapshot._public_git_exact_commit("BoneManTGRM/NICO", expected, runner=runner)

    assert commit is None
    assert error == "public_git_commit_mismatch"


def test_snapshot_uses_public_git_fallback_after_bounded_api_failure(monkeypatch) -> None:
    expected = "d" * 40
    client = FakeClient()
    store = AuditedMemoryStore()
    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: (None, "GitHub returned 403: API rate limit exceeded", 3),
    )
    monkeypatch.setattr(
        snapshot,
        "_public_git_exact_commit",
        lambda repository, sha: (
            {
                "sha": sha,
                "commit": {
                    "committer": {"date": "2026-07-23T20:00:00Z"},
                    "author": {"date": "2026-07-23T20:00:00Z"},
                    "tree": {"sha": "e" * 40},
                    "message": "Exact deployed release",
                },
            },
            None,
        ),
    )

    result = snapshot.capture_repository_snapshot(
        _context(expected),
        client=client,
        store=store,
    )

    assert result["status"] == "attached"
    assert result["commit_sha"] == expected
    assert result["exact_commit_verified"] is True
    assert result["commit_capture_method"] == "public_git_exact_sha"
    assert result["public_git_fallback_used"] is True
    assert result["api_commit_lookup_attempts"] == 3
    assert result["source"] == "public_git_read_only"
    assert store.audit_events[0]["action"] == "assessment.repository_snapshot_captured"
    assert store.audit_events[0]["payload"]["commit_capture_method"] == "public_git_exact_sha"


def test_private_repository_never_uses_public_git_fallback(monkeypatch) -> None:
    expected = "d" * 40
    client = FakeClient(private=True)
    fallback_called = False

    def fallback(repository: str, sha: str):
        nonlocal fallback_called
        fallback_called = True
        return None, "should_not_run"

    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: (None, "GitHub returned 403", 3),
    )
    monkeypatch.setattr(snapshot, "_public_git_exact_commit", fallback)

    result = snapshot.capture_repository_snapshot(
        _context(expected),
        client=client,
        store=AuditedMemoryStore(),
    )

    assert result["status"] == "unavailable"
    assert fallback_called is False
    assert result["public_git_fallback_attempted"] is False
    assert result["snapshot_failure_code"] == "repository_snapshot_commit_unavailable"


def test_api_commit_mismatch_never_falls_back(monkeypatch) -> None:
    expected = "d" * 40
    mismatched = "f" * 40
    client = FakeClient(private=False)
    fallback_called = False

    def fallback(repository: str, sha: str):
        nonlocal fallback_called
        fallback_called = True
        return None, "should_not_run"

    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: (
            {
                "sha": mismatched,
                "commit": {"tree": {"sha": "e" * 40}, "message": "Mismatch"},
            },
            None,
            1,
        ),
    )
    monkeypatch.setattr(snapshot, "_public_git_exact_commit", fallback)

    result = snapshot.capture_repository_snapshot(
        _context(expected),
        client=client,
        store=AuditedMemoryStore(),
    )

    assert result["status"] == "unavailable"
    assert fallback_called is False
    assert result["snapshot_failure_code"] == "repository_snapshot_commit_mismatch"


def test_successful_api_commit_remains_primary_path(monkeypatch) -> None:
    expected = "d" * 40
    client = FakeClient(private=False)
    store = AuditedMemoryStore()
    fallback_called = False

    def fallback(repository: str, sha: str):
        nonlocal fallback_called
        fallback_called = True
        return None, "should_not_run"

    monkeypatch.setattr(
        snapshot,
        "_retry_commit_lookup",
        lambda client, repository, ref: (
            {
                "sha": expected,
                "commit": {
                    "committer": {"date": "2026-07-23T20:00:00Z"},
                    "tree": {"sha": "e" * 40},
                    "message": "API exact release",
                },
            },
            None,
            1,
        ),
    )
    monkeypatch.setattr(snapshot, "_public_git_exact_commit", fallback)

    result = snapshot.capture_repository_snapshot(
        _context(expected),
        client=client,
        store=store,
    )

    assert result["status"] == "attached"
    assert result["commit_capture_method"] == "github_api_commit"
    assert result["public_git_fallback_used"] is False
    assert fallback_called is False
    assert store.audit_events[0]["action"] == "assessment.repository_snapshot_captured"
    assert store.audit_events[0]["payload"]["commit_capture_method"] == "github_api_commit"
