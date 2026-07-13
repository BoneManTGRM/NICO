from __future__ import annotations

from nico.approval_queue import create_approval, transition_approval
from nico.client_acceptance import (
    _acceptance_identity,
    request_client_acceptance,
    transition_client_acceptance,
)
from nico.storage import STORE


def _clear_state() -> None:
    tables = getattr(STORE.adapter, "_tables", None)
    if isinstance(tables, dict):
        tables["approvals"] = {}
        tables["assessment_runs"] = {}


def test_client_acceptance_endpoint_cannot_approve_a_pending_final_review():
    _clear_state()
    approval = create_approval(
        {
            "customer_id": "customer-boundary",
            "project_id": "project-boundary",
            "requested_action": "final_report_approval",
            "evidence": ["Final review requested for run_id=run-boundary."],
        }
    )
    approval["run_id"] = "run-boundary"
    STORE.put("approvals", approval["approval_id"], approval)

    blocked = transition_client_acceptance(
        approval["approval_id"],
        "accepted",
        actor="human_reviewer",
        note="Attempted through the wrong workflow.",
    )

    assert blocked["status"] == "blocked"
    assert "final-review workflow" in blocked["error"]
    assert STORE.get("approvals", approval["approval_id"])["status"] == "pending"


def test_correctly_approved_final_review_is_read_only_acceptance_evidence():
    _clear_state()
    approval = create_approval(
        {
            "customer_id": "customer-boundary",
            "project_id": "project-boundary",
            "requested_action": "final_report_approval",
            "evidence": ["Final review requested for run_id=run-boundary-approved."],
        }
    )
    approval["run_id"] = "run-boundary-approved"
    STORE.put("approvals", approval["approval_id"], approval)
    transition_approval(
        approval["approval_id"],
        "approved",
        actor="technical_reviewer",
        note="Approved through the final-review workflow.",
    )

    reused = transition_client_acceptance(
        approval["approval_id"],
        "accepted",
        actor="technical_reviewer",
        note="Read-only status retry.",
    )

    assert reused["status"] == "ok"
    assert reused["idempotent_reuse"] is True
    assert reused["approval"]["status"] == "approved"
    assert reused["acceptance"]["client_delivery_allowed"] is True


def test_deterministic_acceptance_identity_fails_closed_on_action_collision():
    _clear_state()
    run_id = "run-acceptance-collision"
    customer_id = "customer-boundary"
    project_id = "project-boundary"
    approval_id, idempotency_key = _acceptance_identity(run_id, customer_id, project_id)
    create_approval(
        {
            "approval_id": approval_id,
            "idempotency_key": idempotency_key,
            "customer_id": customer_id,
            "project_id": project_id,
            "requested_action": "final_report_approval",
            "evidence": [f"Conflicting action for run_id={run_id}."],
        }
    )

    blocked = request_client_acceptance(
        {
            "run_id": run_id,
            "customer_id": customer_id,
            "project_id": project_id,
        }
    )

    assert blocked["status"] == "blocked"
    assert blocked["approval_id"] == approval_id
    assert "conflicts with another approval scope or action" in blocked["error"]
