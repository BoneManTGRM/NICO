from __future__ import annotations

from nico.comprehensive_report_truth_stabilization_v52 import stabilize_report_package


def _sample() -> dict:
    finding_summary = {
        "finding_id": "SUMMARY",
        "title": "Reduce complexity in _spanish_pdf",
        "exact_source": "nico/spanish.py:50",
        "function": "_spanish_pdf",
        "rule_id": "complexity_hotspot",
        "observed_evidence": "complexity=74",
    }
    finding_detail = {
        "finding_id": "DETAIL",
        "title": "Reduce complexity in _spanish_pdf",
        "exact_source": "nico/spanish.py:50-223:50",
        "function": "_spanish_pdf",
        "rule_id": "complexity_hotspot",
        "observed_evidence": "complexity=74; loc=174; grade=F",
        "recommendation": "Split preparation, translation, layout, and validation.",
    }
    canonical = {
        "technical_score": 92,
        "canonical_technical_score": 92,
        "evidence_adjusted_score": 86,
        "canonical_evidence_adjusted_score": 86,
        "incomplete_analyzers": ["bandit"],
        "analyzer_execution_coverage": 89,
        "report_contract_status": "blocked",
        "report_contract_reason": "canonical_evidence_adjusted_score_mismatch",
        "findings": [finding_summary, finding_detail],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "status": "completed",
                "exact_commit_match": True,
                "findings": 0,
            }
        ],
    }
    return {
        "report_package": {
            "json": canonical,
            "markdown": "The canonical register contains 88 unique decision-grade findings. span ish_pdf",
            "html": "<html>The canonical register contains 88 unique decision-grade findings. co llect_snapshot_repository_evidence</html>",
            "report_quality_contract": {
                "report_contract_status": "blocked",
                "report_contract_reason": "canonical_evidence_adjusted_score_mismatch",
            },
        }
    }


def test_stabilization_reconciles_scanner_score_and_duplicates() -> None:
    result = stabilize_report_package(_sample())
    package = result["report_package"]
    canonical = package["json"]

    assert canonical["incomplete_analyzers"] == []
    assert canonical["analyzer_execution_coverage"] == 100
    assert canonical["report_contract_status"] == "ready_for_human_review"
    assert canonical["report_contract_reason"] == ""
    assert len(canonical["findings"]) == 1
    assert canonical["findings"][0]["finding_id"] == "DETAIL"
    assert canonical["finding_register_deduplicated"] is True
    assert canonical["scanner_state_reconciled"] is True


def test_stabilization_repairs_cross_format_identifiers_and_count() -> None:
    result = stabilize_report_package(_sample())
    package = result["report_package"]

    assert "span ish_pdf" not in package["markdown"]
    assert "_spanish_pdf" in package["markdown"]
    assert "co llect_snapshot_repository_evidence" not in package["html"]
    assert "collect_snapshot_repository_evidence" in package["html"]
    assert "contains 1 unique decision-grade findings" in package["markdown"]
    assert package["report_quality_contract"]["report_contract_status"] == "ready_for_human_review"
