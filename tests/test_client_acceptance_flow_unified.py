from __future__ import annotations

from nico.approval_queue import create_approval, transition_approval
from nico.client_acceptance import client_acceptance_status, transition_client_acceptance
from nico.client_acceptance_evidence import apply_client_acceptance_evidence
from nico.storage import STORE


def _clear_approvals() -> None:
    tables = getattr(STORE, "_tables", None)
    if isinstance(tables, dict):
        tables["approvals"] = {}


def _base_result() -> dict:
    return {
        "status": "complete",
        "run_id": "run-123",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "release_readiness": {"status": "provisionally_ready_for_human_review"},
        "project_trend_evidence": {"non_regressing": True},
        "sections": [
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "green", "score": 90, "summary": "Ready for review.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Missing.", "evidence": [], "findings": [], "unavailable": []},
        ],
    }


def test_final_report_approval_counts_as_client_acceptance_evidence() -> None:
    _clear_approvals()
    approval = create_approval(
        {
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "requested_action": "final_report_approval",
            "evidence": ["Final review requested for run_id=run-123."],
        }
    )
    approval["run_id"] = "run-123"
    STORE.put("approvals", approval["approval_id"], approval)
    transition_approval(approval["approval_id"], "approved", actor="reviewer", note="Accepted for delivery.")

    result = apply_client_acceptance_evidence(_base_result())
    acceptance = next(item for item in result["sections"] if item["id"] == "client_acceptance")

    assert result["client_acceptance"]["status"] == "accepted"
    assert acceptance["status"] == "green"
    assert acceptance["score"] == 96
    assert any("final_report_approval" in item for item in acceptance["evidence"])


def test_client_acceptance_signoff_counts_as_acceptance_evidence_and_status() -> None:
    _clear_approvals()
    approval = create_approval(
        {
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "requested_action": "client_acceptance_signoff",
            "evidence": ["Client acceptance requested for run_id=run-123."],
        }
    )
    approval["run_id"] = "run-123"
    STORE.put("approvals", approval["approval_id"], approval)

    transitioned = transition_client_acceptance(
        approval["approval_id"],
        "approved",
        actor="client_reviewer",
        note="Client accepts report delivery.",
    )

    assert transitioned["acceptance"]["acceptance_status"] == "accepted"
    assert transitioned["acceptance"]["client_delivery_allowed"] is True

    result = apply_client_acceptance_evidence(_base_result())
    acceptance = next(item for item in result["sections"] if item["id"] == "client_acceptance")

    assert result["client_acceptance"]["status"] == "accepted"
    assert acceptance["status"] == "green"
    assert any("client_acceptance_signoff" in item for item in acceptance["evidence"])


def test_client_acceptance_status_reads_approved_final_review_record() -> None:
    _clear_approvals()
    approval = create_approval(
        {
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "requested_action": "final_report_approval",
            "evidence": ["Final review requested for run_id=run-123."],
        }
    )
    approval["run_id"] = "run-123"
    STORE.put("approvals", approval["approval_id"], approval)
    transition_approval(approval["approval_id"], "approved", actor="technical_reviewer", note="Approved final report.")

    status = client_acceptance_status("run-123", customer_id="cust-a", project_id="proj-a")

    assert status["acceptance_status"] == "accepted"
    assert status["client_delivery_allowed"] is True
    assert status["approved_count"] == 1
    assert "final_report_approval" in status["accepted_actions"]
