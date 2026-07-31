from __future__ import annotations

from nico.client_assessment_truth_v3 import normalize_client_assessment_truth
from nico.client_finding_remediation_register_v4 import (
    build_finding_remediation_register,
    finding_register_markdown,
    synchronize_canonical_finding_surfaces,
)


SHA = "d" * 40


def _finding(identifier: str, location: str, symbol: str) -> dict:
    return {
        "finding_id": identifier,
        "priority": "P1",
        "category": "architecture",
        "status": "open",
        "title": f"Reduce complexity in {symbol}",
        "location": location,
        "finding_family": "complexity_hotspot",
        "fact": "cyclomatic_complexity=74; loc=149; grade=F; method=python_ast",
        "interpretation": "High-complexity code hotspot",
        "business_impact": "Concentrated branching increases regression risk.",
        "recommendation": "Decompose the hotspot.",
        "acceptance_criteria": ["Complexity is at or below 30."],
        "exact_commit_match": True,
        "production_scope": True,
    }


def _canonical() -> dict:
    spanish_legacy = _finding(
        "RISK-P1-47E8089024",
        "nico/comprehensive_report_spanish_artifacts_v51.py:50",
        "_spanish_pdf",
    )
    spanish_stable = _finding(
        "NICO-FINDING-17F564182D49",
        "nico/comprehensive_report_spanish_artifacts_v51.py:50-223:50",
        "_spanish_pdf",
    )
    retainer_legacy = _finding(
        "RISK-P1-B47D9F98CA",
        "nico/retainer_modules.py:112",
        "build_retainer_modules",
    )
    retainer_stable = _finding(
        "NICO-FINDING-CCD6D6200DD4",
        "nico/retainer_modules.py:112-386:112",
        "build_retainer_modules",
    )
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": SHA,
            "run_id": "comprun_0368_regression",
        },
        "assessment": {
            "technical_score": 90,
            "canonical_evidence_adjusted_score": 90,
            "final_report_input_scores_synchronized": True,
            "report_contract_status": "blocked",
            "report_contract_reason": "canonical_score_truth_mismatch",
            "sections": [],
        },
        "stage_summaries": [
            {
                "stage_id": "decision_report_generation",
                "report_contract_status": "blocked",
                "report_contract_reason": "canonical_score_truth_mismatch",
                "final_report_input_scores_synchronized": True,
            }
        ],
        "canonical_findings": [
            spanish_legacy,
            spanish_stable,
            retainer_legacy,
            retainer_stable,
        ],
        "findings_register": [
            spanish_legacy,
            spanish_stable,
            retainer_legacy,
            retainer_stable,
        ],
        "complexity_evidence": {
            "hotspots": [
                {
                    "path": "nico/comprehensive_report_spanish_artifacts_v51.py",
                    "line": 50,
                    "name": "_spanish_pdf",
                    "cyclomatic_complexity": 74,
                    "source_excerpt": "def _spanish_pdf(canonical):\n    prepared = prepare(canonical)",
                },
                {
                    "path": "nico/retainer_modules.py",
                    "line": 112,
                    "name": "build_retainer_modules",
                    "cyclomatic_complexity": 73,
                    "source_excerpt": "def build_retainer_modules(canonical):\n    modules = []",
                },
            ]
        },
    }


def test_newest_report_duplicate_anchors_and_stale_contract_are_repaired() -> None:
    normalized = normalize_client_assessment_truth(_canonical())
    register = build_finding_remediation_register(normalized)
    synchronized = synchronize_canonical_finding_surfaces(normalized, register)
    markdown = finding_register_markdown(register, spanish=False)

    assert len(register["code_findings"]) == 2
    assert len(synchronized["canonical_findings"]) == 2
    assert register["summary"]["semantic_duplicate_code_anchors_absent"] is True
    assert register["summary"]["cross_population_duplicates_absent"] is True
    assert normalized["assessment"]["report_contract_status"] == "reconciled"
    assert normalized["stage_summaries"][0]["report_contract_status"] == "reconciled"
    assert "RISK-P1-47E8089024" not in markdown
    assert "RISK-P1-B47D9F98CA" not in markdown
    assert "def _spanish_pdf" in markdown
    assert "def build_retainer_modules" in markdown
