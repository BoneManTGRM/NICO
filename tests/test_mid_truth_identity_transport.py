from __future__ import annotations

from copy import deepcopy

from nico.mid_truth_identity_transport import project_stale_mid_approval_repair


def test_stale_approval_live_projection_requires_post_without_mutating_source() -> None:
    record = {
        "run_id": "midrun_transport_truth",
        "customer_id": "customer_transport",
        "project_id": "project_transport",
        "repository": "BoneManTGRM/NICO",
        "workflow": "mid_assessment",
        "status": "blocked",
        "response": {
            "run_id": "midrun_transport_truth",
            "status": "blocked",
            "current_stage": "approval_request",
            "progress_percent": 100,
            "report_generation_status": "complete",
            "approval_request_status": "blocked",
            "approval_request_error": "The Mid draft is stale relative to the current truth model.",
            "progress": [
                {"step": "scanner_reconciliation", "status": "complete", "message": "Scanner reconciled.", "evidence": {}},
                {"step": "scoring", "status": "complete", "message": "Scoring complete.", "evidence": {}},
                {"step": "reports", "status": "complete", "message": "Report complete.", "evidence": {}},
                {"step": "approval_request", "status": "blocked", "message": "The Mid draft is stale relative to the current truth model.", "evidence": {}},
            ],
            "human_review_required": True,
            "client_ready": False,
        },
    }
    before = deepcopy(record)

    projected = project_stale_mid_approval_repair(record)
    approval_step = next(item for item in projected["progress"] if item["step"] == "approval_request")

    assert record == before
    assert projected["run_id"] == record["run_id"]
    assert projected["status"] == "running"
    assert projected["current_stage"] == "approval_request"
    assert projected["progress_percent"] == 100
    assert projected["approval_request_status"] == "repair_pending"
    assert projected["continuation_required"] is True
    assert projected["same_run_approval_repair"]["live_status_read_only"] is True
    assert projected["same_run_approval_repair"]["post_continuation_required"] is True
    assert projected["same_run_approval_repair"]["repository_recaptured"] is False
    assert projected["same_run_approval_repair"]["scanner_rerun"] is False
    assert projected["same_run_approval_repair"]["score_recomputed"] is False
    assert projected["same_run_approval_repair"]["replacement_run_created"] is False
    assert projected["same_run_approval_repair"]["duplicate_start_allowed"] is False
    assert approval_step["status"] == "running"
    assert approval_step["evidence"]["client_delivery_allowed"] is False
    assert projected["human_review_required"] is True
    assert projected["client_ready"] is False
