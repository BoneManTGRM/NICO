from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_report_scanner_scoring_v51 import _normalize_assessment


def test_final_normalization_overwrites_stale_maturity_canonical_adjusted_alias() -> None:
    assessment = {
        "technical_score": 91,
        "evidence_adjusted_score": 74,
        "canonical_evidence_adjusted_score": 74,
        "maturity_signal": {
            "score": 91,
            "source_score": 91,
            "presented_score": 91,
            "technical_score": 91,
            "evidence_adjusted_score": 74,
            "canonical_evidence_adjusted_score": 61,
        },
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 80,
                "source_score": 80,
                "presented_score": 80,
                "score_value": 80,
                "evidence": ["Exact immutable repository snapshot analyzed."],
                "findings": [],
                "unavailable": [],
            }
        ],
    }
    original = deepcopy(assessment)

    normalized = _normalize_assessment(assessment, {})

    maturity = normalized["maturity_signal"]
    adjusted_aliases = {
        normalized["evidence_adjusted_score"],
        normalized["canonical_evidence_adjusted_score"],
        maturity["evidence_adjusted_score"],
        maturity["canonical_evidence_adjusted_score"],
    }
    assert adjusted_aliases == {80}
    assert normalized["technical_score"] == 80
    assert maturity["technical_score"] == 80
    assert maturity["presented_score"] == 80
    assert assessment == original
    assert original["maturity_signal"]["canonical_evidence_adjusted_score"] == 61
