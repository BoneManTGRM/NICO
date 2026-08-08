from __future__ import annotations

from pathlib import Path

from nico.phase1_completion_truth_v1 import (
    SCORING_MODEL_VERSION,
    normalize_phase1_scoring_result,
)


def _payload(*, candidate_penalty: int, raw_penalty: int = 0, execution_penalty: int = 0) -> dict:
    return {
        "status": "complete",
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 93 - candidate_penalty - raw_penalty - execution_penalty,
            "canonical_evidence_adjusted_score": 93 - candidate_penalty - raw_penalty - execution_penalty,
            "maturity_signal": {
                "score": 93,
                "technical_score": 93,
                "evidence_adjusted_score": 93 - candidate_penalty - raw_penalty - execution_penalty,
            },
            "evidence_coverage": {
                "candidate_volume_penalty": candidate_penalty,
                "candidate_volume_penalty_by_category": {
                    "dependency": 1,
                    "secret": 1,
                    "static": max(0, candidate_penalty - 2),
                },
                "missing_raw_payload_penalty": raw_penalty,
                "incomplete_analyzer_penalty": execution_penalty,
                "candidate_volume_affects_evidence_adjusted_score": True,
            },
            "score_contract": {
                "candidate_volume_penalty": candidate_penalty,
                "missing_raw_payload_penalty": raw_penalty,
                "incomplete_analyzer_penalty": execution_penalty,
                "assurance_penalty": candidate_penalty + raw_penalty + execution_penalty,
                "candidate_volume_affects_evidence_adjusted_score": True,
            },
            "sections": [
                {
                    "id": "dependencies",
                    "evidence": ["Score effect: assurance-only until triaged."],
                },
                {
                    "id": "secrets",
                    "evidence": ["Assurance-only until triaged."],
                },
            ],
        },
        "evidence": {
            "candidate_volume_penalty": candidate_penalty,
            "missing_raw_payload_penalty": raw_penalty,
            "incomplete_analyzer_penalty": execution_penalty,
        },
        "summary": "legacy",
    }


def test_candidate_volume_and_review_workload_do_not_change_numeric_score() -> None:
    small = normalize_phase1_scoring_result(_payload(candidate_penalty=4))
    large = normalize_phase1_scoring_result(_payload(candidate_penalty=18))

    for result in (small, large):
        assessment = result["assessment"]
        coverage = assessment["evidence_coverage"]
        contract = assessment["score_contract"]
        assert assessment["technical_score"] == 93
        assert assessment["evidence_adjusted_score"] == 93
        assert assessment["canonical_evidence_adjusted_score"] == 93
        assert coverage["candidate_volume_penalty"] == 0
        assert coverage["candidate_volume_affects_numeric_score"] is False
        assert coverage["review_workload_affects_numeric_score"] is False
        assert coverage["candidate_volume_affects_assurance_state"] is True
        assert contract["candidate_volume_penalty"] == 0
        assert contract["assurance_penalty"] == 0
        assert contract["scoring_model_version"] == SCORING_MODEL_VERSION

    assert small["assessment"]["evidence_adjusted_score"] == large["assessment"]["evidence_adjusted_score"]


def test_real_evidence_completeness_failures_can_still_reduce_evidence_adjusted() -> None:
    result = normalize_phase1_scoring_result(
        _payload(candidate_penalty=18, raw_penalty=2, execution_penalty=4)
    )

    assessment = result["assessment"]
    assert assessment["technical_score"] == 93
    assert assessment["evidence_adjusted_score"] == 87
    assert assessment["score_contract"]["evidence_completeness_penalty"] == 6
    assert assessment["score_contract"]["assurance_penalty"] == 6
    assert assessment["evidence_coverage"]["candidate_volume_penalty"] == 0


def test_score_sections_state_completed_technical_triage_truth() -> None:
    result = normalize_phase1_scoring_result(_payload(candidate_penalty=4))
    rendered = repr(result["assessment"]["sections"]).casefold()

    assert "assurance-only until triaged" not in rendered
    assert "nico automated technical triage is complete" in rendered
    assert "authorized human disposition remains pending" in rendered


def test_completion_truth_does_not_create_human_authority() -> None:
    result = normalize_phase1_scoring_result(_payload(candidate_penalty=4))
    truth = result["phase1_scoring_truth"]

    assert truth["technical_triage_distinct_from_human_disposition"] is True
    assert truth["human_approval_created"] is False
    assert truth["client_delivery_allowed"] is False


def test_public_home_has_one_comprehensive_product_route() -> None:
    source = Path("apps/web/app/AssessmentHomeRedirect.tsx").read_text(encoding="utf-8")

    assert "/assessment?tier=comprehensive#assessment" in source
    assert "tier=express" not in source
    assert 'params.get("legacy")' not in source
    assert "Opening NICO Comprehensive" in source
