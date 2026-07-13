from __future__ import annotations

from nico.client_acceptance import (
    CLIENT_ACCEPTANCE_ACTION,
    FINAL_REVIEW_ACTION,
    attach_client_acceptance_gate,
    build_client_acceptance_gate,
    client_acceptance_status,
    request_client_acceptance,
    transition_client_acceptance,
)
from nico.evidence_artifact_bundle import attach_evidence_artifact_bundle
from nico.storage import STORE


def _assessment(run_id: str = "run_client_acceptance_test") -> dict:
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": run_id,
        "run_id": run_id,
        "assessment_mode": "express",
        "timeframe_days": 180,
        "repository_metadata": {"default_branch": "main"},
        "maturity_signal": {"level": "Senior", "score": 90},
        "maturity_semaphore": {"Code Audit": "green"},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 90,
                "status": "green",
                "summary": "Code review.",
                "evidence": ["Evidence exists."],
                "findings": [],
                "unavailable": [],
            }
        ],
        "findings": [],
        "repairs": [],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "# Report\n", "html": "<html>Report</html>"},
        "human_review_required": True,
        "safety_boundary": "Authorized defensive assessment only.",
    }
    return attach_evidence_artifact_bundle(result)


def _store_assessment(run_id: str, customer_id: str = "customer_acceptance", project_id: str = "project_acceptance") -> dict:
    payload = attach_client_acceptance_gate(_assessment(run_id))
    STORE.put(
        "assessment_runs",
        run_id,
        {
            "workflow": "express",
            "customer_id": customer_id,
            "project_id": project_id,
            "status": "complete",
            "payload": payload,
        },
    )
    return payload


def test_client_acceptance_gate_blocks_without_evidence_bundle():
    gate = build_client_acceptance_gate({"sections": [], "reports": {}, "human_review_required": True})

    assert gate["status"] == "blocked_missing_evidence"
    assert gate["client_delivery_allowed"] is False
    assert gate["blockers"]


def test_client_acceptance_gate_truthfully_requires_one_of_two_authorized_actions():
    result = attach_client_acceptance_gate(_assessment("run_gate_ready"))
    gate = result["client_acceptance"]

    assert gate["status"] == "ready_for_human_signoff_with_disclosures"
    assert gate["client_delivery_allowed"] is False
    assert gate["evidence_bundle_hash"]
    assert gate["minimum_approved_signoffs"] == 1
    assert len(gate["required_signoffs"]) == 1
    assert gate["required_signoffs"][0]["role"] == "authorized_human_reviewer"
    assert gate["required_signoffs"][0]["accepted_actions"] == sorted(
        [CLIENT_ACCEPTANCE_ACTION, FINAL_REVIEW_ACTION]
    )
    assert gate["disclosures"]["unavailable_count"] > 0
    assert "one same-run authorized human signoff" in gate["rule"]


def test_client_acceptance_request_and_transition_resolve_the_nested_gate():
    run_id = "run_client_acceptance_transition"
    _store_assessment(run_id)

    requested = request_client_acceptance(
        {
            "run_id": run_id,
            "customer_id": "customer_acceptance",
            "project_id": "project_acceptance",
            "requester": "nico-test",
        }
    )

    assert requested["status"] == "pending_acceptance"
    assert requested["idempotent_reuse"] is False
    approval_id = requested["approval"]["approval_id"]
    pending = client_acceptance_status(run_id, "customer_acceptance", "project_acceptance")
    assert pending["client_delivery_allowed"] is False
    assert pending["approval_count"] == 1
    assert pending["approved_count"] == 0
    assert pending["client_acceptance"]["required_signoffs"][0]["status"] == "pending"

    accepted = transition_client_acceptance(
        approval_id,
        "accepted",
        actor="human_reviewer",
        note="Approved for client delivery after reviewing evidence and disclosures.",
    )

    assert accepted["status"] == "ok"
    assert accepted["idempotent_reuse"] is False
    assert accepted["acceptance"]["acceptance_status"] == "accepted"
    assert accepted["acceptance"]["client_delivery_allowed"] is True
    gate = accepted["acceptance"]["client_acceptance"]
    assert gate["status"] == "accepted"
    assert gate["client_delivery_allowed"] is True
    assert gate["human_review_required"] is False
    assert gate["required_signoffs"][0]["status"] == "approved"
    assert gate["required_signoffs"][0]["approval_id"] == approval_id
    assert gate["required_signoffs"][0]["action"] == CLIENT_ACCEPTANCE_ACTION


def test_client_acceptance_request_is_idempotent_for_one_run_scope():
    run_id = "run_client_acceptance_idempotent"
    _store_assessment(run_id)
    payload = {
        "run_id": run_id,
        "customer_id": "customer_acceptance",
        "project_id": "project_acceptance",
        "requester": "nico-test",
    }

    first = request_client_acceptance(payload)
    repeated = request_client_acceptance(payload)

    assert first["status"] == "pending_acceptance"
    assert first["idempotent_reuse"] is False
    assert repeated["status"] == "pending_acceptance"
    assert repeated["idempotent_reuse"] is True
    assert repeated["approval"]["approval_id"] == first["approval"]["approval_id"]
    status = client_acceptance_status(run_id, "customer_acceptance", "project_acceptance")
    assert status["approval_count"] == 1
    assert status["total_approval_history_count"] == 1


def test_client_acceptance_cannot_approve_missing_evidence():
    run_id = "run_client_acceptance_missing_evidence"
    STORE.put(
        "assessment_runs",
        run_id,
        {
            "workflow": "express",
            "customer_id": "customer_acceptance",
            "project_id": "project_acceptance",
            "status": "complete",
            "payload": {
                "status": "complete",
                "run_id": run_id,
                "repository": "BoneManTGRM/NICO",
                "sections": [],
                "reports": {},
                "human_review_required": True,
            },
        },
    )
    requested = request_client_acceptance(
        {
            "run_id": run_id,
            "customer_id": "customer_acceptance",
            "project_id": "project_acceptance",
        }
    )

    blocked = transition_client_acceptance(
        requested["approval"]["approval_id"],
        "accepted",
        actor="human_reviewer",
        note="Attempted approval.",
    )

    assert blocked["status"] == "blocked"
    assert blocked["acceptance_validation"]["ready_for_approval"] is False
    assert blocked["acceptance_validation"]["blockers"]
    status = client_acceptance_status(run_id, "customer_acceptance", "project_acceptance")
    assert status["client_delivery_allowed"] is False
    assert status["approved_count"] == 0


def test_client_acceptance_terminal_decision_is_idempotent_and_immutable():
    run_id = "run_client_acceptance_terminal"
    _store_assessment(run_id)
    requested = request_client_acceptance(
        {
            "run_id": run_id,
            "customer_id": "customer_acceptance",
            "project_id": "project_acceptance",
        }
    )
    approval_id = requested["approval"]["approval_id"]

    first = transition_client_acceptance(
        approval_id,
        "accepted",
        actor="human_reviewer",
        note="Approved after review.",
    )
    repeated = transition_client_acceptance(
        approval_id,
        "accepted",
        actor="human_reviewer",
        note="Repeated action.",
    )
    conflicting = transition_client_acceptance(
        approval_id,
        "rejected",
        actor="human_reviewer",
        note="Conflicting action.",
    )

    assert first["status"] == "ok"
    assert repeated["status"] == "ok"
    assert repeated["idempotent_reuse"] is True
    assert conflicting["status"] == "blocked"
    assert "already terminal" in conflicting["error"]
    assert client_acceptance_status(run_id, "customer_acceptance", "project_acceptance")["acceptance_status"] == "accepted"


def test_client_acceptance_requires_human_identity_and_negative_decision_note():
    run_id = "run_client_acceptance_human_fields"
    _store_assessment(run_id)
    requested = request_client_acceptance(
        {
            "run_id": run_id,
            "customer_id": "customer_acceptance",
            "project_id": "project_acceptance",
        }
    )
    approval_id = requested["approval"]["approval_id"]

    missing_actor = transition_client_acceptance(approval_id, "accepted", actor="", note="Approved.")
    missing_note = transition_client_acceptance(approval_id, "rejected", actor="reviewer", note="")

    assert missing_actor["status"] == "blocked"
    assert "identity" in missing_actor["error"]
    assert missing_note["status"] == "blocked"
    assert "note" in missing_note["error"]
