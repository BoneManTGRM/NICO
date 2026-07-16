from __future__ import annotations

from copy import deepcopy

from nico.mid_truth_identity_transport import _scope_matches, project_stale_mid_approval_repair


def _record() -> dict:
    return {
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


def test_stale_approval_live_projection_requires_post_without_mutating_source() -> None:
    record = _record()
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
    assert projected["same_run_approval_repair"]["tenant_scope_required"] is True
    assert projected["same_run_approval_repair"]["repository_recaptured"] is False
    assert projected["same_run_approval_repair"]["scanner_rerun"] is False
    assert projected["same_run_approval_repair"]["score_recomputed"] is False
    assert projected["same_run_approval_repair"]["replacement_run_created"] is False
    assert projected["same_run_approval_repair"]["duplicate_start_allowed"] is False
    assert approval_step["status"] == "running"
    assert approval_step["evidence"]["client_delivery_allowed"] is False
    assert projected["human_review_required"] is True
    assert projected["client_ready"] is False


def test_same_run_post_repair_requires_exact_customer_and_project_scope() -> None:
    record = _record()

    assert _scope_matches(record, "customer_transport", "project_transport") is True
    assert _scope_matches(record, "customer_wrong", "project_transport") is False
    assert _scope_matches(record, "customer_transport", "project_wrong") is False
    assert _scope_matches(record, "default_customer", "default_project") is False


def test_scope_falls_back_to_retained_request_identity_without_cross_tenant_defaults() -> None:
    record = _record()
    record.pop("customer_id")
    record.pop("project_id")
    record["request"] = {
        "customer_id": "customer_from_request",
        "project_id": "project_from_request",
    }

    assert _scope_matches(record, "customer_from_request", "project_from_request") is True
    assert _scope_matches(record, "default_customer", "default_project") is False
