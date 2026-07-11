from __future__ import annotations

import base64
from uuid import uuid4

from nico.final_review_workflow import request_final_review, transition_final_review
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_review_{suffix}",
        f"report_review_{suffix}",
        f"customer_review_{suffix}",
        f"project_review_{suffix}",
    )


def _store_full_assessment_report(
    run_id: str,
    report_id: str,
    customer_id: str,
    project_id: str,
    *,
    gate_status: str = "passed",
    pdf_bytes: bytes = b"%PDF-1.4\nreview fixture\n",
    report_path: str = "full_run",
) -> None:
    STORE.put(
        "reports",
        report_id,
        {
            "status": "complete",
            "report_id": report_id,
            "run_id": run_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "formats": {
                "markdown": "# NICO Full Assessment\n",
                "html": "<h1>NICO Full Assessment</h1>",
                "json": {
                    "status": "draft",
                    "run_id": run_id,
                    "report_id": report_id,
                    "report_path": report_path,
                    "repository": "BoneManTGRM/NICO",
                    "maturity_signal": {"level": "Senior", "score": 91},
                    "export_truth_gate": {"status": gate_status},
                    "human_review_required": True,
                    "client_ready": False,
                },
                "pdf": base64.b64encode(pdf_bytes).decode("ascii"),
            },
            "export_truth_gate": {"status": gate_status},
            "client_delivery_allowed": False,
            "human_review_required": True,
        },
    )


def _request(run_id: str, report_id: str, customer_id: str, project_id: str) -> dict:
    response = request_final_review(
        {
            "run_id": run_id,
            "report_id": report_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "requester": "test-suite",
        }
    )
    assert response["status"] == "pending_review"
    return response["approval"]


def test_final_review_approves_only_exact_valid_full_assessment_package():
    run_id, report_id, customer_id, project_id = _identity()
    _store_full_assessment_report(run_id, report_id, customer_id, project_id)
    approval = _request(run_id, report_id, customer_id, project_id)

    assert approval["review_validation"]["ready_for_approval"] is True
    assert all(item["passed"] for item in approval["review_validation"]["checks"])

    result = transition_final_review(
        approval["approval_id"],
        "approved",
        actor="technical_reviewer",
        note="Reviewed scorecard, evidence limits, unavailable data, and draft PDF.",
    )

    assert result["status"] == "ok"
    assert result["approval"]["status"] == "approved"
    assert result["approval"]["approver"] == "technical_reviewer"
    assert result["approval"]["review_decision"]["client_delivery_allowed"] is True
    assert result["approval"]["review_validation"]["ready_for_approval"] is True


def test_final_review_blocks_approval_when_export_truth_gate_did_not_pass():
    run_id, report_id, customer_id, project_id = _identity()
    _store_full_assessment_report(
        run_id,
        report_id,
        customer_id,
        project_id,
        gate_status="review_required",
    )
    approval = _request(run_id, report_id, customer_id, project_id)

    result = transition_final_review(
        approval["approval_id"],
        "approved",
        actor="technical_reviewer",
        note="Attempted approval.",
    )

    assert result["status"] == "blocked"
    assert result["review_validation"]["ready_for_approval"] is False
    assert "Export Truth Gate passed" in " ".join(result["review_validation"]["blockers"])
    assert STORE.get("approvals", approval["approval_id"])["status"] == "pending"


def test_final_review_blocks_approval_when_pdf_integrity_fails():
    run_id, report_id, customer_id, project_id = _identity()
    _store_full_assessment_report(
        run_id,
        report_id,
        customer_id,
        project_id,
        pdf_bytes=b"not-a-pdf",
    )
    approval = _request(run_id, report_id, customer_id, project_id)

    result = transition_final_review(
        approval["approval_id"],
        "approved",
        actor="technical_reviewer",
    )

    assert result["status"] == "blocked"
    assert result["review_validation"]["ready_for_approval"] is False
    assert "valid PDF header" in " ".join(result["review_validation"]["blockers"])


def test_final_review_requires_note_for_more_evidence_or_rejection():
    run_id, report_id, customer_id, project_id = _identity()
    _store_full_assessment_report(run_id, report_id, customer_id, project_id)
    approval = _request(run_id, report_id, customer_id, project_id)

    for state in ("needs_more_evidence", "rejected"):
        result = transition_final_review(
            approval["approval_id"],
            state,
            actor="technical_reviewer",
            note="",
        )
        assert result["status"] == "blocked"
        assert "review note is required" in result["error"].lower()

    assert STORE.get("approvals", approval["approval_id"])["status"] == "pending"


def test_final_review_terminal_decision_is_immutable_but_same_state_is_idempotent():
    run_id, report_id, customer_id, project_id = _identity()
    _store_full_assessment_report(run_id, report_id, customer_id, project_id)
    approval = _request(run_id, report_id, customer_id, project_id)

    approved = transition_final_review(
        approval["approval_id"],
        "approved",
        actor="technical_reviewer",
        note="Approved after review.",
    )
    assert approved["status"] == "ok"

    repeated = transition_final_review(
        approval["approval_id"],
        "approved",
        actor="technical_reviewer",
        note="Repeated click.",
    )
    assert repeated["status"] == "ok"
    assert repeated["idempotent_reuse"] is True

    changed = transition_final_review(
        approval["approval_id"],
        "rejected",
        actor="technical_reviewer",
        note="Attempted reversal.",
    )
    assert changed["status"] == "blocked"
    assert "already terminal" in changed["error"]
    assert STORE.get("approvals", approval["approval_id"])["status"] == "approved"
