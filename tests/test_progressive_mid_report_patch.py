from __future__ import annotations

import nico.mid_assessment_report as report_module
from nico.mid_report_professional_v3 import MID_REPORT_V3_VERSION
from nico.progressive_mid_report_patch import (
    MID_DETAIL_LEVEL,
    MID_INCLUDED_MODULES,
    build_mid_executive_detail,
)


def _payload() -> dict:
    return {
        "sections": [
            {
                "id": "dependencies",
                "label": "Dependencies",
                "truth_status": "Verified",
                "evidence": ["Current-run dependency artifacts are attached."],
                "findings": [],
                "unavailable": [],
                "missing_evidence_sources": [],
                "failed_evidence_tools": [],
                "source_classification": "scanner_artifact",
            },
            {
                "id": "complexity",
                "label": "Complexity",
                "truth_status": "Unavailable",
                "evidence": [],
                "findings": ["Complexity review remains pending."],
                "unavailable": ["No valid same-run complexity measurements."],
                "missing_evidence_sources": [],
                "failed_evidence_tools": [],
                "source_classification": "repository_evidence",
            },
        ],
        "evidence_coverage": {"percent": 75, "numerator": 3, "denominator": 4},
        "review_packet": {
            "exceptions": [
                {"title": "Complexity evidence requires review", "category": "evidence"}
            ]
        },
    }


def test_mid_detail_is_derived_without_upgrading_evidence_or_delivery() -> None:
    detail = build_mid_executive_detail(_payload())

    assert detail["report_tier"] == "mid"
    assert detail["detail_level"] == 2
    assert detail["executive_quick_view"]["verified_areas"] == ["Dependencies"]
    assert detail["executive_quick_view"]["areas_awaiting_verification"] == ["Complexity"]
    assert detail["executive_quick_view"]["evidence_coverage_percent"] == 75
    assert detail["decision_support"]["score_changed"] is False
    assert detail["decision_support"]["evidence_upgraded"] is False
    assert detail["decision_support"]["approval_created"] is False
    assert detail["decision_support"]["client_delivery_allowed"] is False
    assert detail["next_tier_delta"]["tier"] == "full"
    assert detail["next_tier_delta"]["automatic_approval"] is False


def test_mid_report_module_uses_decision_ready_v3_contract() -> None:
    assert report_module.MID_REPORT_VERSION == MID_REPORT_V3_VERSION
    assert MID_DETAIL_LEVEL == 2
    assert "express_baseline" in MID_INCLUDED_MODULES
    assert "review_by_exception" in MID_INCLUDED_MODULES
    assert "decision_support" in MID_INCLUDED_MODULES


def test_professional_payload_adds_decision_layer_without_changing_truth_sections() -> None:
    record = {
        "run_id": "midrun_progressive",
        "customer_id": "customer_one",
        "project_id": "project_one",
        "repository": "example/repository",
        "snapshot_id": "snapshot_one",
        "snapshot_commit_sha": "a" * 40,
        "status": "complete",
        "request": {"client_name": "Client", "project_name": "Project"},
        "response": {
            "assessment": {"maturity_signal": {"level": "Mid", "score": 75}},
            "mid_truth_status": {
                "version": "truth-v2",
                "evidence_coverage": {"percent": 75, "numerator": 3, "denominator": 4},
                "summary": {
                    "verified": 1,
                    "verified_with_limitations": 0,
                    "unavailable": 1,
                    "failed": 0,
                    "human_review_required": 1,
                    "unsupported_claims_permitted": 0,
                },
                "sections": _payload()["sections"],
            },
        },
    }
    packet = {
        "review_packet_id": "packet_one",
        "review_packet_sha256": "b" * 64,
        "summary": {"items_requiring_review": 1},
        "exceptions": _payload()["review_packet"]["exceptions"],
        "verified_sections": ["dependencies"],
    }
    identity = report_module._source_identity(
        record,
        packet,
        record["response"]["mid_truth_status"],
    )
    payload = report_module._report_payload(record, packet, identity, "2026-07-13T20:00:00Z")

    assert payload["report_version"] == MID_REPORT_V3_VERSION
    assert payload["report_tier"] == "Mid"
    assert payload["detail_level"] == 3
    assert payload["included_modules"] == list(MID_INCLUDED_MODULES)
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
    assert payload["approved"] is False
    assert [section["id"] for section in payload["sections"]] == ["dependencies", "complexity"]
    assert payload["executive_quick_view"]["verified_areas"] == ["Dependencies"]
    assert payload["executive_quick_view"]["areas_awaiting_verification"] == ["Complexity"]
    assert payload["decision_support"]["score_changed"] is False
    assert payload["decision_summary"]["technical_score"] == 75
    assert payload["score_integrity"]["human_context_sections_change_score_without_review"] is False
    assert payload["review_exception_final_count"] == 1
