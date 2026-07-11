from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from nico import scanner_worker as base_scanner
from nico import snapshot_assessment_handlers as handlers
from nico import snapshot_scanner_worker as snapshot_scanner
from nico.repository_snapshot import capture_repository_snapshot, repository_snapshot_id
from nico.storage import STORE


class FakeGitHubClient:
    def __init__(self, sha: str = "a" * 40) -> None:
        self.sha = sha
        self.repo_calls = 0
        self.commit_calls = 0

    def get_repo(self, repository: str):
        self.repo_calls += 1
        return {
            "full_name": repository,
            "default_branch": "main",
            "visibility": "private",
            "private": True,
            "pushed_at": "2026-07-11T20:00:00Z",
        }, None

    def get_commit(self, repository: str, ref: str):
        self.commit_calls += 1
        return {
            "sha": self.sha,
            "commit": {
                "message": "Bind deep assessment to one exact commit",
                "committer": {"date": "2026-07-11T20:00:00Z"},
                "author": {"date": "2026-07-11T19:59:00Z"},
                "tree": {"sha": "b" * 40},
            },
        }, None


def _context() -> dict:
    suffix = uuid4().hex[:10]
    return {
        "run_id": f"midrun_snapshot_{suffix}",
        "repository": "BoneManTGRM/NICO",
        "customer_id": f"customer_{suffix}",
        "project_id": f"project_{suffix}",
        "authorized_by": "owner",
        "authorization_scope": "repository assessment only",
        "run_scanners": True,
        "tools": ["bandit"],
    }


@pytest.fixture(autouse=True)
def isolated_scan_jobs():
    original = dict(base_scanner.SCAN_JOBS)
    base_scanner.SCAN_JOBS.clear()
    yield
    base_scanner.SCAN_JOBS.clear()
    base_scanner.SCAN_JOBS.update(original)


def test_snapshot_capture_persists_exact_commit_and_is_idempotent():
    context = _context()
    client = FakeGitHubClient("a" * 40)

    first = capture_repository_snapshot(context, client=client)
    client.sha = "c" * 40
    second = capture_repository_snapshot(context, client=client)

    assert first["status"] == "attached"
    assert first["snapshot_id"] == repository_snapshot_id(context["run_id"], context["repository"])
    assert first["commit_sha"] == "a" * 40
    assert first["tree_sha"] == "b" * 40
    assert first["default_branch"] == "main"
    assert first["run_id"] == context["run_id"]
    assert second["commit_sha"] == "a" * 40
    assert second["idempotent_reuse"] is True
    assert client.commit_calls == 1
    stored = STORE.get("evidence_items", first["snapshot_id"])
    assert stored["evidence"]["commit_sha"] == "a" * 40


def test_snapshot_capture_does_not_claim_attachment_without_full_commit_sha():
    context = _context()
    client = FakeGitHubClient("short-sha")

    result = capture_repository_snapshot(context, client=client)

    assert result["status"] == "unavailable"
    assert result["idempotent_reuse"] is False
    assert "exact default-branch commit" in result["unavailable_data_notes"][0]
    assert STORE.get("evidence_items", result["snapshot_id"]) is None


def test_clone_repository_at_snapshot_verifies_exact_head(monkeypatch):
    monkeypatch.setattr(snapshot_scanner.shutil, "which", lambda name: "/usr/bin/git")

    def fake_git(command, *, cwd, env, timeout=90):
        if command[1] == "clone":
            Path(command[-1]).mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(command, 0, "cloned", "")
        if command[1] == "rev-parse":
            return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(snapshot_scanner, "_git", fake_git)
    monkeypatch.setattr(base_scanner, "directory_size", lambda path: 100)
    with tempfile.TemporaryDirectory() as workspace:
        repo_path, actual_sha, notes = snapshot_scanner.clone_repository_at_snapshot(
            "BoneManTGRM/NICO",
            "a" * 40,
            Path(workspace),
            {"PATH": "/usr/bin"},
        )

    assert repo_path is not None
    assert actual_sha == "a" * 40
    assert notes == []


def test_clone_repository_blocks_mismatched_checkout(monkeypatch):
    monkeypatch.setattr(snapshot_scanner.shutil, "which", lambda name: "/usr/bin/git")

    def fake_git(command, *, cwd, env, timeout=90):
        if command[1] == "clone":
            Path(command[-1]).mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(command, 0, "cloned", "")
        if command[1] == "rev-parse":
            return subprocess.CompletedProcess(command, 0, "c" * 40 + "\n", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(snapshot_scanner, "_git", fake_git)
    with tempfile.TemporaryDirectory() as workspace:
        repo_path, actual_sha, notes = snapshot_scanner.clone_repository_at_snapshot(
            "BoneManTGRM/NICO",
            "a" * 40,
            Path(workspace),
            {"PATH": "/usr/bin"},
        )

    assert repo_path is None
    assert actual_sha == "c" * 40
    assert any("did not match" in note for note in notes)


def test_snapshot_handlers_queue_scanner_with_same_run_and_commit(monkeypatch):
    context = _context()
    snapshot = {
        "status": "attached",
        "snapshot_id": "snapshot_example",
        "run_id": context["run_id"],
        "repository": context["repository"],
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "default_branch": "main",
    }
    captured_payload = {}
    monkeypatch.setattr(handlers, "capture_repository_snapshot", lambda value: dict(snapshot))

    def fake_start(payload):
        captured_payload.update(payload)
        return {
            "status": "queued",
            "scan_id": "scan_snapshot_test",
            "run_id": payload["run_id"],
            "snapshot_id": payload["snapshot_id"],
            "snapshot_commit_sha": payload["snapshot_commit_sha"],
            "tools_requested": payload["tools"],
        }

    monkeypatch.setattr(handlers, "start_snapshot_scan", fake_start)
    repo_output = handlers._snapshot_repository_handler(context, {})
    scan_output = handlers._snapshot_scanner_handler(context, {"repo_evidence": repo_output})

    assert repo_output["status"] == "complete"
    assert scan_output["status"] == "queued"
    assert captured_payload["run_id"] == context["run_id"]
    assert captured_payload["snapshot_id"] == snapshot["snapshot_id"]
    assert captured_payload["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert captured_payload["repository"] == context["repository"]


def test_existing_scanner_with_different_snapshot_is_blocked(monkeypatch):
    context = {**_context(), "scan_id": "scan_existing"}
    snapshot = {
        "status": "attached",
        "snapshot_id": "snapshot_expected",
        "commit_sha": "a" * 40,
    }
    monkeypatch.setattr(
        handlers,
        "get_scan",
        lambda scan_id: {
            "status": "complete",
            "scan_id": scan_id,
            "run_id": context["run_id"],
            "snapshot_id": "snapshot_other",
            "snapshot_commit_sha": "c" * 40,
            "snapshot_match": True,
        },
    )

    result = handlers._snapshot_scanner_handler(
        context,
        {"repo_evidence": {"repository_snapshot": snapshot}},
    )

    assert result["status"] == "blocked"
    assert "does not match" in result["message"]
    assert result["evidence"]["scanner_snapshot_id"] == "snapshot_other"


def test_attachment_requires_completed_exact_snapshot_match():
    context = _context()
    snapshot = {"status": "attached", "snapshot_id": "snapshot_test", "commit_sha": "a" * 40}
    scan = {
        "status": "complete",
        "scan_id": "scan_test",
        "run_id": context["run_id"],
        "snapshot_id": "snapshot_test",
        "snapshot_commit_sha": "a" * 40,
        "actual_commit_sha": "a" * 40,
        "snapshot_match": True,
        "tools_requested": ["bandit"],
        "tools_run": ["bandit"],
        "scanner_results": [{"scanner": "bandit", "status": "passed"}],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_data_notes": [],
    }
    result = handlers._snapshot_evidence_attachment_handler(
        context,
        {
            "repo_evidence": {"repository_snapshot": snapshot},
            "scanner_worker": {"status": "complete", "scan": scan},
        },
    )

    assert result["status"] == "complete"
    assert result["scanner_evidence"]["snapshot_match"] is True
    assert result["scanner_evidence"]["snapshot_commit_sha"] == "a" * 40
    assert result["scanner_evidence"]["actual_commit_sha"] == "a" * 40


def test_attachment_marks_nonmatching_scanner_unavailable():
    context = _context()
    snapshot = {"status": "attached", "snapshot_id": "snapshot_test", "commit_sha": "a" * 40}
    result = handlers._snapshot_evidence_attachment_handler(
        context,
        {
            "repo_evidence": {"repository_snapshot": snapshot},
            "scanner_worker": {
                "status": "unavailable",
                "scan": {
                    "status": "unavailable",
                    "scan_id": "scan_test",
                    "actual_commit_sha": "c" * 40,
                    "snapshot_match": False,
                },
            },
        },
    )

    assert result["status"] == "unavailable"
    assert "could not be attached" in result["message"]


def test_snapshot_handler_set_replaces_repository_scanner_and_attachment_steps():
    configured = handlers.snapshot_bound_assessment_handlers()

    assert configured["repo_evidence"] is handlers._snapshot_repository_handler
    assert configured["scanner_worker"] is handlers._snapshot_scanner_handler
    assert configured["evidence_attachment"] is handlers._snapshot_evidence_attachment_handler
    assert "scoring" in configured
    assert "reports" in configured
    assert "approval_request" in configured
