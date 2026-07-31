from __future__ import annotations

from copy import deepcopy

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v2 as scoring


TOOLS = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)


def _context() -> dict:
    return {
        "run_id": "comprun_scoring_v2",
        "repository": "example/product",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_scoring_v2",
        "customer_id": "customer",
        "project_id": "project",
        "prior_stage_results": {},
    }


def _repo() -> dict:
    return {
        "architecture_evidence": {"source_file_count": 100, "test_path_count": 120},
        "dependency_evidence": {
            "dependency_entries": 20,
            "lockfile_paths": ["requirements.txt", "apps/web/package-lock.json"],
        },
        "activity_evidence": {
            "commits_returned": 100,
            "pull_requests_returned": 100,
            "merged_pull_requests": 89,
        },
        "workflow_evidence": {
            "workflow_file_count": 20,
            "successful_runs": 88,
            "non_success_runs": 12,
            "runs_matching_snapshot_sha": 17,
            "explicit_permissions_present": True,
            "jobs_observed": 25,
            "job_success_rate": 1.0,
            "deployments_observed": 10,
            "successful_deployments": 8,
            "configuration_controls": {"control_count": 11},
        },
        "code_signal_evidence": {
            "risk_pattern_hits": 0,
            "excluded_non_production_risk_count": 15,
            "verified_example_placeholder_secret_count": 34,
            "analysis_version": "nico.source-signal-analysis.v2",
            "comments_and_strings_excluded": True,
        },
        "unavailable_data_notes": [],
    }


def _scan() -> dict:
    by_tool = {
        tool: {
            "raw": 0,
            "material": 0,
            "review_required": 0,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
        }
        for tool in TOOLS
    }
    results = [
        {
            "tool": tool,
            "scanner_name": tool,
            "status": "completed",
            "completed": True,
            "verified": True,
            "exact_commit_match": True,
            "raw_artifact_retention_complete": True,
            "findings": [],
        }
        for tool in TOOLS
    ]
    next(item for item in results if item["tool"] == "trufflehog").update(
        {
            "verified_example_placeholder_count": 34,
            "secret_candidate_disposition": {
                "raw_candidate_count": 34,
                "review_required": 0,
                "verified_example_placeholder": 34,
            },
        }
    )
    return {
        "status": "complete",
        "scanner_results": results,
        "finding_summary": {"by_tool": by_tool},
        "unavailable_data_notes": [],
    }


def test_strong_exact_sha_evidence_can_earn_90_without_override(monkeypatch) -> None:
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())
    monkeypatch.setattr(legacy, "_complexity", lambda context: {"complexity_score": 78, "files_analyzed": 100, "risk_level": "moderate"})
    monkeypatch.setattr(legacy, "_scan", lambda context: _scan())

    result = scoring.canonical_scoring_provider(_context())
    assessment = result["assessment"]
    sections = {item["id"]: item for item in assessment["sections"]}

    assert result["status"] == "complete"
    assert assessment["technical_score"] >= 90
    assert assessment["canonical_evidence_adjusted_score"] >= 90
    assert sections["architecture_debt"]["presented_score"] == 78
    assert sections["dependency_health"]["presented_score"] == 96
    assert sections["secrets_review"]["presented_score"] == 96
    assert sections["static_analysis"]["presented_score"] == 96
    assert assessment["score_contract"]["target_score_not_used_as_input"] is True
    assert assessment["score_contract"]["score_override_allowed"] is False


def test_dependency_candidates_do_not_lower_secret_or_static_scores(monkeypatch) -> None:
    scan = _scan()
    scan["finding_summary"]["by_tool"]["osv-scanner"].update(
        {"raw": 59, "review_required": 59}
    )
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())
    monkeypatch.setattr(legacy, "_complexity", lambda context: {"complexity_score": 78, "files_analyzed": 100, "risk_level": "moderate"})
    monkeypatch.setattr(legacy, "_scan", lambda context: scan)

    result = scoring.canonical_scoring_provider(_context())
    sections = {item["id"]: item for item in result["assessment"]["sections"]}

    assert sections["dependency_health"]["presented_score"] < 96
    assert sections["secrets_review"]["presented_score"] == 96
    assert sections["static_analysis"]["presented_score"] == 96


def test_incomplete_eslint_reduces_coverage_and_static_assurance(monkeypatch) -> None:
    scan = _scan()
    eslint = next(item for item in scan["scanner_results"] if item["tool"] == "eslint")
    eslint.update(
        {
            "status": "configuration_failed",
            "completed": False,
            "verified": False,
            "raw_artifact_retention_complete": True,
        }
    )
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())
    monkeypatch.setattr(legacy, "_complexity", lambda context: {"complexity_score": 78, "files_analyzed": 100, "risk_level": "moderate"})
    monkeypatch.setattr(legacy, "_scan", lambda context: scan)

    result = scoring.canonical_scoring_provider(_context())
    sections = {item["id"]: item for item in result["assessment"]["sections"]}

    assert sections["static_analysis"]["presented_score"] == 88
    assert "eslint" in result["assessment"]["evidence_coverage"]["incomplete_analyzers"]
    assert result["assessment"]["canonical_evidence_adjusted_score"] <= result["assessment"]["technical_score"]
