from __future__ import annotations

from nico.full_assessment_repository_evidence import collect_repository_evidence
from nico.storage import MemoryAdapter


class FakeGitHubClient:
    def __init__(self) -> None:
        self.calls = 0
        self.files = {
            "README.md": "# NICO",
            "requirements.txt": "fastapi==0.115.0\npytest==8.4.0\n",
            "apps/web/package.json": '{"dependencies":{"next":"15.0.0"},"devDependencies":{"eslint":"9.0.0"}}',
            "apps/web/package-lock.json": '{"lockfileVersion":3}',
            ".github/workflows/ci.yml": (
                "permissions: read-all\nconcurrency: ci-${{ github.ref }}\njobs:\n  test:\n    timeout-minutes: 20\n"
                "    steps:\n      - uses: actions/cache@v4\n      - run: pytest\n      - run: npm run build\n"
                "      - uses: actions/upload-artifact@v4\n"
            ),
            "nico/app.py": "def health():\n    return 'ok'\n",
            "tests/test_app.py": "def test_health():\n    assert True\n",
            "Dockerfile": "FROM python:3.13-slim\n",
        }

    def repo_url(self, repo: str, path: str = "") -> str:
        return f"https://api.github.test/repos/{repo}{path}"

    def get_json(self, url: str, params=None):
        self.calls += 1
        if url.endswith("/actions/runs/1001/jobs"):
            return {
                "jobs": [
                    {
                        "id": 2001,
                        "name": "test",
                        "conclusion": "success",
                        "started_at": "2026-07-10T12:00:00Z",
                        "completed_at": "2026-07-10T12:03:00Z",
                        "runner_name": "GitHub Actions 1",
                    }
                ]
            }, None
        if url.endswith("/actions/runs/1002/jobs"):
            return {
                "jobs": [
                    {
                        "id": 2002,
                        "name": "build",
                        "conclusion": "failure",
                        "started_at": "2026-07-09T12:00:00Z",
                        "completed_at": "2026-07-09T12:02:00Z",
                        "runner_name": "GitHub Actions 2",
                    }
                ]
            }, None
        if url.endswith("/deployments"):
            return [
                {
                    "id": 3001,
                    "environment": "production",
                    "ref": "main",
                    "created_at": "2026-07-10T13:00:00Z",
                }
            ], None
        if url.endswith("/deployments/3001/statuses"):
            return [{"state": "success"}], None
        return None, "404"

    def get_repo(self, repo: str):
        self.calls += 1
        return {
            "full_name": repo,
            "default_branch": "main",
            "visibility": "private",
            "private": True,
            "archived": False,
            "language": "Python",
            "size": 321,
            "pushed_at": "2026-07-11T12:00:00Z",
        }, None

    def get_tree(self, _repo: str, _branch: str):
        self.calls += 1
        return [{"type": "blob", "path": path, "size": len(text)} for path, text in self.files.items()], None

    def get_contents(self, _repo: str, path: str = ""):
        self.calls += 1
        if not path:
            return [
                {"name": "README.md"},
                {"name": "nico"},
                {"name": "tests"},
                {"name": "apps"},
                {"name": ".github"},
            ], None
        if path == ".github/workflows":
            return [{"name": "ci.yml", "path": ".github/workflows/ci.yml"}], None
        return None, "404"

    def get_text_file(self, _repo: str, path: str):
        self.calls += 1
        if path in self.files:
            return self.files[path], None
        return None, "404"

    def get_commits(self, _repo: str, _since_iso: str):
        self.calls += 1
        return [
            {
                "sha": "a" * 40,
                "commit": {
                    "message": "Add evidence-bound repository collection",
                    "author": {"date": "2026-07-10T12:00:00Z"},
                },
            }
        ], None

    def get_pulls(self, _repo: str, _since):
        self.calls += 1
        return [
            {
                "number": 253,
                "state": "open",
                "merged_at": None,
                "updated_at": "2026-07-11T12:00:00Z",
                "title": "Attach GitHub repository evidence",
            }
        ], None

    def get_workflow_runs(self, _repo: str, _since_iso: str):
        self.calls += 1
        return [
            {"id": 1001, "name": "CI", "conclusion": "success"},
            {"id": 1002, "name": "CI", "conclusion": "failure"},
        ], None


class FailingClient:
    def get_repo(self, _repo: str):
        return None, "GitHub returned 403: private provider detail"


class UnexpectedClient:
    def get_repo(self, _repo: str):
        raise AssertionError("persisted evidence should be reused before GitHub is called")


def context(run_id: str = "fullrun_repo") -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "authorization_scope": "repository assessment only",
        "timeframe_days": 90,
    }


def test_collect_repository_evidence_attaches_real_github_summaries() -> None:
    store = MemoryAdapter()
    client = FakeGitHubClient()

    result = collect_repository_evidence(context(), client=client, store=store)

    assert result["status"] == "attached"
    assert result["run_id"] == "fullrun_repo"
    assert result["source"] == "github_api_read_only"
    assert result["timeframe_days"] == 90
    assert result["repository_metadata"]["default_branch"] == "main"
    assert result["repository_metadata"]["private"] is True
    assert result["activity_evidence"]["commits_returned"] == 1
    assert result["activity_evidence"]["pull_requests_returned"] == 1
    assert result["workflow_evidence"]["workflow_file_count"] == 1
    assert result["workflow_evidence"]["successful_runs"] == 1
    assert result["workflow_evidence"]["non_success_runs"] == 1
    assert "pytest" in result["workflow_evidence"]["commands_detected"]
    assert result["workflow_evidence"]["jobs_observed"] == 2
    assert result["workflow_evidence"]["successful_jobs"] == 1
    assert result["workflow_evidence"]["non_success_jobs"] == 1
    assert result["workflow_evidence"]["job_success_rate"] == 0.5
    assert result["workflow_evidence"]["configuration_controls"]["cache"] is True
    assert result["workflow_evidence"]["configuration_controls"]["concurrency"] is True
    assert result["workflow_evidence"]["configuration_controls"]["timeout"] is True
    assert result["workflow_evidence"]["deployments_observed"] == 1
    assert result["workflow_evidence"]["successful_deployments"] == 1
    assert result["dependency_evidence"]["dependency_entries"] == 4
    assert "apps/web/package-lock.json" in result["dependency_evidence"]["lockfile_paths"]
    assert result["architecture_evidence"]["source_file_count"] == 1
    assert result["architecture_evidence"]["test_path_count"] == 1
    assert result["code_signal_evidence"]["potential_secret_pattern_hits"] == 0
    stored = store.get("evidence_items", result["evidence_id"])
    assert stored is not None
    assert stored["run_id"] == "fullrun_repo"
    assert stored["evidence"]["repository"] == "BoneManTGRM/NICO"
    assert "CI logs" in result["retention_note"]
    assert client.calls > 0


def test_collect_repository_evidence_reuses_same_run_record() -> None:
    store = MemoryAdapter()
    first = collect_repository_evidence(context("fullrun_reuse"), client=FakeGitHubClient(), store=store)
    second = collect_repository_evidence(context("fullrun_reuse"), client=UnexpectedClient(), store=store)

    assert first["evidence_id"] == second["evidence_id"]
    assert second["idempotent_reuse"] is True
    assert len(store.list("evidence_items")) == 1


def test_collect_repository_evidence_discloses_access_failure_without_provider_body() -> None:
    store = MemoryAdapter()

    result = collect_repository_evidence(context("fullrun_unavailable"), client=FailingClient(), store=store)

    assert result["status"] == "unavailable"
    assert result["human_review_required"] is True
    note = result["unavailable_data_notes"][0]
    assert "lacks required read access" in note
    assert "private provider detail" not in note
    assert store.get("evidence_items", result["evidence_id"]) is not None


def test_repository_evidence_identity_is_run_bound() -> None:
    store = MemoryAdapter()
    first = collect_repository_evidence(context("fullrun_one"), client=FakeGitHubClient(), store=store)
    second = collect_repository_evidence(context("fullrun_two"), client=FakeGitHubClient(), store=store)

    assert first["evidence_id"] != second["evidence_id"]
    assert len(store.list("evidence_items")) == 2
