from __future__ import annotations

import base64

from nico import comprehensive_final_artifact_truth_v53 as artifact_truth


def _finding() -> dict:
    return {
        "finding_id": "NICO-FINDING-ONE",
        "title": "Reduce complexity in _spanish_pdf",
        "exact_source": "nico/spanish.py:50-223:50",
        "function": "_spanish_pdf",
        "rule_id": "complexity_hotspot",
    }


def _operational() -> dict:
    return {
        "finding_id": "NICO-FINDING-TWO",
        "title": "GHSA-example",
        "priority": "P2",
        "recommendation": "Triage the dependency candidate.",
    }


def _package() -> dict:
    rows = [
        {"technical_score": 96, "weight": 0.20, "assurance_factor": 1.00, "included": True},
        {"technical_score": 96, "weight": 0.15, "assurance_factor": 0.98, "included": True},
        {"technical_score": 96, "weight": 0.15, "assurance_factor": 0.98, "included": True},
        {"technical_score": 85, "weight": 0.15, "assurance_factor": 1.00, "included": True},
        {"technical_score": 100, "weight": 0.15, "assurance_factor": 1.00, "included": True},
        {"technical_score": 78, "weight": 0.15, "assurance_factor": 1.00, "included": True},
        {"technical_score": 87, "weight": 0.05, "assurance_factor": 1.00, "included": True},
    ]
    assessment = {
        "technical_score": 92,
        "evidence_adjusted_score": 91,
        "canonical_evidence_adjusted_score": 91,
        "maturity_signal": {
            "score": 92,
            "source_score": 92,
            "technical_score": 92,
            "evidence_adjusted_score": 91,
            "canonical_evidence_adjusted_score": 91,
        },
        "scoring_weights": rows,
        "decision_grade_findings_register": [_finding(), _operational()],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "status": "completed",
                "exact_commit_match": True,
                "artifact_hash": "abc",
            }
        ],
        "incomplete_analyzers": [],
        "analyzer_execution_coverage": 100,
    }
    canonical = {
        "assessment": assessment,
        "findings_register": [_finding(), _operational()],
        "unique_finding_count": 2,
        "stage_summaries": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "evidence": [
                    "technical_score: 92",
                    "canonical_technical_score: 92",
                    "evidence_adjusted_score: 91",
                    "canonical_evidence_adjusted_score: 91",
                    "analyzer_execution_coverage: 100",
                ],
            }
        ],
    }
    return {
        "json": canonical,
        "markdown": "Technical maturity 92/100. Evidence-Adjusted 91/100. _spanish_pdf",
        "html": "<html>Technical maturity 92/100. Evidence-Adjusted 91/100. _spanish_pdf</html>",
        "pdf_base64": base64.b64encode(b"not-a-real-pdf").decode("ascii"),
    }


def test_final_artifact_validation_accepts_one_recomputable_truth(monkeypatch) -> None:
    monkeypatch.setattr(
        artifact_truth,
        "_pdf_text",
        lambda _pdf: "Technical maturity 92/100 Evidence-Adjusted 91/100 _spanish_pdf",
    )

    result = artifact_truth.validate_final_report_package(_package())

    assert result["status"] == "verified"
    assert result["failed_checks"] == []
    assert result["calculated_unique_finding_count"] == 2


def test_final_artifact_validation_blocks_stale_scanner_duplicate_and_identifier(monkeypatch) -> None:
    package = _package()
    canonical = package["json"]
    canonical["assessment"]["incomplete_analyzers"] = ["bandit"]
    canonical["assessment"]["analyzer_execution_coverage"] = 89
    canonical["findings_register"].append(_finding())
    package["markdown"] += " span ish_pdf"
    monkeypatch.setattr(
        artifact_truth,
        "_pdf_text",
        lambda _pdf: "Technical maturity 92/100 Evidence-Adjusted 91/100 span ish_pdf",
    )

    result = artifact_truth.validate_final_report_package(package)

    assert result["status"] == "blocked"
    assert "completed_scanners_not_incomplete" in result["failed_checks"]
    assert "finding_register_has_no_equivalent_duplicates" in result["failed_checks"]
    assert "markdown_identifier_integrity" in result["failed_checks"]
    assert "pdf_identifier_integrity" in result["failed_checks"]
