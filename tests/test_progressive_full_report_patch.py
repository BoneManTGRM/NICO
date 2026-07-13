from __future__ import annotations

from nico.progressive_full_report_patch import (
    FULL_DETAIL_LEVEL,
    FULL_INCLUDED_MODULES,
    FULL_REPORT_VERSION,
    attach_full_report_depth,
    build_full_executive_detail,
)
from nico.reports import markdown_report


def _assessment() -> dict:
    return {
        "run_id": "fullrun_progressive",
        "repository": "example/repository",
        "executive_summary": "Evidence-bound Full Assessment draft.",
        "maturity_signal": {"level": "Mid", "score": 70},
        "client_delivery_verdict": {
            "status": "human_review_required",
            "confidence": "limited",
            "blockers": ["Final human review is required."],
            "unavailable_items": 1,
        },
        "next_steps": ["Review retained evidence."],
        "sections": [
            {
                "id": "dependencies",
                "label": "Dependencies",
                "status": "yellow",
                "score": 70,
                "summary": "Dependency evidence requires review.",
                "evidence": ["Dependency scanner completed."],
                "verified_claims": ["Lockfile was attached."],
                "findings": ["One dependency requires human triage."],
                "unavailable": [],
                "unverified_claims": [],
            },
            {
                "id": "complexity",
                "label": "Complexity",
                "status": "gray",
                "score": 0,
                "summary": "Complexity evidence is unavailable.",
                "evidence": [],
                "verified_claims": [],
                "findings": [],
                "unavailable": ["No valid same-run complexity measurement."],
                "unverified_claims": [],
            },
        ],
    }


def test_full_detail_extends_mid_without_creating_authority() -> None:
    detail = build_full_executive_detail(_assessment())

    assert detail["report_tier"] == "full"
    assert detail["report_version"] == FULL_REPORT_VERSION
    assert detail["detail_level"] == 3
    assert detail["included_modules"] == list(FULL_INCLUDED_MODULES)
    assert "mid_evidence_and_decision_support" in detail["included_modules"]
    assert detail["cross_domain_synthesis"]["risk_bearing_sections"] == ["Dependencies"]
    assert detail["cross_domain_synthesis"]["sections_with_limitations"] == ["Complexity"]
    assert detail["risk_and_remediation_plan"]["automatic_production_change"] is False
    assert detail["verification_and_rollback"]["production_change_authorized"] is False
    assert detail["final_review_preparation"]["human_review_required"] is True
    assert detail["final_review_preparation"]["approval_created"] is False
    assert detail["final_review_preparation"]["client_delivery_allowed"] is False


def test_full_depth_contract_is_bounded_to_retained_section_truth() -> None:
    detail = build_full_executive_detail(_assessment())

    assert detail["risk_and_remediation_plan"]["prioritized_risks"] == [
        {
            "section_id": "dependencies",
            "section": "Dependencies",
            "status": "yellow",
            "finding": "One dependency requires human triage.",
            "human_review_required": True,
        }
    ]
    assert detail["evidence_appendix_summary"] == [
        {
            "section_id": "dependencies",
            "section": "Dependencies",
            "status": "yellow",
            "evidence_count": 2,
            "finding_count": 1,
            "limitation_count": 0,
        },
        {
            "section_id": "complexity",
            "section": "Complexity",
            "status": "gray",
            "evidence_count": 0,
            "finding_count": 0,
            "limitation_count": 1,
        },
    ]
    assert FULL_DETAIL_LEVEL > 2


def test_full_depth_is_attached_before_rendering_without_changing_scores_or_sections() -> None:
    source = _assessment()
    enriched = attach_full_report_depth(source)

    assert enriched["report_version"] == FULL_REPORT_VERSION
    assert enriched["report_tier"] == "full"
    assert enriched["detail_level"] == 3
    assert enriched["sections"] == source["sections"]
    assert enriched["maturity_signal"] == source["maturity_signal"]
    assert enriched["human_review_required"] is True
    assert enriched["client_ready"] is False
    assert "Full-depth analysis reviewed 2 retained assessment section(s)" in enriched["executive_summary"]
    assert "Review and remediate: One dependency requires human triage." in enriched["next_steps"]
    assert any("rollback plan" in item for item in enriched["next_steps"])
    assert enriched["full_depth_contract"]["final_review_preparation"]["approval_created"] is False


def test_markdown_receives_full_depth_summary_and_action_plan() -> None:
    rendered = markdown_report(attach_full_report_depth(_assessment()))

    assert "Full-depth analysis reviewed 2 retained assessment section(s)" in rendered
    assert "Review and remediate: One dependency requires human triage." in rendered
    assert "Require a reviewed rollback plan" in rendered
    assert "## Required Human Review" in rendered
    assert "code changes require human review" in rendered
