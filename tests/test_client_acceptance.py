from __future__ import annotations

from nico.client_acceptance import (
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


def test_client_acceptance_gate_blocks_without_evidence_bundle():
    gate = build_client_acceptance_gate({"sections": [], "reports": {}, "human_review_required": True})

    assert gate["status"] == "blocked_missing_evidence"
    assert gate["client_delivery_allowed"] is False
    assert gate["blockers"]


def test_client_acceptance_gate_ready_with_bundle_and_pending_signoffs():
    result = attach_client_acceptance_gate(_assessment("run_gate_ready"))
    gate = result["client_acceptance"]

    assert gate["status"] == "ready_for_human_signoff_with_disclosures"
    assert gate["client_delivery_allowed"] is False
    assert gate["evidence_bundle_hash"]
    assert len(gate["required_signoffs"]) == 2
    assert gate["disclosures"]["unavailable_count"] > 0


def test_client_acceptance_request_and_transition_allows_delivery_after_approval():
    run_id = "run_client_acceptance_transition"
    payload = attach_client_acceptance_gate(_assessment(run_id))
    STORE.put(
        "assessment_runs",
        run_id,
        {
            "workflow": "express",
            "customer_id": "customer_acceptance",
            "project_id": "project_acceptance",
            "status": "complete",
            "payload": payload,
        },
    )

    requested = request_client_acceptance(
        {
            "run_id": run_id,
            "customer_id": "customer_acceptance",
            "project_id": "project_acceptance",
            "requester": "nico-test",
        }
    )

    assert requested["status"] == "pending_acceptance"
    approval_id = requested["approval"]["approval_id"]
    pending = client_acceptance_status(run_id, "customer_acceptance", "project_acceptance")
    assert pending["client_delivery_allowed"] is False

    accepted = transition_client_acceptance(approval_id, "accepted", actor="human_reviewer", note="Approved for client delivery.")

    assert accepted["status"] == "ok"
    assert accepted["acceptance"]["acceptance_status"] == "accepted"
    assert accepted["acceptance"]["client_delivery_allowed"] is True
