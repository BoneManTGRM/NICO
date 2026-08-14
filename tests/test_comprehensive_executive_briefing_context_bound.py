from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_run_service import (
    _EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS,
    _EXECUTIVE_BRIEFING_STAGE_ID,
    _prior_stage_results_for_stage,
)


class _DeepcopyBomb:
    def __deepcopy__(self, memo: dict) -> object:
        raise AssertionError("unrelated retained scanner evidence must not be cloned")


def test_executive_briefing_projects_only_required_prior_stage_results() -> None:
    retained = {
        stage_id: {"stage_id": stage_id, "payload": [stage_id]}
        for stage_id in _EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS
    }
    retained["repository_and_delivery_evidence"] = {"large_scanner_tree": _DeepcopyBomb()}
    completed = list(retained)

    projected = _prior_stage_results_for_stage(
        _EXECUTIVE_BRIEFING_STAGE_ID,
        retained,
        completed,
    )

    assert set(projected) == set(_EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS)
    assert "repository_and_delivery_evidence" not in projected
    for stage_id in _EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS:
        assert projected[stage_id] == retained[stage_id]
        assert projected[stage_id] is not retained[stage_id]


def test_executive_briefing_projection_preserves_mutation_isolation() -> None:
    retained = {
        stage_id: {"nested": {"values": [stage_id]}}
        for stage_id in _EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS
    }
    projected = _prior_stage_results_for_stage(
        _EXECUTIVE_BRIEFING_STAGE_ID,
        retained,
        list(retained),
    )

    first_stage = _EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS[0]
    projected[first_stage]["nested"]["values"].append("changed")
    assert retained[first_stage]["nested"]["values"] == [first_stage]


def test_final_report_keeps_existing_reference_contract() -> None:
    retained = {"completed": {"evidence": [1, 2, 3]}}
    projected = _prior_stage_results_for_stage(
        FINAL_REPORT_STAGE_ID,
        retained,
        ["completed"],
    )
    assert projected is retained


def test_other_stages_keep_historical_full_deepcopy_contract() -> None:
    retained = {"example": {"nested": [1, 2, 3]}}
    projected = _prior_stage_results_for_stage(
        "functional_qa",
        retained,
        ["example"],
    )
    assert projected == deepcopy(retained)
    assert projected is not retained
    assert projected["example"] is not retained["example"]
