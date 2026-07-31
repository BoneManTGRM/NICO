from __future__ import annotations

from copy import deepcopy

from nico import comprehensive_assessment_hardening_v1 as hardening
from nico import comprehensive_native_providers_v4 as scoring
from nico.comprehensive_score_truth_scope_v4 import install_score_truth_scope


def _assessment(technical: int = 91) -> dict:
    return {
        "technical_score": technical,
        "canonical_evidence_adjusted_score": 90,
        "evidence_adjusted_score": 90,
        "maturity_signal": {
            "score": 90,
            "source_score": 90,
            "presented_score": 90,
            "technical_score": 90,
            "evidence_adjusted_score": 89,
        },
        "score_contract": {
            "technical_score": 90,
            "evidence_adjusted_score": 89,
        },
        "sections": [
            {"id": "one", "presented_score": 90},
            {"id": "two", "presented_score": 92},
        ],
    }


def _package(technical: int = 91) -> dict:
    assessment = _assessment(technical)
    return {
        "status": "complete",
        "assessment": assessment,
        "stage_summaries": [
            {
                "stage_id": "decision_report_generation",
                "report_contract_status": "blocked",
                "report_contract_reason": "canonical_score_truth_mismatch",
                "technical_score": 90,
                "evidence_adjusted_score": 89,
            }
        ],
        "report_package": {
            "json": {
                "assessment": deepcopy(assessment),
                "technical_score": 90,
                "evidence_adjusted_score": 89,
                "report_contract_status": "blocked",
                "report_contract_reason": "canonical_evidence_adjusted_score_mismatch",
            }
        },
    }


def test_consistent_score_alias_mismatch_is_repaired_before_publication_gate() -> None:
    install_score_truth_scope()
    payload = _package()

    scoring.repair_score_truth(payload)
    gated = hardening.enforce_report_contract_gate(payload)

    assert gated["report_quality_contract"]["report_contracts_clear"] is True
    assert gated["report_quality_contract"]["report_contract_blocked_count"] == 0
    assert gated["report_package"]["report_contract_status"] == "clear"
    assert gated["assessment"]["technical_score"] == 91
    assert gated["assessment"]["canonical_evidence_adjusted_score"] == 90


def test_real_section_score_disagreement_stays_blocked_at_publication_gate() -> None:
    install_score_truth_scope()
    payload = _package(technical=90)

    scoring.repair_score_truth(payload)
    gated = hardening.enforce_report_contract_gate(payload)

    assert gated["status"] == "blocked"
    assert gated["report_quality_contract"]["report_contracts_clear"] is False
    assert gated["report_quality_contract"]["report_contract_blocked_count"] >= 1
    assert gated["report_package"]["publication_allowed"] is False
