from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from urllib.parse import unquote
from uuid import uuid4

from nico.snapshot_repository_evidence import collect_snapshot_repository_evidence


class FakeSnapshotClient:
    def __init__(
        self,
        *,
        credential_used: bool = False,
        tree_truncated: bool = False,
        pull_error: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.commit_sha = "a" * 40
        self.tree_sha = "b" * 40
        self.credential_used = credential_used
        self.access_mode = (
            "authenticated_read_only"
            if credential_used
            else "anonymous_public"
        )
        self.headers = (
            {"Authorization": "Bearer sentinel-provider-secret"}
            if credential_used
            else {}
        )
        self.tree_truncated = tree_truncated
        self.pull_error = pull_error
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
                "sha": self.tree_sha,
                "truncated": self.tree_truncated,
                "tree": [
                    {"type": "blob", "path": path, "size": len(content.encode())}
                    for path, content in self.files.items()
                ],
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
        if self.pull_error:
            return [], self.pull_error
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
    snapshot_before = dict(snapshot)

    repository, complexity = collect_snapshot_repository_evidence(context, snapshot, client=client)

    assert repository["status"] == "attached"
    assert snapshot == snapshot_before
    assert repository["run_id"] == context["run_id"]
    assert repository["snapshot_id"] == snapshot["snapshot_id"]
    assert repository["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert repository["repository_metadata"]["commit_sha"] == snapshot["commit_sha"]
    assert repository["file_evidence"]["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert repository["dependency_evidence"]["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert repository["workflow_evidence"]["workflow_configuration_snapshot_sha"] == snapshot["commit_sha"]
    assert repository["code_signal_evidence"]["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert repository["repository_provider"] == "github"
    assert repository["repository_provider_instance"] == "github.com"
    assert repository["provider_access_observed"] is True
    assert repository["provider_access_binding_consistent"] is True
    assert repository["provider_access_mode"] == "anonymous_public"
    assert repository["provider_credential_used"] is False
    assert repository["required_source_evidence_complete"] is True
    assert repository["provider_pagination_complete"] is False
    assert repository["provider_source_fingerprint"].startswith("sha256:")
    assert len(repository["provider_source_fingerprint"]) == 71
    assert repository["assessment_snapshot_id"] == snapshot["snapshot_id"]
    assert repository["exact_source_locator_count"] == len(
        repository["exact_source_locators"]
    )
    assert repository["exact_source_locator_count"] == 6
    assert all(
        locator.startswith(
            f"https://github.com/BoneManTGRM/NICO/blob/{snapshot['commit_sha']}/"
        )
        and "?" not in locator
        and "#" not in locator
        for locator in repository["exact_source_locators"]
    )
    capability_states = {
        item["capability"]: item["state"]
        for item in repository["provider_capability_states"]
    }
    assert capability_states["repository"] == "supported"
    assert capability_states["tree"] == "supported"
    assert capability_states["source_links"] == "supported"
    assert any(
        "Link-header pagination proof was not retained" in note
        for note in repository["provider_collection_limitations"]
    )
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


def test_authenticated_access_truth_is_boolean_and_never_persists_secret() -> None:
    context = _context()
    snapshot = _snapshot(context)
    snapshot.update(
        {
            "provider": "github",
            "provider_instance": "github.com",
            "provider_access_observed": True,
            "access_mode": "authenticated_read_only",
            "credential_used": True,
        }
    )
    repository, _ = collect_snapshot_repository_evidence(
        context,
        snapshot,
        client=FakeSnapshotClient(credential_used=True),
    )

    assert repository["provider_access_mode"] == "authenticated_read_only"
    assert repository["provider_credential_used"] is True
    serialized = json.dumps(repository, sort_keys=True)
    assert "sentinel-provider-secret" not in serialized
    assert "Authorization" not in serialized


def test_snapshot_collection_access_drift_fails_closed_without_api_calls() -> None:
    context = _context()
    snapshot = _snapshot(context)
    snapshot.update(
        {
            "provider": "github",
            "provider_instance": "github.com",
            "provider_access_observed": True,
            "access_mode": "anonymous_public",
            "credential_used": False,
        }
    )
    client = FakeSnapshotClient(credential_used=True)

    repository, complexity = collect_snapshot_repository_evidence(
        context,
        snapshot,
        client=client,
    )

    assert repository["status"] == "unavailable"
    assert complexity["status"] == "unavailable"
    assert repository["provider_access_binding_consistent"] is False
    assert "changed after the immutable snapshot" in (
        repository["unavailable_data_notes"][0]
    )
    assert client.calls == []


def test_truncated_source_tree_is_not_claimed_as_complete() -> None:
    context = _context()
    snapshot = _snapshot(context)
    repository, _ = collect_snapshot_repository_evidence(
        context,
        snapshot,
        client=FakeSnapshotClient(tree_truncated=True),
    )

    assert repository["status"] == "attached"
    assert repository["required_source_evidence_complete"] is False
    states = {
        item["capability"]: item["state"]
        for item in repository["provider_capability_states"]
    }
    assert states["tree"] == "supported_limited"
    assert any(
        "truncated" in note.casefold()
        for note in repository["provider_collection_limitations"]
    )


def test_rate_limited_optional_capability_is_explicit() -> None:
    context = _context()
    snapshot = _snapshot(context)
    repository, _ = collect_snapshot_repository_evidence(
        context,
        snapshot,
        client=FakeSnapshotClient(
            pull_error="GitHub returned 429: rate limit reached"
        ),
    )

    assert repository["status"] == "attached"
    assert repository["required_source_evidence_complete"] is True
    assert repository["provider_rate_limit_state"]["limited"] is True
    states = {
        item["capability"]: item["state"]
        for item in repository["provider_capability_states"]
    }
    assert states["change_requests"] == "rate_limited"


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
