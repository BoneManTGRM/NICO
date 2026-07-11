from __future__ import annotations

from nico.full_assessment_scorecard import (
    TECHNICAL_SECTION_WEIGHTS,
    build_full_assessment_scorecard,
    full_assessment_scoring_handler,
)


def _context(run_id: str = "fullrun_score") -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "client_name": "Client A",
        "project_name": "Project A",
    }


def _repository(run_id: str = "fullrun_score") -> dict:
    return {
        "status": "attached",
        "evidence_id": "evidence_repo_score",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "file_evidence": {"files_profiled": 40, "tree_paths_seen": 300},
        "architecture_evidence": {
            "source_file_count": 120,
            "test_path_count": 25,
            "documentation_path_count": 12,
            "deployment_manifests": ["Dockerfile", "render.yaml"],
            "top_level_directories": ["nico", "apps", "tests", "docs", ".github"],
        },
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt", "apps/web/package.json"],
            "lockfile_paths": ["apps/web/package-lock.json"],
            "dependency_entries": 60,
            "ecosystems": ["PyPI", "npm"],
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
            "todo_fixme_security_notes": 2,
            "risk_pattern_hits": 0,
            "potential_secret_pattern_hits": 0,
        },
        "unavailable_data_notes": [],
    }


def _scanner(run_id: str = "fullrun_score") -> dict:
    return {
        "status": "attached",
        "run_id": run_id,
        "scan_id": "scan_score",
        "tools_requested": ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "gitleaks"],
        "tools_run": ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "gitleaks"],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_data_notes": [],
    }


def _outputs(run_id: str = "fullrun_score") -> dict:
    return {
        "repo_evidence": {"status": "complete", "repository_evidence": _repository(run_id)},
        "evidence_attachment": {"status": "complete", "scanner_evidence": _scanner(run_id)},
    }


def test_scorecard_builds_seven_weighted_technical_sections_plus_integrity() -> None:
    assessment = build_full_assessment_scorecard(_context(), _repository(), _scanner())

    sections = assessment["sections"]
    by_id = {item["id"]: item for item in sections}

    assert len(sections) == 8
    assert set(TECHNICAL_SECTION_WEIGHTS).issubset(by_id)
    assert "evidence_integrity" in by_id
    assert assessment["maturity_signal"]["score"] >= 80
    assert assessment["maturity_signal"]["level"] == "Senior"
    assert assessment["scorecard"]["evidence_readiness_score"] >= 90
    assert by_id["ci_cd"]["status"] == "green"
    assert by_id["dependency_health"]["confidence"] == "scanner-and-repository-bound"
    assert assessment["client_delivery_verdict"]["status"] == "human_review_required"
    assert assessment["human_review_required"] is True
    assert assessment["client_ready"] is False
    assert assessment["repository_evidence_id"] == "evidence_repo_score"
    assert assessment["scanner_evidence_id"] == "scan_score"


def test_secrets_score_does_not_claim_clean_without_dedicated_scanner() -> None:
    scanner = _scanner()
    scanner["tools_requested"] = [item for item in scanner["tools_requested"] if item != "gitleaks"]
    scanner["tools_run"] = [item for item in scanner["tools_run"] if item != "gitleaks"]

    assessment = build_full_assessment_scorecard(_context(), _repository(), scanner)
    secrets = next(item for item in assessment["sections"] if item["id"] == "secrets_review")

    assert secrets["score"] <= 68
    assert secrets["confidence"] == "limited"
    assert any("not proof" in note for note in secrets["unavailable"])


def test_scoring_handler_waits_until_both_evidence_sets_are_attached() -> None:
    result = full_assessment_scoring_handler(
        _context(),
        {
            "repo_evidence": {"repository_evidence": _repository()},
            "evidence_attachment": {"evidence": {"status": "pending", "run_id": "fullrun_score"}},
        },
    )

    assert result["status"] == "planned"
    assert result["evidence"]["repository_evidence_status"] == "attached"
    assert result["evidence"]["scanner_evidence_status"] == "not_attached"
    assert "assessment" not in result


def test_scoring_handler_blocks_mismatched_repository_run() -> None:
    outputs = _outputs()
    outputs["repo_evidence"]["repository_evidence"]["run_id"] = "other_run"

    result = full_assessment_scoring_handler(_context(), outputs)

    assert result["status"] == "blocked"
    assert result["evidence"]["repository_evidence_run_id"] == "other_run"
    assert "assessment" not in result


def test_scoring_handler_returns_multi_section_assessment_and_evidence_ids() -> None:
    result = full_assessment_scoring_handler(_context(), _outputs())

    assert result["status"] == "complete"
    assert result["evidence"]["repository_evidence_id"] == "evidence_repo_score"
    assert result["evidence"]["scanner_evidence_id"] == "scan_score"
    assert result["evidence"]["sections"] == 8
    assert result["assessment"]["scorecard"]["technical_score"] == result["evidence"]["technical_score"]
