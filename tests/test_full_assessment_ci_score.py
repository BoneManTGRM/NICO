from __future__ import annotations

from copy import deepcopy

from nico.full_assessment_ci_score import apply_ci_runtime_score
from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS, build_full_assessment_scorecard


def _context() -> dict:
    return {
        "run_id": "fullrun_ci_score",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-ci",
        "project_id": "proj-ci",
    }


def _repo(with_jobs: bool = True) -> dict:
    workflow_evidence = {
        "workflow_file_count": 3,
        "workflow_run_count": 20,
        "successful_runs": 18,
        "non_success_runs": 2,
        "commands_detected": ["pytest", "npm run lint", "npm run build"],
        "explicit_permissions_present": True,
    }
    if with_jobs:
        workflow_evidence.update(
            {
                "runtime_evidence_status": "complete",
                "configuration_controls": {
                    "cache": True,
                    "concurrency": True,
                    "timeout": True,
                    "matrix": True,
                    "artifact_upload": False,
                    "environment_gate": False,
                },
                "job_evidence": {
                    "status": "complete",
                    "runs_with_jobs": 8,
                    "jobs_observed": 24,
                    "successful_jobs": 23,
                    "non_success_jobs": 1,
                    "job_success_rate": 0.9583,
                    "median_job_duration_seconds": 145,
                    "failed_job_samples": [{"job_name": "lint", "conclusion": "failure"}],
                },
                "deployment_evidence": {
                    "status": "complete",
                    "deployments_observed": 4,
                    "successful_deployments": 4,
                    "non_success_deployments": 0,
                },
            }
        )
    return {
        "status": "attached",
        "evidence_id": "repo-ci-score",
        "run_id": "fullrun_ci_score",
        "file_evidence": {"files_profiled": 40},
        "architecture_evidence": {
            "source_file_count": 100,
            "test_path_count": 20,
            "documentation_path_count": 10,
            "deployment_manifests": ["Dockerfile"],
            "top_level_directories": ["nico", "apps", "tests"],
        },
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt"],
            "lockfile_paths": ["package-lock.json"],
            "dependency_entries": 50,
        },
        "activity_evidence": {
            "commits_returned": 80,
            "pull_requests_returned": 30,
            "merged_pull_requests": 25,
            "open_pull_requests": 5,
        },
        "workflow_evidence": workflow_evidence,
        "code_signal_evidence": {
            "todo_fixme_security_notes": 0,
            "risk_pattern_hits": 0,
            "potential_secret_pattern_hits": 0,
        },
        "unavailable_data_notes": [],
    }


def _scanner() -> dict:
    tools = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint"]
    return {
        "status": "attached",
        "run_id": "fullrun_ci_score",
        "scan_id": "scan-ci-score",
        "tools_requested": tools,
        "tools_run": tools,
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_data_notes": [],
    }


def _ci(assessment: dict) -> dict:
    return next(item for item in assessment["sections"] if item["id"] == "ci_cd")


def test_job_level_evidence_raises_only_ci_section_and_preserves_weights() -> None:
    repo = _repo(with_jobs=True)
    baseline = build_full_assessment_scorecard(_context(), repo, _scanner())
    baseline_ci = _ci(baseline)["score"]
    baseline_other = {item["id"]: item["score"] for item in baseline["sections"] if item["id"] != "ci_cd"}

    updated = apply_ci_runtime_score(deepcopy(baseline), repo)
    updated_ci = _ci(updated)
    updated_other = {item["id"]: item["score"] for item in updated["sections"] if item["id"] != "ci_cd"}

    assert updated_ci["score"] > baseline_ci
    assert updated_ci["score"] <= 95
    assert updated_ci["confidence"] == "job-and-workflow-bound"
    assert updated_ci["score_evidence_breakdown"]["weights_changed"] is False
    assert updated_ci["score_evidence_breakdown"]["thresholds_changed"] is False
    assert updated_other == baseline_other
    assert updated["scorecard"]["weights"] == TECHNICAL_SECTION_WEIGHTS
    assert updated["scorecard"]["technical_score"] >= baseline["scorecard"]["technical_score"]
    assert updated["scorecard"]["ci_runtime_evidence"]["jobs_observed"] == 24
    assert any("job-level CI evidence" in line.lower() for line in updated_ci["evidence"])
    assert any("Job logs were not collected" in line for line in updated_ci["unavailable"])


def test_missing_job_evidence_does_not_change_score() -> None:
    repo = _repo(with_jobs=False)
    baseline = build_full_assessment_scorecard(_context(), repo, _scanner())

    updated = apply_ci_runtime_score(deepcopy(baseline), repo)

    assert _ci(updated)["score"] == _ci(baseline)["score"]
    assert updated["maturity_signal"]["score"] == baseline["maturity_signal"]["score"]
    assert updated["scorecard"]["ci_job_evidence_applied"] is False


def test_poor_job_evidence_does_not_receive_reliability_credit() -> None:
    repo = _repo(with_jobs=True)
    jobs = repo["workflow_evidence"]["job_evidence"]
    jobs.update(
        {
            "runs_with_jobs": 5,
            "jobs_observed": 12,
            "successful_jobs": 3,
            "non_success_jobs": 9,
            "job_success_rate": 0.25,
            "failed_job_samples": [{"job_name": "test", "conclusion": "failure"}],
        }
    )
    repo["workflow_evidence"]["configuration_controls"] = {}
    repo["workflow_evidence"]["deployment_evidence"] = {
        "status": "not_observed",
        "deployments_observed": 0,
        "successful_deployments": 0,
        "non_success_deployments": 0,
    }
    baseline = build_full_assessment_scorecard(_context(), repo, _scanner())

    updated = apply_ci_runtime_score(deepcopy(baseline), repo)
    breakdown = _ci(updated)["score_evidence_breakdown"]

    assert breakdown["job_evidence_increment"] <= 2
    assert any("non-success jobs outnumber" in reason for reason in breakdown["reasons"])
    assert any("Review 9 non-success job" in finding for finding in _ci(updated)["findings"])
