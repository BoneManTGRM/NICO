from __future__ import annotations

from nico.full_assessment_scorecard import build_full_assessment_scorecard


def _context() -> dict:
    return {
        "run_id": "fullrun_score_regression",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-score",
        "project_id": "proj-score",
    }


def _repo() -> dict:
    return {
        "status": "attached",
        "evidence_id": "repo-score-regression",
        "run_id": "fullrun_score_regression",
        "file_evidence": {"files_profiled": 40},
        "architecture_evidence": {
            "source_file_count": 120,
            "test_path_count": 25,
            "documentation_path_count": 12,
            "deployment_manifests": ["Dockerfile"],
            "top_level_directories": ["nico", "apps", "tests"],
        },
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt", "apps/web/package.json"],
            "lockfile_paths": ["apps/web/package-lock.json"],
            "dependency_entries": 60,
        },
        "activity_evidence": {
            "commits_returned": 100,
            "pull_requests_returned": 40,
            "merged_pull_requests": 35,
            "open_pull_requests": 5,
        },
        "workflow_evidence": {
            "workflow_file_count": 4,
            "workflow_run_count": 50,
            "successful_runs": 46,
            "non_success_runs": 4,
            "commands_detected": ["pytest", "npm run lint", "npm run build", "semgrep"],
            "explicit_permissions_present": True,
        },
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
        "run_id": "fullrun_score_regression",
        "scan_id": "scan-score-regression",
        "tools_requested": tools,
        "tools_run": tools,
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_data_notes": [],
    }


def test_score_only_changes_when_underlying_evidence_changes() -> None:
    baseline = build_full_assessment_scorecard(_context(), _repo(), _scanner())
    repeated = build_full_assessment_scorecard(_context(), _repo(), _scanner())

    assert repeated["maturity_signal"]["score"] == baseline["maturity_signal"]["score"]
    assert repeated["scorecard"]["weights"] == baseline["scorecard"]["weights"]

    degraded_repo = _repo()
    degraded_repo["workflow_evidence"] = {
        "workflow_file_count": 0,
        "workflow_run_count": 0,
        "successful_runs": 0,
        "non_success_runs": 0,
        "commands_detected": [],
        "explicit_permissions_present": False,
    }
    degraded = build_full_assessment_scorecard(_context(), degraded_repo, _scanner())

    assert degraded["maturity_signal"]["score"] < baseline["maturity_signal"]["score"]
    assert next(item for item in degraded["sections"] if item["id"] == "ci_cd")["score"] < next(
        item for item in baseline["sections"] if item["id"] == "ci_cd"
    )["score"]
