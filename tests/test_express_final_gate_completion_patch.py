from __future__ import annotations

import base64

import pytest

from nico.express_final_gate_completion_patch import (
    normalize_assessment_completion,
    normalize_express_completion,
)


def _pdf() -> str:
    return base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n").decode("ascii")


def _complete_payload(tier: str = "express") -> dict:
    return {
        "status": "complete",
        "assessment_type": tier,
        "repository": "owner/repo",
        "sections": [{"id": "architecture", "score": 80}],
        "maturity_signal": {"score": 80},
        "reports": {
            "markdown": "# Report",
            "html": "<h1>Report</h1>",
            "pdf_base64": _pdf(),
        },
        "human_review_required": True,
        "client_ready": False,
    }


@pytest.mark.parametrize("tier", ["express", "mid", "full"])
def test_delivery_block_does_not_convert_completed_assessment_to_failed_run(tier: str) -> None:
    before = _complete_payload(tier)
    after = {
        **before,
        "status": "blocked",
        "client_acceptance": {"status": "blocked_missing_evidence", "client_delivery_allowed": False},
        "report_quality_guards": {"status": "review_required"},
    }
    result = normalize_assessment_completion(before, after)
    assert result["status"] == "complete"
    assert result["current_stage"] == "complete"
    assert result["progress_percent"] == 100
    assert result["report_generation_status"] == "complete"
    assert result["delivery_status"] == "blocked_pending_human_review"
    assert result["client_delivery_allowed"] is False
    assert result["human_review_required"] is True
    assert result["assessment_completion"]["tier"] == tier
    assert result["assessment_completion"]["status"] == "complete_pending_human_review"
    assert ("express_completion" in result) is (tier == "express")


def test_backward_compatible_express_alias_uses_canonical_contract() -> None:
    before = _complete_payload()
    result = normalize_express_completion(before, {**before, "status": "blocked"})
    assert result["assessment_completion"] == result["express_completion"]


@pytest.mark.parametrize("tier", ["express", "mid", "full"])
def test_missing_report_formats_remains_blocked_for_every_tier(tier: str) -> None:
    before = _complete_payload(tier)
    before["reports"] = {"markdown": "# Report", "html": "<h1>Report</h1>"}
    result = normalize_assessment_completion(before, {**before, "status": "blocked"})
    assert result["status"] == "blocked"
    assert result["assessment_completion"]["status"] == "blocked_missing_completion_evidence"
    assert result["assessment_completion"]["report_formats_ready"] is False


def _hashed_bundle() -> dict:
    return {
        "bundle_hash": "d" * 64,
        "artifacts": {
            "markdown": {"available": True, "sha256": "a" * 64},
            "html": {"available": True, "sha256": "b" * 64},
            "pdf": {"available": True, "sha256": "c" * 64},
        },
    }


def test_hashed_artifact_bundle_can_prove_formats_after_safe_payload_reduction_for_mid() -> None:
    before = _complete_payload("mid")
    after = {
        "status": "blocked",
        "assessment_type": "mid",
        "sections": before["sections"],
        "maturity_signal": before["maturity_signal"],
        "evidence_artifact_bundle": _hashed_bundle(),
        "client_acceptance": {"status": "ready_for_human_signoff"},
    }
    result = normalize_assessment_completion(before, after)
    assert result["status"] == "complete"
    assert result["assessment_completion"]["report_formats_ready"] is True
    assert "express_completion" not in result


def test_express_hash_only_evidence_cannot_claim_usable_report_completion() -> None:
    before = _complete_payload("express")
    before["reports"] = {}
    after = {
        "status": "blocked",
        "assessment_type": "express",
        "sections": before["sections"],
        "maturity_signal": before["maturity_signal"],
        "evidence_artifact_bundle": _hashed_bundle(),
    }
    result = normalize_assessment_completion(before, after)
    assert result["status"] == "blocked"
    assert result["express_completion"]["report_formats_ready"] is False
    assert result["report_generation_status"] == "blocked_missing_usable_artifacts"
    assert "usable Markdown, HTML, and PDF" in result["report_format_error"]


def test_missing_score_or_sections_cannot_be_inferred_as_completion() -> None:
    before = _complete_payload("full")
    before.pop("maturity_signal")
    before["sections"] = []
    result = normalize_assessment_completion(before, {**before, "status": "blocked"})
    assert result["status"] == "blocked"
    assert result["assessment_completion"]["score_ready"] is False
    assert result["assessment_completion"]["sections_ready"] is False


def test_unknown_tier_is_not_reclassified() -> None:
    before = _complete_payload("custom")
    after = {**before, "status": "blocked"}
    assert normalize_assessment_completion(before, after) == after
