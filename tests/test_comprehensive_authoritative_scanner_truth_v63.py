from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_authoritative_scanner_truth_v63 import (
    reconcile_authoritative_scanner_truth,
)

TOOLS = [
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
]


def _record(name: str, *, completed: bool = True) -> dict[str, object]:
    return {
        "scanner_name": name,
        "tool": name,
        "status": "completed" if completed else "partial",
        "completed": completed,
        "verified": completed,
        "verified_complete": completed,
        "exact_commit_match": True,
        "artifact_hash": f"artifact-{name}",
        "findings": [],
        "required": True,
    }


def _canonical(*, gitleaks_complete: bool) -> dict[str, object]:
    records = [
        _record(name, completed=(name != "gitleaks" or gitleaks_complete))
        for name in TOOLS
    ]
    return {
        "identity": {"commit_sha": "a" * 40},
        "live_scanner_evidence": {
            "tools_requested": list(TOOLS),
            "tools_run": list(TOOLS),
            "failed_tools": [] if gitleaks_complete else ["gitleaks"],
            "unavailable_tools": [],
            "timed_out_tools": [],
        },
        "scanner_execution_records": deepcopy(records),
        "assessment": {
            "technical_score": 93,
            "scanner_execution_records": deepcopy(records),
            "evidence_coverage": {
                "applicable_analyzers": 9,
                "completed_verified_analyzers": 8,
                "incomplete_analyzers": ["gitleaks"],
                "analyzer_completion_percent": 89,
                "analyzer_execution_coverage": 100,
            },
            "evidence_completion_contract": {
                "single_source_of_truth": True,
                "analyzer_completion": {
                    "label": "Successful analyzer completion",
                    "total": 9,
                    "completed": 8,
                    "percent": 89,
                },
            },
            "evidence_health_summary": {
                "completed_scanners": [name for name in TOOLS if name != "gitleaks"],
                "incomplete_scanners": [
                    {"scanner": "gitleaks", "status": "partial", "required": True}
                ],
                "scanner_status_counts": {"complete": 8, "partial": 1},
                "required_scanner_failures": ["gitleaks"],
            },
        },
        "stage_summaries": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "evidence": [
                    "incomplete_analyzers[0]: gitleaks",
                    "analyzer_execution_coverage: 89",
                ],
            }
        ],
    }


def test_all_completed_exact_run_scanners_replace_stale_89_percent_projections() -> None:
    result = reconcile_authoritative_scanner_truth(_canonical(gitleaks_complete=True))
    assessment = result["assessment"]
    assert result["analyzer_execution_coverage"] == 100
    assert assessment["evidence_coverage"]["analyzer_completion_percent"] == 100
    assert assessment["evidence_coverage"]["analyzer_execution_coverage"] == 100
    assert assessment["evidence_coverage"]["completed_verified_analyzers"] == 9
    assert assessment["evidence_coverage"]["incomplete_analyzers"] == []
    completion = assessment["evidence_completion_contract"]["analyzer_completion"]
    assert completion == {
        "label": "Successful analyzer completion",
        "total": 9,
        "completed": 9,
        "percent": 100,
    }
    health = assessment["evidence_health_summary"]
    assert health["completed_scanners"] == TOOLS
    assert health["incomplete_scanners"] == []
    assert health["required_scanner_failures"] == []
    evidence = result["stage_summaries"][0]["evidence"]
    assert "incomplete_analyzers[0]: gitleaks" not in evidence
    assert "analyzer_execution_coverage: 100" in evidence
    assert all("analyzer_execution_coverage: 89" not in item for item in evidence)


def test_incomplete_exact_run_scanner_remains_visible_and_coverage_is_not_inflated() -> None:
    result = reconcile_authoritative_scanner_truth(_canonical(gitleaks_complete=False))
    assessment = result["assessment"]
    assert result["analyzer_execution_coverage"] == 89
    assert assessment["evidence_coverage"]["analyzer_completion_percent"] == 89
    assert assessment["evidence_coverage"]["completed_verified_analyzers"] == 8
    assert assessment["evidence_coverage"]["incomplete_analyzers"] == ["gitleaks"]
    completion = assessment["evidence_completion_contract"]["analyzer_completion"]
    assert completion["total"] == 9
    assert completion["completed"] == 8
    assert completion["percent"] == 89
    health = assessment["evidence_health_summary"]
    assert health["required_scanner_failures"] == ["gitleaks"]
    assert health["incomplete_scanners"][0]["scanner"] == "gitleaks"
    evidence = result["stage_summaries"][0]["evidence"]
    assert "incomplete_analyzers[0]: gitleaks" in evidence
    assert "analyzer_execution_coverage: 89" in evidence
