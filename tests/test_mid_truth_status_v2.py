from __future__ import annotations

from nico.mid_truth_status import attach_mid_truth_status, build_mid_evidence_coverage


def _section(section_id: str, score: int, unavailable: list[str] | None = None) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "green" if score >= 80 else "yellow",
        "summary": f"Evidence-bound summary for {section_id}.",
        "evidence": [f"Direct evidence for {section_id}."],
        "findings": [],
        "unavailable": unavailable or [],
    }


def _result() -> dict:
    sha = "a" * 40
    return {
        "status": "complete",
        "run_id": "midrun_truth_v2",
        "repository_snapshot": {"status": "attached", "snapshot_id": "snapshot_one", "commit_sha": sha},
        "repository_evidence": {
            "status": "attached",
            "snapshot_commit_sha": sha,
            "file_evidence": {"files_profiled": 120},
            "dependency_evidence": {"manifest_paths": ["requirements.txt"], "dependency_entries": 20},
            "workflow_evidence": {"workflow_file_count": 5, "jobs_observed": 10, "deployments_observed": 2, "workflow_configuration_snapshot_sha": sha},
            "activity_evidence": {"commits_returned": 30, "pull_requests_returned": 20},
        },
        "complexity_evidence": {"status": "attached", "files_analyzed": 118, "snapshot_commit_sha": sha},
        "scanner_evidence": {
            "status": "attached",
            "scan_id": "scan_one",
            "snapshot_match": True,
            "tools_requested": ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript", "gitleaks", "trufflehog"],
            "tools_run": ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript", "gitleaks", "trufflehog"],
            "failed_tools": [],
            "timed_out_tools": [],
            "unavailable_tools": [],
            "full_history_verified_tools": ["gitleaks", "trufflehog"],
        },
        "assessment": {
            "sections": [
                _section("code_audit", 88, ["This score does not replace line-by-line semantic code review."]),
                _section("dependency_health", 88, ["A clean scanner result does not prove that no vulnerability exists."]),
                _section("secrets_review", 90, ["Clean scanner execution reduces observed risk but is not proof that no credential exists outside the scanned repository history."]),
                _section("static_analysis", 86, ["Completed analyzer execution does not prove that no vulnerability exists."]),
                _section("ci_cd", 92, ["Runtime history is time-window operational evidence."]),
                _section("architecture_debt", 90, ["Call-graph, coupling, duplication, and cyclomatic-complexity conclusions require language-specific analyzer output."]),
                _section("velocity_complexity", 84, ["Story-point expectations, developer seniority, review quality, and business-value delivery require stakeholder context and human review."]),
            ],
            "maturity_signal": {"score": 88, "level": "Senior"},
        },
        "optional_evidence": {"section_availability": {}},
    }


def test_mid_coverage_builds_a_real_ledger_and_reaches_all_explicit_units() -> None:
    result = _result()

    coverage = build_mid_evidence_coverage(result)

    assert coverage["calculated"] is True
    assert coverage["numerator"] == coverage["denominator"] == 12
    assert coverage["percent"] == 100
    assert result["evidence_ledger"]["entry_count"] > 0
    assert result["evidence_ledger"]["ledger_hash"]
    assert result["assessment"]["evidence_ledger"]["generated_from_attached_evidence_only"] is True


def test_general_caveats_remain_disclosures_without_downgrading_complete_evidence() -> None:
    result = _result()

    attach_mid_truth_status(result)
    sections = {item["id"]: item for item in result["assessment"]["sections"]}

    assert all(section["truth_status"] == "Verified" for section in sections.values())
    assert sections["code_audit"]["unavailable"] == []
    assert sections["code_audit"]["scope_disclosures"] == ["This score does not replace line-by-line semantic code review."]
    assert sections["architecture_debt"]["unavailable"] == []
    assert result["mid_truth_status"]["version"] == "mid-truth-status-v2"
    assert result["mid_truth_status"]["summary"]["verified"] == 7
    assert result["mid_truth_status"]["summary"]["verified_with_limitations"] == 0
    assert result["review_summary"]["scope_disclosures"] >= 6


def test_actual_missing_tool_still_creates_a_verified_with_limitations_section() -> None:
    result = _result()
    result["scanner_evidence"]["tools_run"].remove("eslint")
    result["scanner_evidence"]["unavailable_tools"] = ["eslint"]
    result["assessment"]["sections"][3]["unavailable"] = ["ESLint exact-snapshot execution status=not run."]

    attach_mid_truth_status(result)
    static = next(item for item in result["assessment"]["sections"] if item["id"] == "static_analysis")

    assert static["truth_status"] == "Verified with limitations"
    assert static["unavailable"] == ["ESLint exact-snapshot execution status=not run."]
