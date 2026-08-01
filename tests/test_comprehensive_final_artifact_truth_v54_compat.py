from __future__ import annotations

from nico.comprehensive_final_artifact_truth_v54 import weighted_score_diagnostics


def test_legacy_package_without_weight_rows_remains_compatible() -> None:
    canonical = {
        "assessment": {
            "technical_score": 85,
            "canonical_evidence_adjusted_score": 74,
            "maturity_signal": {
                "score": 85,
                "technical_score": 85,
                "canonical_evidence_adjusted_score": 74,
                "evidence_adjusted_score": 74,
            },
        }
    }

    diagnostics = weighted_score_diagnostics(canonical)

    assert diagnostics["matches"] is True
    assert diagnostics["reason"] == "legacy_package_without_weight_rows"


def test_new_truth_package_without_weight_rows_still_fails_closed() -> None:
    canonical = {
        "pre_render_truth_reconciliation": True,
        "assessment": {
            "technical_score": 85,
            "canonical_evidence_adjusted_score": 74,
            "maturity_signal": {"score": 85},
        },
    }

    diagnostics = weighted_score_diagnostics(canonical)

    assert diagnostics["matches"] is False
    assert diagnostics["reason"] == "included_scoring_rows_missing"
