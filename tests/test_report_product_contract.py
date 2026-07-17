from __future__ import annotations

import pytest

from nico.report_product_contract import (
    REPORT_TIER_CONTRACTS,
    evaluate_report_product_quality,
    get_report_tier_contract,
    normalize_report_tier,
)


def test_tier_aliases_and_depth_order() -> None:
    assert normalize_report_tier("quick") == "express"
    assert normalize_report_tier("medium") == "mid"
    assert normalize_report_tier("enterprise") == "full"
    assert REPORT_TIER_CONTRACTS["express"].minimum_substantive_pages < REPORT_TIER_CONTRACTS["mid"].minimum_substantive_pages < REPORT_TIER_CONTRACTS["full"].minimum_substantive_pages


def test_unknown_tier_fails_closed() -> None:
    with pytest.raises(ValueError):
        get_report_tier_contract("unknown")


def test_visible_markup_blocks_release() -> None:
    result = evaluate_report_product_quality(
        tier="express",
        page_count=15,
        rendered_text="DRAFT — HUMAN REVIEW REQUIRED <b>Proceed</b>",
        section_presence={name: True for name in REPORT_TIER_CONTRACTS["express"].required_sections},
        visual_presence={name: True for name in REPORT_TIER_CONTRACTS["express"].required_visuals},
    )
    assert result["release_blocked"] is True
    assert {item["code"] for item in result["defects"]} == {"visible_markup"}


def test_approved_artifact_cannot_say_draft() -> None:
    result = evaluate_report_product_quality(
        tier="mid",
        page_count=40,
        rendered_text="DRAFT — approved technical assessment",
        approved=True,
        section_presence={name: True for name in REPORT_TIER_CONTRACTS["mid"].required_sections},
        visual_presence={name: True for name in REPORT_TIER_CONTRACTS["mid"].required_visuals},
    )
    assert result["release_blocked"] is True
    assert any(item["code"] == "approved_artifact_marked_draft" for item in result["defects"])


def test_page_depth_only_enforced_when_evidence_supports_it() -> None:
    kwargs = dict(
        tier="full",
        page_count=20,
        rendered_text="HUMAN REVIEW REQUIRED",
        section_presence={name: True for name in REPORT_TIER_CONTRACTS["full"].required_sections},
        visual_presence={name: True for name in REPORT_TIER_CONTRACTS["full"].required_visuals},
    )
    assert evaluate_report_product_quality(**kwargs, evidence_sufficient_for_depth=False)["product_ready"] is True
    result = evaluate_report_product_quality(**kwargs, evidence_sufficient_for_depth=True)
    assert result["product_ready"] is False
    assert any(item["code"] == "insufficient_substantive_depth" for item in result["defects"])


def test_complete_mid_contract_is_product_ready() -> None:
    contract = REPORT_TIER_CONTRACTS["mid"]
    result = evaluate_report_product_quality(
        tier="mid",
        page_count=40,
        rendered_text="HUMAN REVIEW REQUIRED — immutable assessment",
        section_presence={name: True for name in contract.required_sections},
        visual_presence={name: True for name in contract.required_visuals},
        evidence_sufficient_for_depth=True,
    )
    assert result["defects"] == []
    assert result["product_ready"] is True
