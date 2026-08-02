from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_post_readiness_maturity_truth_v2 import (
    install_post_readiness_maturity_truth,
)
from nico.comprehensive_post_readiness_report_contract_truth_v1 import (
    install_post_readiness_report_contract_truth,
    remove_superseded_report_contract_diagnostics,
    strip_superseded_report_contract_text,
)

MATURITY_INSTALLATION = install_post_readiness_maturity_truth()
INSTALLATION = install_post_readiness_report_contract_truth()

from nico.comprehensive_client_readiness_v59 import reconcile_client_readiness


def _canonical() -> dict:
    return {
        "service_id": "comprehensive",
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "run_id": "comprun_post_readiness_report_contract",
        },
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 90,
            "maturity_level": "Senior",
            "report_contract_status": "blocked",
            "report_contract_reason": "executive_decision_brief_page_gate_failed",
            "sections": [],
        },
        "stage_summaries": [
            {
                "stage_id": "report_contract_validation",
                "status": "complete",
                "evidence": [
                    "report_contract_status: blocked",
                    "core_report_contract_reason = canonical_score_truth_mismatch",
                    "Client Delivery Blocked",
                    "Human approval remains required",
                ],
            },
            {
                "stage_id": "current_delivery_truth",
                "report_contract_status": "ready_for_internal_review",
                "report_contract_reason": "human_approval_required",
            },
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_post_readiness_report_contract_installer_is_bound() -> None:
    assert MATURITY_INSTALLATION["bound"] is True
    assert INSTALLATION["bound"] is True
    assert INSTALLATION["post_readiness_boundary"] is True
    assert INSTALLATION["strict_semantic_validation_preserved"] is True


def test_superseded_structured_and_text_diagnostics_are_removed() -> None:
    canonical = _canonical()
    source = deepcopy(canonical)

    output = reconcile_client_readiness(canonical)
    rendered = repr(output).casefold()

    assert canonical == source
    assert "report_contract_status: blocked" not in rendered
    assert "executive_decision_brief_page_gate_failed" not in rendered
    assert "canonical_score_truth_mismatch" not in rendered
    assert "report_contract_status" not in output["assessment"]
    assert "report_contract_reason" not in output["assessment"]

    evidence = output["stage_summaries"][0]["evidence"]
    assert evidence == [
        "Client Delivery Blocked",
        "Human approval remains required",
    ]

    current = output["stage_summaries"][1]
    assert current["report_contract_status"] == "ready_for_internal_review"
    assert current["report_contract_reason"] == "human_approval_required"

    manifest = output["post_readiness_report_contract_truth"]
    assert manifest["status"] == "applied"
    assert manifest["removed_count"] == 4
    assert manifest["raw_diagnostic_repeated_in_client_manifest"] is False
    assert all(
        item["original_value_retained_in_client_manifest"] is False
        for item in manifest["removals"]
    )
    assert output["client_readiness_contract"]["maturity_label"] == "Exceptional"
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False


def test_text_cleanup_is_narrow_and_preserves_delivery_language() -> None:
    source = (
        "report_contract_status: blocked; Client Delivery Blocked; "
        "Senior engineering reviewer required"
    )
    output = strip_superseded_report_contract_text(source)

    assert output == "Client Delivery Blocked; Senior engineering reviewer required"


def test_direct_cleanup_preserves_non_superseded_contract_values() -> None:
    canonical = {
        "report_contract_status": "ready_for_internal_review",
        "report_contract_reason": "human_approval_required",
        "note": "Client Delivery Blocked",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    output, manifest = remove_superseded_report_contract_diagnostics(canonical)

    assert output["report_contract_status"] == "ready_for_internal_review"
    assert output["report_contract_reason"] == "human_approval_required"
    assert output["note"] == "Client Delivery Blocked"
    assert manifest["status"] == "not_needed"
    assert manifest["removed_count"] == 0
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False
