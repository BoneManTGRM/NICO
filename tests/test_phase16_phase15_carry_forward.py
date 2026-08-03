from __future__ import annotations

import base64
from copy import deepcopy

from nico.phase15_client_report_quality_v3 import upgrade_phase15_report
from nico.phase16_client_delivery_verification_v1 import (
    repair_client_delivery_package,
    verify_client_delivery_package,
)


def _base_finding() -> dict:
    return {
        "finding_id": "RISK-P1-1",
        "finding_aliases": ["RISK-1"],
        "priority": "P1",
        "category": "architecture",
        "title": "Complexity hotspot requires remediation",
        "decision_title": "Complexity hotspot requires remediation",
        "interpretation": "Complexity hotspot requires remediation",
        "location": "nico/example.py:10",
        "symbol": "example",
        "status": "open",
        "evidence": "cyclomatic_complexity=45",
        "fact": "cyclomatic_complexity=45",
        "recommendation": "Extract bounded helpers.",
        "business_impact": "Change risk is elevated.",
        "owner_role": "Product Engineering Architect",
        "effort": "M",
        "acceptance_criteria": [
            "Complexity is at or below 30 [method: static analysis]",
            "Complexity is at or below 30 [target commit: abc123]",
        ],
        "roadmap_ids": ["WP-001"],
        "backlog_id": "BL-001",
    }


def _phase15_package() -> dict:
    finding = _base_finding()
    return {
        "json": {
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "abc123",
                "run_id": "run-phase16-carry-forward",
            },
            "canonical_findings": [finding],
            "findings_register": [deepcopy(finding)],
            "findings": [deepcopy(finding)],
            "decision_grade_findings_register": [deepcopy(finding)],
            "executive_risk_register": [deepcopy(finding)],
            "priority_findings": [deepcopy(finding)],
            "assessment": {
                "technical_score": 80,
                "evidence_adjusted_score": 75,
            },
        },
        "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL.pdf",
        "pdf_base64": base64.b64encode(b"%PDF-1.4\nphase16 proof\n%%EOF").decode("ascii"),
        "canonical_truth_sha256": "0" * 64,
        "phase9_release_gate": {"valid": True},
        "analyzer_evidence_report": {"analyzers": []},
    }


def test_phase15_quality_fields_and_strict_p1_survive_phase16() -> None:
    upgraded = upgrade_phase15_report(_phase15_package())
    repaired = repair_client_delivery_package(upgraded)
    finding = repaired["json"]["canonical_findings"][0]

    assert finding["priority"] == "P1"
    assert finding["business_impact"] == "Change risk is elevated."
    assert finding["owner_role"] == "Product Engineering Architect"
    assert finding["recommendation"] == "Extract bounded helpers."


def test_phase15_top5_next10_and_backlog_survive_phase16() -> None:
    upgraded = upgrade_phase15_report(_phase15_package())
    repaired = repair_client_delivery_package(upgraded)
    report = repaired["json"]

    assert report["executive_risk_register"]
    assert report["priority_findings"]
    finding = report["canonical_findings"][0]
    assert finding["roadmap_ids"] == ["WP-001"]
    assert finding["backlog_id"] == "BL-001"


def test_phase15_bandit_exit_one_is_completed_only_with_proof() -> None:
    package = _phase15_package()
    package["json"]["scanner_execution_records"] = [
        {
            "scanner_name": "bandit",
            "state": "completed",
            "completed": True,
            "verified": True,
            "exit_code": 1,
            "artifact_hash": "a" * 64,
        }
    ]
    upgraded = upgrade_phase15_report(package)
    record = upgraded["json"]["scanner_execution_records"][0]

    assert record["completed"] is True
    assert record["verified"] is True
    assert record["artifact_hash"] == "a" * 64


def test_phase16_repairs_phase15_visible_report_failures_and_reverifies() -> None:
    first = _base_finding()
    duplicate = deepcopy(first)
    duplicate["finding_id"] = "RISK-P1-1"
    duplicate["title"] = "Complexity hotspot requires remediation"
    duplicate["decision_title"] = "Complexity hotspot requires remediation"
    duplicate["finding_aliases"] = ["RISK-1"]
    package = {
        "json": {
            "canonical_findings": [first, duplicate],
            "findings_register": [first, duplicate],
            "findings": [first, duplicate],
            "decision_grade_findings_register": [first, duplicate],
            "executive_risk_register": [first, duplicate],
            "priority_findings": [first, duplicate],
        },
        "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
        "canonical_truth_sha256": "0" * 64,
        "phase9_release_gate": {"valid": True},
        "analyzer_evidence_report": {"analyzers": []},
    }

    repaired = repair_client_delivery_package(package)
    findings = repaired["json"]["canonical_findings"]

    assert len(findings) == 1
    assert {"RISK-1", "RISK-P1-1"}.issubset(set(findings[0]["finding_aliases"]))
    assert len(findings[0]["acceptance_criteria"]) == 1
    assert repaired["pdf_filename"].count("AUTOMATED-DRAFT-PENDING-APPROVAL") == 1
    assert repaired["report_finality"] == "automated_draft"
    assert repaired["approval_status"] == "pending_human_approval"
    assert repaired["client_delivery_allowed"] is False
    assert repaired["canonical_truth_sha256"] != "0" * 64

    verification = verify_client_delivery_package(repaired)
    assert verification["valid"] is True, verification["errors"]
