from __future__ import annotations

from copy import deepcopy

from nico import comprehensive_native_providers_v4 as scoring
from nico.comprehensive_score_truth_scope_v4 import install_score_truth_scope


def test_section_score_contract_is_not_overwritten_by_overall_alias_repair() -> None:
    install_score_truth_scope()
    section = {
        "id": "ci_cd",
        "score": 100,
        "presented_score": 100,
        "score_contract": {
            "version": "nico.immutable-ci-score.v1",
            "immutable_control_count": 11,
            "score_inputs": {"exact_configuration_match": True},
        },
    }
    original = deepcopy(section)

    touched = scoring._sync_score_container(section, 93, 91)

    assert touched == 0
    assert section == original


def test_assessment_and_report_aliases_are_synchronized() -> None:
    install_score_truth_scope()
    assessment = {
        "technical_score": 71,
        "canonical_evidence_adjusted_score": 61,
        "maturity_signal": {
            "score": 71,
            "presented_score": 71,
            "evidence_adjusted_score": 61,
        },
        "score_contract": {
            "technical_score": 71,
            "evidence_adjusted_score": 61,
        },
    }

    touched = scoring._sync_score_container(assessment, 93, 91)

    assert touched > 0
    assert assessment["technical_score"] == 93
    assert assessment["canonical_evidence_adjusted_score"] == 91
    assert assessment["maturity_signal"]["score"] == 93
    assert assessment["maturity_signal"]["evidence_adjusted_score"] == 91
    assert assessment["score_contract"]["technical_score"] == 93
    assert assessment["score_contract"]["evidence_adjusted_score"] == 91
