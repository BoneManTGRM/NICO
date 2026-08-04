from __future__ import annotations

import base64

from nico.comprehensive_client_ready_projection_v1 import APPROVAL_SUFFIX
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package


GENERATED_AT = "2026-08-04T16:15:00Z"


def _finding(finding_id: str, *, enriched: bool) -> dict:
    result = {
        "finding_id": finding_id,
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "decision_title": "High-complexity code hotspot",
        "interpretation": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "priority": "P1",
        "status": "open",
        "fact": "cyclomatic_complexity=52; method=typescript_compiler_ast",
        "recommendation": "Decompose the hotspot into bounded modules.",
        "acceptance_criteria": ["Target complexity is at most 30."],
    }
    if enriched:
        result.update(
            {
                "business_impact": "Concentrated branch logic increases regression risk.",
                "owner_role": "Product Engineering Architect",
                "effort": "M-L",
                "cost_of_inaction": "Material exposure over 90 days.",
                "residual_risk": "Moderate residual likelihood.",
                "acceptance_criteria": [
                    "Target complexity is at most 30. [method: metric_comparison; target commit: " + "a" * 40 + "]",
                    "Target complexity is at most 30. [method: metric_comparison; target commit: " + "a" * 40 + "]",
                ],
            }
        )
    return result


def _result() -> dict:
    legacy = _finding("RISK-LEGACY", enriched=False)
    prioritized = _finding("RISK-P1-CANONICAL", enriched=True)
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_phase17",
            "generated_at": GENERATED_AT,
        },
        "generated_at": GENERATED_AT,
        "assessment": {
            "technical_score": 83,
            "canonical_evidence_adjusted_score": 81,
            "executive_summary": "Assessment complete.",
            "sections": [
                {
                    "id": "static_analysis",
                    "label": "Static Analysis",
                    "score": 83,
                    "presented_score": 83,
                    "status": "review_limited_not_scored",
                    "presented_status": "REVIEW_LIMITED_NOT_SCORED",
                    "unavailable": ["One supplemental analyzer was review-limited."],
                    "summary": "Completed analyzer evidence is scored separately from assurance limits.",
                }
            ],
        },
        "canonical_findings": [legacy, prioritized],
        "findings_register": [legacy, prioritized],
        "findings": [legacy, prioritized],
        "decision_grade_findings_register": [legacy, prioritized],
    }
    return {
        "status": "failed",
        "record": {"status": "failed"},
        "report_package": {
            "json": canonical,
            "generated_at": GENERATED_AT,
            "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "pdf_base64": base64.b64encode(b"%PDF-1.4 stale duplicate artifact").decode("ascii"),
            "markdown": "stale duplicate artifact",
        },
    }


def test_phase17_renders_repaired_canonical_truth_not_stale_artifacts() -> None:
    output = finalize_report_package(_result())
    package = output["report_package"]
    canonical = package["json"]

    assert len(canonical["canonical_findings"]) == 1
    assert len(canonical["canonical_findings"][0]["acceptance_criteria"]) == 1
    assert package["markdown"].count("## Compact Finding and Remediation Register") == 1
    assert package["markdown"].count("apps/web/app/operations/page.tsx:177") >= 1
    assert package["markdown"].count("Target complexity is at most 30") == 1
    register = canonical["client_finding_remediation_register"]
    assert register["summary"]["semantic_duplicate_code_anchors_absent"] is True
    assert register["summary"]["verification_and_exit_criteria_distinct"] is True
    assert "RISK-LEGACY" not in package["markdown"] or "RISK-P1-CANONICAL" not in package["markdown"]
    assert base64.b64decode(package["pdf_base64"]).startswith(b"%PDF")
    assert package["phase17_artifact_rebuild"]["rebuilt_from_repaired_canonical_truth"] is True
    assert package["phase9_release_gate"]["artifacts_rebuilt_after_canonical_repair"] is True
    assert package["pdf_filename"] == f"nico-report-{APPROVAL_SUFFIX}.pdf"
    assert package["json"]["identity"]["generated_at"] == GENERATED_AT
    assert package["report_finality"] == "automated_draft"
    assert package["approval_status"] == "pending_human_approval"
    assert package["client_delivery_allowed"] is False

    section = canonical["assessment"]["sections"][0]
    assert section["presented_score"] == 83
    assert section["presented_status"] == "MODERATE"
    assert section["status"] == "moderate"
    assert section["assurance_status"] == "review_limited"
    assert canonical["v2_pipeline_contract"]["scored_sections_never_labeled_not_scored"] is True


def test_phase17_returns_completed_package_as_internal_review_required() -> None:
    output = finalize_report_package(_result())

    assert output["status"] == "review_required"
    assert output["record"]["status"] == "review_required"
    assert output["record"]["assessment_package_complete"] is True
    assert output["human_review_required"] is True
    assert output["human_review_completed"] is False
    assert output["client_delivery_allowed"] is False
