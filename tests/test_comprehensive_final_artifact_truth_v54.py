from __future__ import annotations

from nico.comprehensive_final_artifact_truth_v54 import weighted_score_diagnostics


def _canonical(*, adjusted: int = 90) -> dict:
    rows = [
        {
            "section_id": "code_audit",
            "technical_score": 100,
            "weight": 0.5,
            "assurance": "VERIFIED",
            "included": True,
        },
        {
            "section_id": "static_analysis",
            "technical_score": 84,
            "weight": 0.5,
            "assurance": "REVIEW LIMITED",
            "included": True,
        },
    ]
    return {
        "assessment": {
            "technical_score": 92,
            "canonical_evidence_adjusted_score": adjusted,
            "evidence_adjusted_score": adjusted,
            "maturity_signal": {
                "score": 92,
                "technical_score": 92,
                "canonical_evidence_adjusted_score": adjusted,
                "evidence_adjusted_score": adjusted,
            },
            "scoring_weights": rows,
            "score_reconciliation": {"rows": rows},
        }
    }


def test_missing_numeric_factor_is_derived_from_retained_assurance_status() -> None:
    diagnostics = weighted_score_diagnostics(_canonical())

    assert diagnostics["matches"] is True
    assert diagnostics["recalculated_technical_score"] == 92
    assert diagnostics["recalculated_evidence_adjusted_score"] == 90
    assert diagnostics["rows"][1]["assurance_factor"] == 0.95
    assert (
        diagnostics["rows"][1]["assurance_factor_source"]
        == "derived_from_retained_assurance_status"
    )


def test_real_score_mismatch_still_fails_closed() -> None:
    diagnostics = weighted_score_diagnostics(_canonical(adjusted=86))

    assert diagnostics["matches"] is False
    assert diagnostics["reason"] == "weighted_score_mismatch"
    assert diagnostics["recalculated_evidence_adjusted_score"] == 90
    assert diagnostics["canonical_evidence_adjusted_score"] == 86
