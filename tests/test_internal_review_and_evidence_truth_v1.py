from __future__ import annotations

from pathlib import Path

from nico.comprehensive_canonical_report_truth_v1 import apply_canonical_score_truth

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps/web/app/assessment"


def _assessment(*, missing_control: bool = False) -> dict:
    scores = [
        ("code_audit", 0.20, 92, "VERIFIED"),
        ("dependency_health", 0.15, 92, "LIMITED · CANDIDATE DISPOSITION"),
        ("secrets_review", 0.15, 93, "LIMITED · CANDIDATE DISPOSITION"),
        ("static_analysis", 0.15, None if missing_control else 79, "" if missing_control else "LIMITED · ANALYZER COVERAGE"),
        ("ci_cd", 0.15, 86, "VERIFIED"),
        ("architecture_debt", 0.15, 78, "VERIFIED"),
        ("velocity_complexity", 0.05, 84, "VERIFIED"),
    ]
    return {
        "repository": "BoneManTGRM/NICO",
        "evidence_coverage": {"calculated": True, "percent": 81, "label": "Automated evidence coverage"},
        "evidence_health_summary": {
            "completed_scanners": ["scanner-a", "scanner-b", "scanner-c", "scanner-d"],
            "incomplete_scanners": [{"scanner": "bandit", "status": "failed"}, {"scanner": "eslint", "status": "failed"}],
        },
        "sections": [
            {
                "id": section_id,
                "score_value": score,
                "assurance_label": assurance,
                "unavailable": ["Required analyzer unavailable"] if missing_control and section_id == "static_analysis" else [],
            }
            for section_id, _weight, score, assurance in scores
        ],
        "scoring_weights": [
            {
                "section_id": section_id,
                "control": section_id,
                "weight": weight,
                "technical_score": score,
                "assurance": assurance,
                "included": score is not None,
            }
            for section_id, weight, score, assurance in scores
        ],
    }


def test_evidence_metrics_distinguish_processing_disposition_analyzers_and_overall() -> None:
    result = apply_canonical_score_truth(_assessment())
    contract = result["evidence_completion_contract"]

    assert contract["automatable_repository_evidence"]["percent"] == 100
    assert contract["automatable_repository_evidence"]["completed"] == 7
    assert contract["required_evidence_disposition"]["percent"] == 100
    assert contract["analyzer_completion"]["percent"] == 67
    assert contract["overall_engagement_evidence"]["percent"] == 81
    assert contract["overall_engagement_evidence"]["gap_percent"] == 19
    assert contract["full_automation_claim_allowed"] is True
    assert contract["full_engagement_coverage_claim_allowed"] is False
    assert result["evidence_coverage"]["automatable_percent"] == 100
    assert result["evidence_coverage"]["percent"] == 81


def test_missing_automatable_result_cannot_be_reported_as_100_percent() -> None:
    result = apply_canonical_score_truth(_assessment(missing_control=True))
    contract = result["evidence_completion_contract"]

    assert contract["automatable_repository_evidence"]["percent"] < 100
    assert contract["full_automation_claim_allowed"] is False
    assert contract["required_evidence_disposition"]["percent"] == 100


def test_completed_assessment_links_to_protected_internal_review() -> None:
    workspace = (ASSESSMENT / "AssessmentWorkspace.tsx").read_text(encoding="utf-8")
    evidence = (ASSESSMENT / "assessmentEvidence.ts").read_text(encoding="utf-8")

    assert 'data-assessment-internal-review="true"' in workspace
    assert "internalReviewHrefFor(result, locale)" in workspace
    assert "/operations/final-review?" in evidence
    assert 'service: "comprehensive"' in evidence
    assert 'run_id: String(result?.run_id' in evidence
    assert "X-NICO-Admin-Token" not in evidence


def test_approved_run_is_complete_and_client_ready_in_the_frontend_contract() -> None:
    evidence = (ASSESSMENT / "assessmentEvidence.ts").read_text(encoding="utf-8")
    workspace = (ASSESSMENT / "AssessmentWorkspace.tsx").read_text(encoding="utf-8")

    assert 'value === "approved" && deliveryAllowed' in evidence
    assert 'return "complete"' in evidence
    assert "clientReadyStatus" in workspace
    assert "internalReview.approved ? copy.downloadApprovedPdf : copy.downloadReviewPdf" in workspace


def test_visible_product_language_is_internal_review_not_client_acceptance() -> None:
    copy = (ASSESSMENT / "assessmentCopy.ts").read_text(encoding="utf-8")
    review = (ROOT / "apps/web/app/operations/final-review/FinalReviewWorkspace.tsx").read_text(encoding="utf-8")
    pdf = (ROOT / "nico/comprehensive_express_quality_v7.py").read_text(encoding="utf-8")

    assert "Open internal review" in copy
    assert "Internal review approved" in copy
    assert "Internal final review and client-ready authorization" in review
    assert '"INTERNAL REVIEW"' in pdf
    assert '"CLIENT-READY"' in pdf
    assert '"Draft only"' not in pdf
