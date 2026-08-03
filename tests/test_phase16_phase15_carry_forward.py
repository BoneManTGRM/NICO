from __future__ import annotations

from nico.phase15_finding_quality_v1 import prioritize_findings, quality_finding
from nico.phase15_production_integration_v1 import normalize_production_scanner_records
from nico.phase16_client_delivery_verification_v1 import (
    repair_client_delivery_package,
    verify_client_delivery_package,
)


def _finding(index: int, *, severity: str = "high", release_blocking: bool = False):
    return {
        "finding_id": f"RISK-{index}",
        "title": f"Repair verified issue {index}",
        "decision_title": f"Repair verified issue {index}",
        "location": f"src/module_{index}.py:{index}",
        "category": "security",
        "severity": severity,
        "likelihood": "likely",
        "confidence": "high",
        "business_impact": "Could delay release or expose production risk.",
        "release_blocking": release_blocking,
        "fact": f"Exact-SHA evidence for issue {index}.",
        "interpretation": f"Issue {index} is material.",
        "inference": "Risk remains until the verified repair is accepted.",
        "recommendation": f"Repair issue {index} and rerun the same checks.",
        "owner_role": "Engineering owner",
        "effort": "1-2 days",
        "residual_risk": "Low after verification.",
        "acceptance_criteria": [
            f"The exact-SHA regression test for issue {index} passes.",
            f"The exact-SHA regression test for issue {index} passes. [method: pytest]",
        ],
    }


def test_phase15_quality_fields_and_strict_p1_survive_phase16() -> None:
    release_blocker = quality_finding(_finding(1, release_blocking=True))
    incomplete = quality_finding({"finding_id": "INCOMPLETE", "title": "Unproven issue"})

    assert release_blocker["priority"] == "P1"
    assert release_blocker["ranking_score"] > 0
    assert release_blocker["ranking_reason"].startswith("P1 because")
    assert release_blocker["quality_complete"] is True
    for field in (
        "fact",
        "interpretation",
        "inference",
        "recommendation",
        "owner_role",
        "effort",
        "residual_risk",
        "acceptance_criteria",
    ):
        assert release_blocker[field]

    assert incomplete["priority"] == "P3"
    assert incomplete["quality_complete"] is False
    assert incomplete["quality_gaps"]


def test_phase15_top5_next10_and_backlog_survive_phase16() -> None:
    result = prioritize_findings([_finding(index) for index in range(1, 19)])

    assert len(result["top_5"]) == 5
    assert len(result["next_10"]) == 10
    assert len(result["backlog"]) == 3
    assert len(result["all_findings"]) == 18
    scores = [item["ranking_score"] for item in result["all_findings"]]
    assert scores == sorted(scores, reverse=True)


def test_phase15_bandit_exit_one_is_completed_only_with_proof() -> None:
    sha = "a" * 40
    proven, failed = normalize_production_scanner_records(
        [
            {
                "scanner": "bandit",
                "raw_exit_code": 1,
                "artifact_sha256": "b" * 64,
                "json_parseable": True,
                "exact_commit_match": True,
                "commit_sha": sha,
                "status": "failed",
            },
            {
                "scanner": "bandit-unproven",
                "raw_exit_code": 1,
                "commit_sha": sha,
                "status": "failed",
            },
        ],
        expected_sha=sha,
    )

    assert proven["status"] == "completed"
    assert proven["exit_code"] == 1
    assert proven["artifact_sha256"] == "b" * 64
    assert failed["status"] == "failed"


def test_phase16_repairs_phase15_visible_report_failures_and_reverifies() -> None:
    first = _finding(1)
    duplicate = {
        **first,
        "finding_id": "RISK-P1-1",
        "title": "Complexity hotspot requires remediation",
        "decision_title": "Complexity hotspot requires remediation",
        "finding_aliases": ["RISK-1"],
    }
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
    assert "FINAL-PENDING-APPROVAL" not in repaired["pdf_filename"]
    assert repaired["report_finality"] == "automated_draft"
    assert repaired["approval_status"] == "pending_human_approval"
    assert repaired["client_delivery_allowed"] is False
    assert repaired["canonical_truth_sha256"] != "0" * 64

    verification = verify_client_delivery_package(repaired)
    assert verification["valid"] is True, verification["errors"]
