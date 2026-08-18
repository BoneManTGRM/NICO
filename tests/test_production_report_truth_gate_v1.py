from __future__ import annotations

import nico.scanner_tool_runners as scanner_module
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from nico.production_report_truth_gate_v1 import reconcile_production_report_truth
from nico.scanner_command_repair_v1 import install_scanner_command_repair


def _scanner(tool: str, category: str, marker: str, **extra: object) -> dict:
    return {
        "tool": tool,
        "status": "completed",
        "current_run": True,
        "execution_observed_for_this_report": True,
        "exact_commit_match": True,
        "verified_for_this_report": True,
        "output_capture_complete": True,
        "raw_artifact_capture_complete": True,
        "returncode_valid": True,
        "timed_out": False,
        "output_truncated": False,
        "artifact_hash": marker * 64,
        "raw_artifact_retention_complete": True,
        "category": category,
        "findings": [],
        **extra,
    }


def _package() -> dict:
    return {
        "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
        "human_review_required": True,
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
                _scanner("bandit", "static", "b"),
                _scanner("eslint", "static", "e"),
                _scanner(
                    "gitleaks",
                    "secret",
                    "g",
                    scans_git_history=True,
                    full_history_verified=True,
                ),
            ],
            "canonical_findings": [
                {
                    "finding_id": "RISK-OLD",
                    "category": "architecture",
                    "title": "Hotspot",
                    "location": "x.py:1",
                    "fact": "complexity=50",
                },
                {
                    "finding_id": "RISK-P1-NEW",
                    "category": "architecture",
                    "title": "Hotspot",
                    "location": "x.py:1",
                    "fact": "complexity=50",
                    "acceptance_criteria": [
                        "Reduce complexity. [method: test]; Reduce complexity. [method: rerun]; "
                        "Preserve behavior. [method: automated_test; target commit: abc]"
                    ],
                },
            ],
            "roadmap": [
                {
                    "window": "0-30 days",
                    "work_packages": [
                        {
                            "work_package_id": "WP-001",
                            "related_risks": ["RISK-OLD", "RISK-P1-NEW", "RISK-OLD"],
                        }
                    ],
                }
            ],
            "stage_summaries": [
                {
                    "stage_id": "decision_report_generation",
                    "report_contract_status": "blocked",
                    "report_contract_reason": "canonical_score_truth_mismatch",
                },
                {
                    "stage_id": "evidence_reconciliation_and_scoring",
                    "technical_score": 78,
                    "evidence_adjusted_score": 78,
                },
            ],
        },
    }


def test_reconciles_scanners_scores_findings_roadmap_and_filename():
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
    assert canonical["canonical_findings"][0]["acceptance_criteria"] == [
        "Reduce complexity. [method: test]",
        "Preserve behavior. [method: automated_test; target commit: abc]",
    ]
    assert canonical["roadmap"][0]["work_packages"][0]["related_risks"] == [
        "RISK-P1-NEW"
    ]

    decision_stage = next(
        item
        for item in canonical["stage_summaries"]
        if item["stage_id"] == "decision_report_generation"
    )
    assert decision_stage["report_contract_status"] == "passed"
    assert result["pdf_filename"].endswith("-FINAL-PENDING-APPROVAL.pdf")
    assert result["pdf_filename"].count("FINAL-PENDING-APPROVAL") == 1

    readiness = canonical["client_readiness_contract"]
    assert readiness["automated_report_truth_ready"] is True
    assert readiness["single_score_truth"] is True
    assert readiness["single_scanner_record_per_tool"] is True
    assert readiness["all_observed_scanners_verified"] is True
    assert readiness["internal_human_approval_required"] is True
    assert readiness["client_delivery_allowed"] is False


def test_completed_scanner_without_current_report_verification_stays_incomplete():
    package = _package()
    package["json"]["scanner_execution_records"][0]["verified_for_this_report"] = False

    result = reconcile_production_report_truth(package)
    bandit = next(
        item for item in result["json"]["scanner_execution_records"] if item["tool"] == "bandit"
    )

    assert bandit["verified_complete"] is False
    assert "scanner_verification_not_proven" in bandit["verification_deficits"]
    assert result["json"]["client_readiness_contract"]["all_observed_scanners_verified"] is False


def test_compact_scanner_proof_passes_public_gate_and_missing_current_run_fails_closed():
    raw_records = [
        _scanner("bandit", "static", "b"),
        _scanner("eslint", "static", "e"),
        _scanner(
            "gitleaks",
            "secret",
            "g",
            scans_git_history=True,
            full_history_verified=True,
        ),
    ]
    records = compact_scanner_records(
        {"scan_id": "scan", "scanner_results": raw_records},
        commit_sha="a" * 40,
    )
    package = _package()
    package["json"]["scanner_execution_records"] = records

    result = reconcile_production_report_truth(package)
    assert all(
        record["verified_complete"]
        for record in result["json"]["scanner_execution_records"]
    )

    records[0]["current_run"] = False
    package = _package()
    package["json"]["scanner_execution_records"] = records
    result = reconcile_production_report_truth(package)
    bandit = next(
        record
        for record in result["json"]["scanner_execution_records"]
        if record["tool"] == "bandit"
    )
    assert bandit["verified_complete"] is False
    assert "current_run_not_proven" in bandit["verification_deficits"]


def test_unrelated_report_contract_block_is_preserved_fail_closed():
    package = _package()
    decision_stage = package["json"]["stage_summaries"][0]
    decision_stage["report_contract_reason"] = "missing_approval_identity"

    result = reconcile_production_report_truth(package)
    repaired = next(
        item
        for item in result["json"]["stage_summaries"]
        if item["stage_id"] == "decision_report_generation"
    )

    assert repaired["report_contract_status"] == "blocked"
    assert repaired["report_contract_reason"] == "missing_approval_identity"
    assert result["json"]["client_readiness_contract"]["automated_report_truth_ready"] is False
    assert result["json"]["client_readiness_contract"]["report_contract_status"] == "blocked"


def test_bandit_command_uses_explicit_supported_exclusions_without_skips():
    install_scanner_command_repair()
    bandit = next(item for item in scanner_module.TOOL_SPECS if item.name == "bandit")
    assert bandit.command[:5] == ("bandit", "-r", ".", "-f", "json")
    assert "-x" in bandit.command
    assert "-s" not in bandit.command
