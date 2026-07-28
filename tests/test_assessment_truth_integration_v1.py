import pytest

from nico.assessment_truth_integration_v1 import (
    calculate_score_ledger,
    enforce_finding_verification,
    freeze_assessment,
)
from nico.final_assessment_truth_v1 import TruthViolation


def test_missing_weight_is_not_redistributed_into_maturity():
    ledger = calculate_score_ledger(scored_contribution=70.4, scored_weight=0.85)
    assert round(ledger.observed_performance) == 83
    assert round(ledger.coverage_adjusted_maturity) == 70


def test_penalties_and_ceilings_are_auditable():
    ledger = calculate_score_ledger(
        scored_contribution=78,
        scored_weight=1,
        penalties=[{"reason": "missing exact SHA CI", "points": 8}],
        ceilings=[{"reason": "static analysis unavailable", "maximum": 69, "applies": True}],
    )
    assert ledger.coverage_adjusted_maturity == 69
    assert ledger.evidence_adjusted_readiness == 69
    assert ledger.as_dict()["formula_version"]


def test_unverified_p0_is_downgraded():
    [finding] = enforce_finding_verification([
        {"title": "Possible unsafe parser", "severity": "P0", "verification_status": "candidate"}
    ])
    assert finding["severity"] == "P1"
    assert "requires verified" in finding["severity_adjustment_reason"]


def test_unresolved_placeholder_is_blocked():
    with pytest.raises(TruthViolation):
        enforce_finding_verification([{"title": "XXE $FLAVOR", "severity": "P1"}])


def test_frozen_truth_contains_three_score_views():
    ledger = calculate_score_ledger(scored_contribution=70.4, scored_weight=0.85)
    truth = freeze_assessment(
        {
            "assessment_identity": {"repository": "ARA", "immutable_revision": "abc"},
            "canonical_findings": [],
            "limitations": [],
            "approval_state": "blocked",
        },
        ledger,
    ).as_dict()
    assert round(truth["observed_performance"]) == 83
    assert round(truth["technical_score"]) == 70
    assert truth["evidence_adjusted_score"] <= truth["technical_score"]
