from __future__ import annotations

from nico.comprehensive_decision_content_restoration_v66 import (
    restore_decision_content,
)


COMMIT = "a" * 40


def _base_assessment() -> dict:
    return {
        "sections": [
            {
                "id": "ci_cd",
                "score_contract": {
                    "operational_trend": {
                        "successful_runs": 83,
                        "non_success_runs": 12,
                        "jobs_observed": 38,
                        "score_effect": "none",
                    }
                },
            }
        ]
    }


def test_restores_rich_structured_findings_without_duplicate_cards() -> None:
    finding = {
        "finding_id": "NICO-FINDING-ABC123",
        "category": "architecture",
        "finding_family": "complexity_hotspot",
        "priority": "P1",
        "title": "Reduce complexity in build_report",
        "location": "nico/report.py:40-120",
        "function": "build_report",
        "evidence": "cyclomatic_complexity=61; exact_commit_match=True",
        "business_impact": "Concentrated branching increases regression risk.",
        "recommendation": "Split preparation, rendering, and validation.",
        "acceptance_criteria": ["Complexity is at or below 30."],
        "owner_role": "Product Engineering Architect",
        "effort": "M-L",
        "rollback": "Revert the isolated remediation if verification fails.",
        "exit_criteria": ["The exact-SHA rerun no longer reports the condition."],
    }
    assessment = _base_assessment()
    assessment["findings_register"] = [finding, dict(finding)]

    canonical, restored, manifest = restore_decision_content(
        {"assessment": assessment},
        raw_stages={"evidence_reconciliation_and_scoring": {"assessment": assessment}},
        assessment=assessment,
        commit_sha=COMMIT,
    )

    assert len(canonical["canonical_findings"]) == 1
    assert canonical["decision_grade_finding_count"] == 1
    assert restored["findings_register"][0]["rollback"].startswith("Revert")
    assert manifest["structured_finding_count_recovered"] == 1
    assert manifest["complexity_finding_count_synthesized"] == 0


def test_restores_actionable_exact_sha_hotspots_when_register_is_missing() -> None:
    raw_stages = {
        "repository_and_delivery_evidence": {
            "complexity_evidence": {
                "hotspots": [
                    {
                        "path": "nico/report_builder.py",
                        "line": 50,
                        "end_line": 180,
                        "name": "build_report",
                        "cyclomatic_complexity": 74,
                        "method": "python_ast",
                    },
                    {
                        "path": "tests/test_report_builder.py",
                        "line": 10,
                        "end_line": 80,
                        "name": "test_report",
                        "cyclomatic_complexity": 90,
                        "method": "python_ast",
                    },
                    {
                        "path": "nico/small_helper.py",
                        "line": 8,
                        "end_line": 24,
                        "name": "small_helper",
                        "cyclomatic_complexity": 12,
                        "method": "python_ast",
                    },
                ]
            }
        }
    }

    canonical, restored, manifest = restore_decision_content(
        {"assessment": {}},
        raw_stages=raw_stages,
        assessment={},
        commit_sha=COMMIT,
    )

    assert len(canonical["canonical_findings"]) == 1
    finding = canonical["canonical_findings"][0]
    assert finding["title"] == "Reduce complexity in build_report"
    assert finding["location"] == "nico/report_builder.py:50-180"
    assert finding["status"] == "review_required"
    assert finding["exact_commit_match"] is True
    assert finding["verification"]
    assert finding["rollback"]
    assert finding["exit_criteria"]
    assert restored["architecture_hotspots"][0]["cyclomatic_complexity"] == 74
    assert manifest["complexity_finding_count_synthesized"] == 1


def test_retains_review_candidates_and_ci_history_without_promoting_defects() -> None:
    raw_stages = {
        "deep_scanner_triage": {
            "scanner_triage": {
                "finding_summary": {
                    "raw_total": 614,
                    "material_total": 0,
                    "review_required_total": 614,
                    "by_category": {
                        "dependency": {"raw": 59, "review_required": 59, "material": 0},
                        "secret": {"raw": 17, "review_required": 17, "material": 0},
                        "static": {"raw": 538, "review_required": 538, "material": 0},
                    },
                    "by_tool": {
                        "osv-scanner": {"raw": 59, "review_required": 59},
                        "bandit": {"raw": 538, "review_required": 538},
                        "gitleaks": {"raw": 6, "review_required": 6},
                        "trufflehog": {"raw": 11, "review_required": 11},
                    },
                }
            },
            "candidate": {
                "category": "dependency",
                "status": "review_required",
                "advisory_id": "GHSA-example",
                "title": "Candidate advisory",
                "package": "example-package",
                "installed_version": "1.0.0",
                "fixed_version": "1.0.1",
                "location": "requirements.txt",
            },
        }
    }
    assessment = _base_assessment()

    canonical, _restored, manifest = restore_decision_content(
        {"assessment": assessment},
        raw_stages=raw_stages,
        assessment=assessment,
        commit_sha=COMMIT,
    )

    assert canonical["canonical_findings"] == []
    assert canonical["review_required_candidate_count"] == 614
    assert canonical["review_candidate_summary"]["verified_material_total"] == 0
    assert canonical["review_candidate_summary"]["score_effect"] == "assurance_only_until_triaged"
    assert canonical["review_candidate_register"][0]["candidate_id"] == "GHSA-example"
    assert canonical["ci_operational_context"]["successful_runs"] == 83
    assert canonical["ci_operational_context"]["non_success_runs"] == 12
    assert canonical["ci_operational_context"]["technical_score_effect"] == "none"
    assert manifest["confirmed_defects_not_inferred_from_review_candidates"] is True


def test_explicit_zero_remains_zero_only_without_findings_or_hotspots() -> None:
    canonical, restored, manifest = restore_decision_content(
        {"assessment": {}},
        raw_stages={"authorization_and_scope": {"status": "complete"}},
        assessment={},
        commit_sha=COMMIT,
    )

    assert canonical["canonical_findings"] == []
    assert canonical["architecture_hotspots"] == []
    assert canonical["decision_grade_finding_count"] == 0
    assert restored["review_required_candidate_count"] == 0
    assert manifest["structured_finding_count_recovered"] == 0
    assert manifest["complexity_finding_count_synthesized"] == 0
