from __future__ import annotations

import base64

from nico.express_backend_final_gate_truth import reconcile_express_backend_completion


def _pdf() -> str:
    return base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n").decode("ascii")


def _complete_result() -> dict:
    return {
        "assessment_type": "express",
        "status": "running",
        "reports": {
            "markdown": "# Report",
            "html": "<h1>Report</h1>",
            "pdf_base64": _pdf(),
        },
        "sections": [{"id": "architecture", "score": 80}],
        "maturity_signal": {"score": 80},
        "human_review_required": True,
    }


def test_client_acceptance_block_cannot_convert_completed_assessment_to_failed_run() -> None:
    before = _complete_result()
    after = {
        "assessment_type": "express",
        "status": "blocked",
        "client_acceptance": {
            "status": "blocked_pending_human_review",
            "client_delivery_allowed": False,
        },
    }
    result = reconcile_express_backend_completion(before, after)
    assert result["status"] == "complete"
    assert result["current_stage"] == "complete"
    assert result["progress_percent"] == 100
    assert result["assessment_completion"]["status"] == "complete_pending_human_review"
    assert result["assessment_completion"]["report_formats_ready"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["delivery_status"] == "blocked_pending_human_review"


def test_gate_preserves_report_score_sections_and_evidence_fields() -> None:
    before = {
        **_complete_result(),
        "evidence_readiness": {"status": "ready"},
        "evidence_artifact_bundle": {"bundle_hash": "a" * 64},
        "findings": [{"id": "F-1"}],
        "repair_intelligence": {"actions": ["repair"]},
        "report_quality_guards": {"status": "pass"},
    }
    result = reconcile_express_backend_completion(before, {"assessment_type": "express", "status": "blocked"})
    for field in (
        "reports",
        "sections",
        "maturity_signal",
        "evidence_readiness",
        "evidence_artifact_bundle",
        "findings",
        "repair_intelligence",
        "report_quality_guards",
    ):
        assert result[field] == before[field]


def test_missing_or_truncated_artifacts_fail_closed_with_specific_evidence() -> None:
    before = _complete_result()
    before["reports"]["pdf_base64"] = base64.b64encode(b"%PDF-1.4 truncated").decode("ascii")
    result = reconcile_express_backend_completion(before, {"assessment_type": "express", "status": "running"})
    assert result["status"] == "blocked"
    assert result["current_stage"] == "truth_and_review_gates"
    assert result["recovery_required"] is True
    assert result["recovery_code"] == "express_backend_completion_evidence_missing"
    assert result["assessment_completion"]["pdf_ready"] is False
    assert "pdf" in result["assessment_completion"]["missing"]


def test_missing_score_or_sections_never_claims_completion() -> None:
    before = _complete_result()
    before["sections"] = []
    before["maturity_signal"] = {}
    result = reconcile_express_backend_completion(before, {"assessment_type": "express", "status": "blocked"})
    assert result["status"] == "blocked"
    assert result["assessment_completion"]["sections_ready"] is False
    assert result["assessment_completion"]["score_ready"] is False
    assert set(result["assessment_completion"]["missing"]) >= {"sections", "score"}


def test_non_express_tier_is_not_reclassified() -> None:
    before = {**_complete_result(), "assessment_type": "mid"}
    after = {"assessment_type": "mid", "status": "blocked"}
    assert reconcile_express_backend_completion(before, after) == after
