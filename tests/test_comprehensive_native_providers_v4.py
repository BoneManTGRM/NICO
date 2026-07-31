from __future__ import annotations

from copy import deepcopy

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v4 as scoring


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
    commit_sha = "a" * 40
    return {
        "run_id": "comprun_real_90_v4",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": commit_sha,
        "evidence_ledger_id": "ledger_real_90_v4",
        "customer_id": "customer",
        "project_id": "project",
        "prior_stage_results": {},
    }


def _repo() -> dict:
    commit_sha = "a" * 40
    controls = {
        "cache": True,
        "concurrency": True,
        "timeout": True,
        "matrix": True,
        "artifact_upload": True,
        "environment_gate": True,
        "test_command": True,
        "lint_command": True,
        "build_command": True,
        "security_command": True,
        "deployment_command": True,
        "control_count": 11,
    }
    return {
        "architecture_evidence": {"source_file_count": 794, "test_path_count": 807},
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
            "workflow_file_count": 34,
            "workflow_configuration_snapshot_sha": commit_sha,
            "explicit_permissions_present": True,
            "configuration_controls": controls,
            "successful_runs": 84,
            "non_success_runs": 9,
            "jobs_observed": 25,
            "job_success_rate": 1.0,
            "deployments_observed": 10,
            "successful_deployments": 7,
        },
        "code_signal_evidence": {
            "risk_pattern_hits": 0,
            "excluded_non_production_risk_count": 0,
            "verified_example_placeholder_secret_count": 4,
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
    by_tool["osv-scanner"].update({"raw": 59, "review_required": 59})
    by_tool["gitleaks"].update({"raw": 6, "review_required": 6})
    by_tool["trufflehog"].update({"raw": 11, "review_required": 11})
    results = [
        {
            "tool": tool,
            "scanner_name": tool,
            "status": "completed_with_findings" if tool in {"osv-scanner", "gitleaks", "trufflehog"} else "completed",
            "completed": True,
            "verified": True,
            "exact_commit_match": True,
            "raw_artifact_retention_complete": True,
            "findings": [],
        }
        for tool in TOOLS
    ]
    return {
        "status": "complete",
        "scanner_results": results,
        "finding_summary": {"by_tool": by_tool},
        "unavailable_data_notes": [],
    }


def test_review_candidates_are_assurance_only_and_real_scores_exceed_90(monkeypatch) -> None:
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())
    monkeypatch.setattr(
        legacy,
        "_complexity",
        lambda context: {
            "complexity_score": 78,
            "files_analyzed": 795,
            "risk_level": "moderate",
        },
    )
    monkeypatch.setattr(legacy, "_scan", lambda context: _scan())

    result = scoring.canonical_scoring_provider(_context())
    assessment = result["assessment"]
    sections = {item["id"]: item for item in assessment["sections"]}

    assert result["status"] == "complete"
    assert sections["dependency_health"]["presented_score"] == 96
    assert sections["secrets_review"]["presented_score"] == 96
    assert sections["static_analysis"]["presented_score"] == 96
    assert assessment["technical_score"] >= 90
    assert assessment["canonical_evidence_adjusted_score"] >= 90
    assert assessment["technical_score"] == round(
        sum(item["presented_score"] for item in assessment["sections"]) / 7
    )
    assert assessment["evidence_coverage"]["percent"] == 100
    assert assessment["evidence_coverage"]["incomplete_analyzers"] == []
    assert assessment["score_contract"]["unverified_candidate_volume_affects_technical_score"] is False
    assert assessment["score_contract"]["target_score_not_used_as_input"] is True
    assert assessment["score_contract"]["score_override_allowed"] is False


def test_verified_material_finding_still_reduces_only_its_category(monkeypatch) -> None:
    scan = _scan()
    scan["finding_summary"]["by_tool"]["osv-scanner"].update(
        {"raw": 59, "material": 1, "review_required": 58}
    )
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())
    monkeypatch.setattr(
        legacy,
        "_complexity",
        lambda context: {"complexity_score": 78, "files_analyzed": 795, "risk_level": "moderate"},
    )
    monkeypatch.setattr(legacy, "_scan", lambda context: scan)

    result = scoring.canonical_scoring_provider(_context())
    sections = {item["id"]: item for item in result["assessment"]["sections"]}

    assert sections["dependency_health"]["presented_score"] == 78
    assert sections["secrets_review"]["presented_score"] == 96
    assert sections["static_analysis"]["presented_score"] == 96
    assert sections["dependency_health"]["score_contract"]["material_count"] == 1


def test_duplicate_complexity_records_collapse_and_preserve_aliases() -> None:
    assessment = {
        "findings_register": [
            {
                "id": "RISK-P1-ONE",
                "finding_id": "RISK-P1-ONE",
                "category": "architecture",
                "title": "Reduce complexity in _spanish_pdf",
                "location": "nico/report.py:50",
                "function_or_component": "_spanish_pdf",
                "analyzer_rule": "complexity_hotspot",
                "evidence": "cyclomatic_complexity=74",
            },
            {
                "id": "NICO-FINDING-TWO",
                "finding_id": "NICO-FINDING-TWO",
                "category": "architecture",
                "title": "Reduce complexity in _spanish_pdf",
                "location": "nico/report.py:50-223:50",
                "function_or_component": "_spanish_pdf",
                "analyzer_rule": "complexity_hotspot",
                "evidence": "cyclomatic_complexity=74; loc=149",
            },
        ]
    }

    result = scoring.deduplicate_finding_register(assessment)

    assert len(result["findings_register"]) == 1
    finding = result["findings_register"][0]
    assert set(finding["source_finding_ids"]) == {"RISK-P1-ONE", "NICO-FINDING-TWO"}
    assert finding["duplicate_source_records_reconciled"] == 1
    assert result["finding_deduplication_summary"]["duplicate_record_count_removed"] == 1


def _canonical(technical: int = 91) -> dict:
    return {
        "assessment": {
            "technical_score": technical,
            "canonical_evidence_adjusted_score": 90,
            "evidence_adjusted_score": 90,
            "maturity_signal": {
                "score": 90,
                "source_score": 90,
                "presented_score": 90,
                "technical_score": 90,
                "evidence_adjusted_score": 89,
            },
            "score_contract": {
                "technical_score": 90,
                "evidence_adjusted_score": 89,
            },
            "sections": [
                {"presented_score": 90},
                {"presented_score": 92},
            ],
        },
        "report_package": {
            "technical_score": 90,
            "evidence_adjusted_score": 89,
            "report_contract_status": "blocked",
            "report_contract_reason": "canonical_evidence_adjusted_score_mismatch",
        },
    }


def test_score_aliases_reconcile_only_after_section_average_verification() -> None:
    canonical = _canonical()

    repaired = scoring.repair_score_truth(canonical)

    assert repaired >= 1
    assessment = canonical["assessment"]
    assert assessment["maturity_signal"]["score"] == 91
    assert assessment["maturity_signal"]["evidence_adjusted_score"] == 90
    assert canonical["report_package"]["technical_score"] == 91
    assert canonical["report_package"]["evidence_adjusted_score"] == 90
    assert canonical["report_package"]["report_contract_status"] == "reconciled"
    assert canonical["score_alias_synchronization"]["section_average_verified"] is True


def test_real_score_disagreement_remains_blocked() -> None:
    canonical = _canonical(technical=90)
    original = deepcopy(canonical)

    scoring.repair_score_truth(canonical)

    assert canonical["report_package"]["report_contract_status"] == "blocked"
    assert canonical["report_package"]["technical_score"] == original["report_package"]["technical_score"]
