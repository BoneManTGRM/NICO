from __future__ import annotations

import base64
from datetime import datetime, timezone
from urllib.parse import unquote
from uuid import uuid4

from nico.snapshot_repository_evidence import collect_snapshot_repository_evidence


class FakeSnapshotClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.commit_sha = "a" * 40
        self.tree_sha = "b" * 40
        self.files = {
            "README.md": "# Snapshot project\n",
            "requirements.txt": "fastapi==0.115.0\n",
            "app.py": "def simple(value):\n    if value:\n        return 1\n    return 0\n",
            "service.py": "def calculate(a, b):\n    return a + b\n",
            "tests/test_app.py": "def test_simple():\n    assert True\n",
            ".github/workflows/ci.yml": "permissions: read-all\njobs:\n  test:\n    timeout-minutes: 10\n    steps:\n      - run: pytest\n",
        }

    def repo_url(self, repository: str, path: str = "") -> str:
        return f"https://api.github.test/repos/{repository}{path}"

    def get_json(self, url: str, params: dict | None = None):
        self.calls.append((url, params))
        suffix = url.split("/repos/BoneManTGRM/NICO", 1)[-1]
        if suffix.startswith("/git/trees/"):
            return {
                "tree": [
                    {"type": "blob", "path": path, "size": len(content.encode())}
                    for path, content in self.files.items()
                ]
            }, None
        if suffix == "/contents":
            return [{"name": "README.md"}, {"name": "app.py"}, {"name": "tests"}, {"name": ".github"}], None
        if suffix.startswith("/contents/"):
            path = unquote(suffix.removeprefix("/contents/"))
            content = self.files.get(path)
            if content is None:
                return None, "404"
            return {
                "type": "file",
                "size": len(content.encode()),
                "content": base64.b64encode(content.encode()).decode(),
            }, None
        if suffix == "/actions/runs/1/jobs":
            return {
                "jobs": [
                    {
                        "id": 11,
                        "name": "test",
                        "conclusion": "success",
                        "started_at": "2026-07-10T12:00:00Z",
                        "completed_at": "2026-07-10T12:02:00Z",
                        "runner_name": "hosted",
                    }
                ]
            }, None
        if suffix == "/deployments":
            return [], None
        return None, f"unexpected URL: {suffix}"

    def get_commits(self, repository: str, since_iso: str):
        return [
            {
                "sha": self.commit_sha,
                "commit": {"author": {"date": "2026-07-10T12:00:00Z"}, "message": "captured work"},
            },
            {
                "sha": "c" * 40,
                "commit": {"author": {"date": "2026-07-12T12:00:00Z"}, "message": "future work"},
            },
        ], None

    def get_pulls(self, repository: str, since: datetime):
        return [
            {"number": 10, "state": "closed", "merged_at": "2026-07-10T13:00:00Z", "updated_at": "2026-07-10T13:00:00Z", "title": "captured PR"},
            {"number": 11, "state": "open", "merged_at": None, "updated_at": "2026-07-12T13:00:00Z", "title": "future PR"},
        ], None

    def get_workflow_runs(self, repository: str, since_iso: str):
        return [
            {
                "id": 1,
                "name": "CI",
                "head_sha": self.commit_sha,
                "created_at": "2026-07-10T12:00:00Z",
                "conclusion": "success",
            },
            {
                "id": 2,
                "name": "Future CI",
                "head_sha": "c" * 40,
                "created_at": "2026-07-12T12:00:00Z",
                "conclusion": "failure",
            },
        ], None


def _context() -> dict:
    suffix = uuid4().hex[:10]
    return {
        "run_id": f"midrun_evidence_{suffix}",
        "repository": "BoneManTGRM/NICO",
        "customer_id": f"customer_{suffix}",
        "project_id": f"project_{suffix}",
        "authorization_scope": "repository assessment only",
        "timeframe_days": 180,
    }


def _snapshot(context: dict) -> dict:
    return {
        "status": "attached",
        "snapshot_id": f"snapshot_{uuid4().hex[:10]}",
        "run_id": context["run_id"],
        "repository": context["repository"],
        "customer_id": context["customer_id"],
        "project_id": context["project_id"],
        "captured_at": "2026-07-11T20:00:00Z",
        "default_branch": "main",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "repository_visibility": "private",
        "repository_pushed_at": "2026-07-11T19:59:00Z",
    }


def test_code_evidence_uses_exact_commit_ref_and_retains_snapshot_identity():
    context = _context()
    snapshot = _snapshot(context)
    client = FakeSnapshotClient()

    repository, complexity = collect_snapshot_repository_evidence(context, snapshot, client=client)

    assert repository["status"] == "attached"
    assert repository["run_id"] == context["run_id"]
    assert repository["snapshot_id"] == snapshot["snapshot_id"]
    assert repository["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert repository["repository_metadata"]["commit_sha"] == snapshot["commit_sha"]
    assert repository["file_evidence"]["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert repository["dependency_evidence"]["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert repository["workflow_evidence"]["workflow_configuration_snapshot_sha"] == snapshot["commit_sha"]
    assert repository["code_signal_evidence"]["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert complexity["status"] == "attached"
    assert complexity["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert complexity["run_id"] == context["run_id"]
    content_calls = [(url, params) for url, params in client.calls if "/contents" in url]
    assert content_calls
    assert all(params == {"ref": snapshot["commit_sha"]} for _, params in content_calls)
    tree_calls = [(url, params) for url, params in client.calls if "/git/trees/" in url]
    assert tree_calls == [(tree_calls[0][0], {"recursive": "1"})]
    assert snapshot["tree_sha"] in tree_calls[0][0]


def test_operational_history_is_bounded_to_capture_time_and_labeled_separately():
    context = _context()
    snapshot = _snapshot(context)
    repository, _ = collect_snapshot_repository_evidence(context, snapshot, client=FakeSnapshotClient())

    activity = repository["activity_evidence"]
    workflows = repository["workflow_evidence"]
    assert activity["status"] == "time_window_operational_evidence"
    assert activity["commits_returned"] == 1
    assert activity["pull_requests_returned"] == 1
    assert activity["sample_commits"][0]["sha"] == snapshot["commit_sha"][:12]
    assert activity["sample_pull_requests"][0]["number"] == 10
    assert workflows["workflow_run_count"] == 1
    assert workflows["successful_runs"] == 1
    assert workflows["non_success_runs"] == 0
    assert workflows["runs_matching_snapshot_sha"] == 1
    assert "historical operational evidence" in workflows["ci_runtime_guardrail"]
    assert "not exact-commit code evidence" in repository["operational_evidence_scope"]


def test_snapshot_workflow_configuration_and_job_evidence_are_distinct():
    context = _context()
    snapshot = _snapshot(context)
    repository, _ = collect_snapshot_repository_evidence(context, snapshot, client=FakeSnapshotClient())

    workflows = repository["workflow_evidence"]
    assert workflows["workflow_file_count"] == 1
    assert workflows["commands_detected"] == ["pytest"]
    assert workflows["explicit_permissions_present"] is True
    assert workflows["configuration_controls"]["timeout"] is True
    assert workflows["jobs_observed"] == 1
    assert workflows["successful_jobs"] == 1
    assert workflows["job_success_rate"] == 1.0


def test_snapshot_repository_evidence_is_idempotent_without_refetching():
    context = _context()
    snapshot = _snapshot(context)
    client = FakeSnapshotClient()

    first_repository, first_complexity = collect_snapshot_repository_evidence(context, snapshot, client=client)
    call_count = len(client.calls)
    second_repository, second_complexity = collect_snapshot_repository_evidence(context, snapshot, client=client)

    assert first_repository["evidence_id"] == second_repository["evidence_id"]
    assert first_complexity["evidence_id"] == second_complexity["evidence_id"]
    assert second_repository["idempotent_reuse"] is True
    assert second_complexity["idempotent_reuse"] is True
    assert len(client.calls) == call_count


def test_mismatched_snapshot_identity_is_unavailable_without_api_calls():
    context = _context()
    snapshot = _snapshot(context)
    snapshot["run_id"] = "different-run"
    client = FakeSnapshotClient()

    repository, complexity = collect_snapshot_repository_evidence(context, snapshot, client=client)

    assert repository["status"] == "unavailable"
    assert complexity["status"] == "unavailable"
    assert "matching run and repository identity" in repository["unavailable_data_notes"][0]
    assert client.calls == []


def test_future_activity_cannot_change_snapshot_code_signals():
    context = _context()
    snapshot = _snapshot(context)
    repository, complexity = collect_snapshot_repository_evidence(context, snapshot, client=FakeSnapshotClient())

    assert repository["file_evidence"]["files_profiled"] == 6
    assert repository["architecture_evidence"]["source_file_count"] == 2
    assert repository["activity_evidence"]["commits_returned"] == 1
    assert repository["activity_evidence"]["pull_requests_returned"] == 1
    assert complexity["profiled_file_count"] == 6
    assert repository["snapshot_commit_sha"] == "a" * 40
