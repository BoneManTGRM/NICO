from __future__ import annotations

from nico.comprehensive_finding_count_truth_v66 import (
    reconcile_finding_count_truth,
)


def test_reconciles_false_zero_stage_aliases_without_touching_scanner_counts() -> None:
    canonical = {
        "canonical_findings": [
            {
                "finding_id": "NICO-FINDING-1",
                "title": "Reduce complexity in build_report",
                "location": "nico/report.py:50-180",
            }
        ],
        "stage_summaries": [
            {
                "stage_id": "risk_reduction_and_executive_briefing",
                "summary": "The canonical register contains 0 unique decision-grade findings.",
                "findings": ["No unresolved priority finding retained"],
                "evidence": ["Exact-source findings: 0 · Operational/context findings: 0"],
            }
        ],
        "assessment": {
            "canonical_finding_count": 0,
            "scanner_execution_records": [
                {"scanner_name": "osv-scanner", "finding_count": 59}
            ],
            "review_candidate_summary": {"review_required_total": 59},
        },
    }

    restored, manifest = reconcile_finding_count_truth(canonical)

    stage = restored["stage_summaries"][0]
    assert stage["summary"] == "The canonical register contains 1 unique decision-grade finding."
    assert stage["findings"] == ["Priority finding retained: Reduce complexity in build_report"]
    assert stage["evidence"] == ["Exact-source findings: 1 · Operational/context findings: 0"]
    assert restored["assessment"]["canonical_finding_count"] == 1
    assert restored["assessment"]["scanner_execution_records"][0]["finding_count"] == 59
    assert restored["assessment"]["review_candidate_summary"]["review_required_total"] == 59
    assert manifest["scanner_finding_counts_preserved"] is True


def test_zero_finding_truth_remains_zero_when_no_findings_exist() -> None:
    canonical = {
        "canonical_findings": [],
        "stage_summaries": [
            {
                "summary": "The canonical register contains 0 unique decision-grade findings.",
                "findings": ["No unresolved priority finding retained"],
            }
        ],
        "assessment": {"canonical_finding_count": 0},
    }

    restored, manifest = reconcile_finding_count_truth(canonical)

    assert restored["stage_summaries"][0]["summary"].endswith("0 unique decision-grade findings.")
    assert restored["stage_summaries"][0]["findings"] == ["No unresolved priority finding retained"]
    assert manifest["canonical_finding_count"] == 0
