from __future__ import annotations

from nico.production_report_truth_gate_v1 import reconcile_production_report_truth
from nico.scanner_command_repair_v1 import install_scanner_command_repair
import nico.scanner_tool_runners as scanner_module


def _package() -> dict:
    return {
        "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
        "json": {
            "assessment": {
                "technical_score": 79,
                "evidence_adjusted_score": 77,
                "maturity_signal": {"score": 79, "presented_score": 79},
                "sections": [
                    {
                        "id": "static_analysis",
                        "label": "Static Analysis",
                        "evidence": ["bandit: status=failed", "eslint: status=missing"],
                        "findings": [],
                        "unavailable": ["bandit exact-SHA evidence remains failed"],
                    },
                    {
                        "id": "secrets_exposure_review",
                        "label": "Secrets Exposure Review",
                        "evidence": ["gitleaks: status=missing"],
                        "findings": [],
                        "unavailable": [],
                    },
                ],
                "scanner_execution_records": [
                    {"tool": "bandit", "status": "failed", "current_run": False},
                    {"tool": "eslint", "status": "missing", "current_run": False},
                ],
            },
            "scanner_execution_records": [
                {
                    "tool": "bandit",
                    "status": "completed",
                    "current_run": True,
                    "execution_observed_for_this_report": True,
                    "exact_commit_match": True,
                    "artifact_hash": "b" * 64,
                    "output_truncated": False,
                    "timed_out": False,
                    "category": "static",
                    "findings": [],
                },
                {
                    "tool": "eslint",
                    "status": "completed",
                    "current_run": True,
                    "exact_commit_match": True,
                    "artifact_hash": "e" * 64,
                    "category": "static",
                    "findings": [],
                },
                {
                    "tool": "gitleaks",
                    "status": "completed",
                    "current_run": True,
                    "exact_commit_match": True,
                    "artifact_hash": "g" * 64,
                    "category": "secret",
                    "scans_git_history": True,
                    "full_history_verified": True,
                    "findings": [],
                },
            ],
            "canonical_findings": [
                {"finding_id": "RISK-OLD", "category": "architecture", "title": "Hotspot", "location": "x.py:1", "fact": "complexity=50"},
                {"finding_id": "RISK-P1-NEW", "category": "architecture", "title": "Hotspot", "location": "x.py:1", "fact": "complexity=50", "acceptance_criteria": ["Reduce complexity. [method: test]", "Reduce complexity. [method: rerun]"]},
            ],
            "stage_summaries": [
                {"stage_id": "decision_report_generation", "report_contract_status": "blocked", "report_contract_reason": "canonical_score_truth_mismatch"},
                {"stage_id": "evidence_reconciliation_and_scoring", "technical_score": 78, "evidence_adjusted_score": 78},
            ],
        },
    }


def test_reconciles_scanners_scores_findings_and_filename():
    result = reconcile_production_report_truth(_package())
    canonical = result["json"]
    assessment = canonical["assessment"]
    assert assessment["technical_score"] == 78
    assert assessment["evidence_adjusted_score"] == 78
    assert assessment["maturity_signal"]["presented_score"] == 78
    assert len(canonical["scanner_execution_records"]) == 3
    assert all(item["verified_complete"] for item in canonical["scanner_execution_records"])
    assert len(canonical["canonical_findings"]) == 1
    assert canonical["canonical_findings"][0]["finding_id"] == "RISK-P1-NEW"
    assert len(canonical["canonical_findings"][0]["acceptance_criteria"]) == 1
    decision_stage = next(item for item in canonical["stage_summaries"] if item["stage_id"] == "decision_report_generation")
    assert decision_stage["report_contract_status"] == "passed"
    assert result["pdf_filename"].endswith("-FINAL-PENDING-APPROVAL.pdf")
    assert result["pdf_filename"].count("FINAL-PENDING-APPROVAL") == 1


def test_bandit_command_uses_explicit_supported_exclusions_without_skips():
    install_scanner_command_repair()
    bandit = next(item for item in scanner_module.TOOL_SPECS if item.name == "bandit")
    assert bandit.command[:5] == ("bandit", "-r", ".", "-f", "json")
    assert "-x" in bandit.command
    assert "-s" not in bandit.command
