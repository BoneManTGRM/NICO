from __future__ import annotations

from nico.full_assessment_ci_evidence import (
    collect_ci_runtime_evidence,
    workflow_configuration_controls,
)


class FakeClient:
    def repo_url(self, repo: str, path: str = "") -> str:
        return f"https://api.github.test/repos/{repo}{path}"

    def get_json(self, url: str, params=None):
        if url.endswith("/actions/runs/11/jobs"):
            return {
                "jobs": [
                    {
                        "id": 101,
                        "name": "test",
                        "conclusion": "success",
                        "started_at": "2026-07-11T10:00:00Z",
                        "completed_at": "2026-07-11T10:02:00Z",
                        "runner_name": "runner-a",
                    },
                    {
                        "id": 102,
                        "name": "build",
                        "conclusion": "success",
                        "started_at": "2026-07-11T10:02:00Z",
                        "completed_at": "2026-07-11T10:05:00Z",
                        "runner_name": "runner-a",
                    },
                ]
            }, None
        if url.endswith("/actions/runs/12/jobs"):
            return {
                "jobs": [
                    {
                        "id": 103,
                        "name": "security",
                        "conclusion": "failure",
                        "started_at": "2026-07-10T10:00:00Z",
                        "completed_at": "2026-07-10T10:01:00Z",
                        "runner_name": "runner-b",
                    }
                ]
            }, None
        if url.endswith("/deployments"):
            return [{"id": 201, "environment": "production", "ref": "main", "created_at": "2026-07-11T11:00:00Z"}], None
        if url.endswith("/deployments/201/statuses"):
            return [{"state": "success"}], None
        return None, "404 private provider body"


def test_workflow_configuration_controls_detect_operational_controls() -> None:
    controls = workflow_configuration_controls(
        {
            ".github/workflows/ci.yml": """
permissions: read-all
concurrency: ci-${{ github.ref }}
jobs:
  test:
    timeout-minutes: 20
    strategy:
      matrix:
        python: ['3.12', '3.13']
    steps:
      - uses: actions/cache@v4
      - run: pytest
      - run: npm run lint
      - run: npm run build
      - run: semgrep scan
      - uses: actions/upload-artifact@v4
"""
        }
    )

    assert controls["cache"] is True
    assert controls["concurrency"] is True
    assert controls["timeout"] is True
    assert controls["matrix"] is True
    assert controls["artifact_upload"] is True
    assert controls["test_command"] is True
    assert controls["lint_command"] is True
    assert controls["build_command"] is True
    assert controls["security_command"] is True
    assert controls["control_count"] >= 9


def test_collect_ci_runtime_evidence_attaches_jobs_durations_and_deployments() -> None:
    result = collect_ci_runtime_evidence(
        FakeClient(),
        "BoneManTGRM/NICO",
        {".github/workflows/ci.yml": "concurrency: ci\njobs:\n  test:\n    timeout-minutes: 20\n    steps:\n      - run: pytest\n"},
        [{"id": 11, "name": "CI"}, {"id": 12, "name": "Security"}],
    )

    jobs = result["job_evidence"]
    deployments = result["deployment_evidence"]

    assert jobs["status"] == "complete"
    assert jobs["runs_inspected"] == 2
    assert jobs["runs_with_jobs"] == 2
    assert jobs["jobs_observed"] == 3
    assert jobs["successful_jobs"] == 2
    assert jobs["non_success_jobs"] == 1
    assert jobs["job_success_rate"] == 0.6667
    assert jobs["average_job_duration_seconds"] == 120
    assert jobs["median_job_duration_seconds"] == 120
    assert jobs["failed_job_samples"][0]["job_name"] == "security"
    assert "logs and secrets are not collected" in jobs["retention_note"]
    assert deployments["status"] == "complete"
    assert deployments["deployments_observed"] == 1
    assert deployments["successful_deployments"] == 1
    assert deployments["environments"] == ["production"]
    assert result["guardrail"].startswith("CI score credit is based on attached")


def test_ci_runtime_errors_are_sanitized() -> None:
    class DeniedClient:
        def repo_url(self, repo: str, path: str = "") -> str:
            return f"https://api.github.test/repos/{repo}{path}"

        def get_json(self, url: str, params=None):
            return None, "GitHub returned 403: secret provider detail"

    result = collect_ci_runtime_evidence(
        DeniedClient(),
        "BoneManTGRM/NICO",
        {},
        [{"id": 99, "name": "CI"}],
    )

    notes = result["unavailable_data_notes"]
    assert notes
    assert all("secret provider detail" not in note for note in notes)
    assert any("lacks required read access" in note for note in notes)
