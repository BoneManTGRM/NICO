from __future__ import annotations

from nico.express_run_record_integrity import reconcile_record


def _existing_complete() -> dict:
    response = {
        "status": "complete",
        "current_stage": "complete",
        "progress_percent": 100,
        "reports": {"markdown": "# Report", "html": "<h1>Report</h1>", "pdf_base64": "pdf"},
        "sections": [{"id": "architecture", "score": 82}],
        "maturity_signal": {"score": 82, "level": "Senior"},
        "assessment_completion": {"status": "complete_pending_human_review"},
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
        "delivery_status": "blocked_pending_human_review",
    }
    return {"status": "complete", "response": response, "payload": response}


def test_late_running_projection_cannot_revive_completed_run() -> None:
    result = reconcile_record(
        _existing_complete(),
        {"status": "running", "current_stage": "truth_and_review_gates", "progress_percent": 96},
    )
    assert result["status"] == "complete"
    assert result["current_stage"] == "complete"
    assert result["progress_percent"] == 100
    assert result["status_regression_prevented"] is True
    assert result["reports"]["markdown"] == "# Report"
    assert result["maturity_signal"]["score"] == 82


def test_failed_status_cannot_claim_complete_stage() -> None:
    result = reconcile_record({}, {"status": "failed", "current_stage": "complete", "progress_percent": 100})
    assert result["status"] == "failed"
    assert result["current_stage"] == "failed"
    assert result["terminal_stage_contradiction_repaired"] is True
    assert result["client_delivery_allowed"] is False


def test_sparse_final_gate_write_preserves_rich_fields() -> None:
    result = reconcile_record(
        _existing_complete(),
        {"status": "complete", "current_stage": "complete", "progress_percent": 100},
    )
    assert result["reports"]["html"] == "<h1>Report</h1>"
    assert result["sections"][0]["id"] == "architecture"
    assert result["assessment_completion"]["status"] == "complete_pending_human_review"
    assert result["delivery_status"] == "blocked_pending_human_review"
