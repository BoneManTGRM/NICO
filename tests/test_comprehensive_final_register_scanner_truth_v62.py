from __future__ import annotations

from nico.comprehensive_final_register_scanner_truth_v62 import (
    install_comprehensive_final_register_scanner_truth_v62,
)


def test_final_register_boundary_reconciles_stale_coverage_aliases() -> None:
    from nico import client_report_completion_v2 as completion

    install_comprehensive_final_register_scanner_truth_v62()
    canonical = {
        "assessment": {
            "technical_score": 92,
            "analyzer_execution_coverage": 78,
            "incomplete_analyzers": ["bandit"],
        },
        "analyzer_execution_coverage": 100,
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "status": "completed",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "findings": [],
            },
            {
                "scanner_name": "eslint",
                "status": "completed",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "e" * 64,
                "findings": [],
            },
        ],
        "live_scanner_evidence": {
            "tools_requested": ["bandit", "eslint"],
            "tools_run": ["bandit", "eslint"],
            "failed_tools": [],
            "unavailable_tools": [],
            "timed_out_tools": [],
        },
        "canonical_findings": [],
        "findings_register": [],
    }

    result = completion._install_register(canonical)

    assert result["analyzer_execution_coverage"] == 100
    assert result["assessment"]["analyzer_execution_coverage"] == 100
    assert result["assessment"]["incomplete_analyzers"] == []
    contract = result["client_readiness_contract"]
    assert contract["coverage_numerator"] == 2
    assert contract["coverage_denominator"] == 2
    assert contract["incomplete_analyzers"] == []
    assert getattr(
        completion._install_register,
        "_nico_comprehensive_final_register_scanner_truth_v62",
        False,
    ) is True
