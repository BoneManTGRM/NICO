from __future__ import annotations

from nico.express_final_gate_completion_patch import normalize_express_completion


def _complete_payload() -> dict:
    return {
        "status": "complete",
        "assessment_type": "express",
        "repository": "owner/repo",
        "sections": [{"id": "architecture", "score": 80}],
        "maturity_signal": {"score": 80},
        "reports": {
            "markdown": "# Report",
            "html": "<h1>Report</h1>",
            "pdf_base64": "JVBERi0xLjQ=",
        },
        "human_review_required": True,
        "client_ready": False,
    }


def test_delivery_block_does_not_convert_completed_assessment_to_failed_run() -> None:
    before = _complete_payload()
    after = {
        **before,
        "status": "blocked",
        "client_acceptance": {
            "status": "blocked_missing_evidence",
            "client_delivery_allowed": False,
        },
        "report_quality_guards": {"status": "review_required"},
    }

    result = normalize_express_completion(before, after)

    assert result["status"] == "complete"
    assert result["current_stage"] == "complete"
    assert result["progress_percent"] == 100
    assert result["report_generation_status"] == "complete"
    assert result["delivery_status"] == "blocked_pending_human_review"
    assert result["client_delivery_allowed"] is False
    assert result["human_review_required"] is True
    assert result["client_acceptance"]["status"] == "blocked_missing_evidence"
    assert result["express_completion"]["status"] == "complete_pending_human_review"


def test_missing_report_formats_remains_blocked() -> None:
    before = _complete_payload()
    before["reports"] = {"markdown": "# Report", "html": "<h1>Report</h1>"}
    after = {**before, "status": "blocked"}

    result = normalize_express_completion(before, after)

    assert result["status"] == "blocked"
    assert result["express_completion"]["status"] == "blocked_missing_completion_evidence"
    assert result["express_completion"]["report_formats_ready"] is False


def test_hashed_artifact_bundle_can_prove_formats_after_safe_payload_reduction() -> None:
    before = _complete_payload()
    after = {
        "status": "blocked",
        "assessment_type": "express",
        "sections": before["sections"],
        "maturity_signal": before["maturity_signal"],
        "evidence_artifact_bundle": {
            "bundle_hash": "d" * 64,
            "artifacts": {
                "markdown": {"available": True, "sha256": "a" * 64},
                "html": {"available": True, "sha256": "b" * 64},
                "pdf": {"available": True, "sha256": "c" * 64},
            },
        },
        "client_acceptance": {"status": "ready_for_human_signoff"},
    }

    result = normalize_express_completion(before, after)

    assert result["status"] == "complete"
    assert result["express_completion"]["report_formats_ready"] is True
    assert result["client_ready"] is False


def test_missing_score_or_sections_cannot_be_inferred_as_completion() -> None:
    before = _complete_payload()
    before.pop("maturity_signal")
    before["sections"] = []
    after = {**before, "status": "blocked"}

    result = normalize_express_completion(before, after)

    assert result["status"] == "blocked"
    assert result["express_completion"]["score_ready"] is False
    assert result["express_completion"]["sections_ready"] is False
