from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_full_report_finish_v1 import _WORKSHEET_TITLES
from nico.comprehensive_human_review_worksheet_title_contract_v1 import (
    WORKSHEET_TITLE_BY_STAGE_ID,
    WORKSHEET_TITLES,
    install_human_review_worksheet_title_contract_v1,
    normalize_human_review_worksheet_titles,
)


FAILED_RUN_ID = "comprun_bcc38fafaadf4550906332c2c17b9264"
LEGACY_RISK_TITLE = "Executive Risk Register and Decision Briefing"
CANONICAL_RISK_TITLE = "Risk Reduction and Executive Briefing"


def _worksheet_stages() -> list[dict]:
    stages = [
        {
            "stage_id": stage_id,
            "title": title,
            "evidence": [f"Evidence retained for {stage_id}."],
        }
        for stage_id, title in WORKSHEET_TITLE_BY_STAGE_ID.items()
    ]
    for stage in stages:
        if stage["stage_id"] == "risk_reduction_and_executive_briefing":
            stage["title"] = LEGACY_RISK_TITLE
    return stages


def test_shared_title_contract_matches_full_data_validator() -> None:
    assert WORKSHEET_TITLES == _WORKSHEET_TITLES
    assert CANONICAL_RISK_TITLE in WORKSHEET_TITLES


def test_failed_run_legacy_risk_title_is_normalized_without_mutation() -> None:
    stages = _worksheet_stages()
    before = deepcopy(stages)

    legacy_titles = {stage["title"] for stage in stages}
    assert CANONICAL_RISK_TITLE not in legacy_titles
    assert CANONICAL_RISK_TITLE in _WORKSHEET_TITLES

    normalized = normalize_human_review_worksheet_titles(stages)
    titles = {stage["title"] for stage in normalized}

    assert not [title for title in _WORKSHEET_TITLES if title not in titles]
    assert LEGACY_RISK_TITLE not in titles
    assert CANONICAL_RISK_TITLE in titles
    assert stages == before
    assert FAILED_RUN_ID.startswith("comprun_")


def test_normalizer_does_not_synthesize_missing_worksheets() -> None:
    stages = [
        {
            "stage_id": "functional_qa",
            "title": "Functional QA",
            "evidence": ["Repository-only QA evidence."],
        }
    ]

    normalized = normalize_human_review_worksheet_titles(stages)

    assert normalized == stages
    assert len(normalized) == 1
    assert all(
        stage["stage_id"] != "risk_reduction_and_executive_briefing"
        for stage in normalized
    )


def test_premium_stage_builder_emits_validator_compatible_risk_title() -> None:
    from nico import v2_premium_report_renderer as premium

    status = install_human_review_worksheet_title_contract_v1()
    stages = premium._canonical_stages(
        {
            "stage_summaries": [
                {
                    "stage_id": "risk_reduction_and_executive_briefing",
                    "title": LEGACY_RISK_TITLE,
                    "evidence": ["Bounded executive evidence."],
                    "findings": [],
                    "unavailable": [],
                }
            ],
            "canonical_findings": [],
        }
    )
    risk_stage = next(
        stage
        for stage in stages
        if stage["stage_id"] == "risk_reduction_and_executive_briefing"
    )

    assert status["canonical_worksheet_titles"] is True
    assert status["missing_stages_not_synthesized"] is True
    assert risk_stage["title"] == CANONICAL_RISK_TITLE
    assert risk_stage["status"] == "review_required"
