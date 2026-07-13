from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from nico import approved_delivery_access as access
from nico import approved_delivery_acknowledgments as acknowledgments
from nico import approved_delivery_atomic as atomic
from nico import approved_delivery_receipts as receipts
from nico.approved_delivery_operational_readiness import approved_delivery_operational_readiness
from nico.final_review_workflow import final_review_status, request_final_review, transition_final_review
from nico.storage import STORE


ADMIN_TOKEN = "test-admin-token"
REPOSITORY = "BoneManTGRM/NICO"


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:12]
    return (
        f"fullrun_unified_e2e_{suffix}",
        f"report_unified_e2e_{suffix}",
        f"approval_unified_e2e_{suffix}",
        f"customer_unified_e2e_{suffix}",
        f"project_unified_e2e_{suffix}",
    )


def _draft_report(run_id: str, report_id: str, customer_id: str, project_id: str) -> dict:
    source_pdf = b"%PDF-1.4\nfull-unified-e2e-draft\n%%EOF\n"
    return {
        "status": "complete",
        "record_type": "full_assessment_report",
        "report_id": report_id,
        "report_path": "full_run",
        "report_path_label": "Full Assessment",
        "run_id": run_id,
        "repository": REPOSITORY,
        "customer_id": customer_id,
        "project_id": project_id,
        "formats": {
            "markdown": "# NICO Full Assessment\n",
            "html": "<h1>NICO Full Assessment</h1>",
            "pdf": base64.b64encode(source_pdf).decode("ascii"),
            "json": {
                "status": "draft",
                "mode": "full",
                "assessment_mode": "full",
                "report_path": "full_run",
                "report_path_label": "Full Assessment",
                "run_id": run_id,
                "report_id": report_id,
                "repository": REPOSITORY,
                "customer_id": customer_id,
                "project_id": project_id,
                "executive_summary": "Exact-run evidence-bound Full Assessment prepared for human review.",
                "maturity_signal": {"level": "Senior", "score": 90},
                "evidence_ledger": {
                    "status": "complete",
                    "run_id": run_id,
                    "entry_count": 9,
                    "verified_entry_count": 8,
                    "unavailable_entry_count": 1,
                },
                "export_truth_gate": {"status": "passed"},
                "client_delivery_verdict": {
                    "status": "human_review_required",
                    "blockers": ["A human reviewer must approve the exact draft before delivery."],
                },
                "sections": [],
                "unavailable_data_notes": ["One optional evidence source was unavailable and received no passing credit."],
                "human_review_required": True,
                "client_ready": False,
            },
        },
        "export_truth_gate": {"status": "passed"},
        "client_delivery_allowed": False,
        "human_review_required": True,
    }


@pytest.fixture(autouse=True)
def isolated_full_delivery_stores(monkeypatch):
    monkeypatch.setattr(access, "_database_url", lambda: "")
    monkeypatch.setattr(receipts, "_database_url", lambda: "")
    monkeypatch.setattr(acknowledgments, "_database_url", lambda: "")
    monkeypatch.delenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", raising=False)
    monkeypatch.setenv("NICO_ADMIN_TOKEN", ADMIN_TOKEN)
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS.clear()
    with receipts._MEMORY_LOCK:
        receipts._MEMORY_RECEIPTS.clear()
    with acknowledgments._MEMORY_LOCK:
        acknowledgments._MEMORY_ACKNOWLEDGMENTS.clear()
    yield
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS.clear()
    with receipts._MEMORY_LOCK:
        receipts._MEMORY_RECEIPTS.clear()
    with acknowledgments._MEMORY_LOCK:
        acknowledgments._MEMORY_ACKNOWLEDGMENTS.clear()


def test_one_full_run_remains_identity_bound_through_review_delivery_receipt_and_acknowledgment():
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = _draft_report(run_id, report_id, customer_id, project_id)
    original_draft = deepcopy(report)
    STORE.put("reports", report_id, report)

    requested = request_final_review(
        {
            "approval_id": approval_id,
            "idempotency_key": f"full-review:{run_id}:{report_id}",
            "run_id": run_id,
            "report_id": report_id,
            "repository": REPOSITORY,
            "customer_id": customer_id,
            "project_id": project_id,
            "requester": "nico-full-run",
            "risk_level": "delivery_review",
            "evidence": [
                f"Exact Full Assessment run_id={run_id}.",
                f"Exact draft report_id={report_id}.",
                "Unavailable evidence remains disclosed and receives no passing credit.",
            ],
        }
    )
    pending = requested["approval"]

    assert requested["status"] == "pending_review"
    assert pending["approval_id"] == approval_id
    assert pending["run_id"] == run_id
    assert pending["report_id"] == report_id
    assert pending["requested_action"] == "final_report_approval"
    assert pending["review_validation"]["ready_for_approval"] is True
    assert pending["status"] == "pending"

    decision = transition_final_review(
        approval_id,
        "approved",
        actor="Senior Technical Reviewer",
        note="Reviewed the exact run, report, evidence ledger, unavailable evidence, score, and delivery boundary.",
    )
    artifact = decision["approved_delivery"]
    stored_report = STORE.get("reports", report_id)

    assert decision["status"] == "ok"
    assert decision["approval"]["status"] == "approved"
    assert decision["approval"]["run_id"] == run_id
    assert decision["approval"]["report_id"] == report_id
    assert artifact["status"] == "complete"
    assert artifact["run_id"] == run_id
    assert artifact["report_id"] == report_id
    assert artifact["approval_id"] == approval_id
    assert artifact["client_delivery_allowed"] is True
    assert len(artifact["approval_identity_sha256"]) == 64
    assert hashlib.sha256(base64.b64decode(artifact["pdf_base64"], validate=True)).hexdigest() == artifact["pdf_sha256"]
    assert stored_report["formats"]["pdf"] == original_draft["formats"]["pdf"]
    assert stored_report["formats"]["json"]["client_ready"] is False
    assert stored_report["approved_delivery"]["pdf_sha256"] == artifact["pdf_sha256"]

    created = access.create_approved_delivery_access(
        {
            "run_id": run_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "recipient_label": "Full E2E Client",
            "created_by": "Senior Technical Reviewer",
            "expires_in_hours": 24,
            "max_downloads": 1,
        },
        admin_token=ADMIN_TOKEN,
    )
    token = created["token"]
    access_id = created["access"]["access_id"]

    assert created["status"] == "created"
    assert created["access"]["run_id"] == run_id
    assert created["access"]["report_id"] == report_id
    assert created["access"]["approval_id"] == approval_id
    assert token.startswith(f"{access_id}.")
    assert token not in repr(access._MEMORY_ACCESS[access_id])

    inspected = access.inspect_approved_delivery_access(token)
    assert inspected["status"] == "available"
    assert inspected["delivery"]["run_id"] == run_id
    assert inspected["delivery"]["report_id"] == report_id
    assert inspected["delivery"]["approval_id"] == approval_id
    assert inspected["delivery"]["pdf_sha256"] == artifact["pdf_sha256"]
    assert "pdf" not in inspected

    delivered = atomic.redeem_approved_delivery_with_receipt(token)
    receipt = delivered["receipt"]

    assert delivered["status"] == "recorded"
    assert delivered["available"] is True
    assert delivered["atomic"] is True
    assert delivered["access"]["run_id"] == run_id
    assert delivered["access"]["report_id"] == report_id
    assert delivered["access"]["approval_id"] == approval_id
    assert delivered["pdf_sha256"] == artifact["pdf_sha256"]
    assert receipt["verified"] is True
    assert receipt["run_id"] == run_id
    assert receipt["report_id"] == report_id
    assert receipt["approval_id"] == approval_id
    assert receipt["pdf_sha256"] == artifact["pdf_sha256"]
    assert receipt["download_number"] == 1
    assert len(receipt["receipt_sha256"]) == 64

    acknowledged = acknowledgments.create_delivery_acknowledgment(
        {
            "token": token,
            "receipt_id": receipt["receipt_id"],
            "acknowledged_by": "Full E2E Client",
            "acknowledged": True,
        }
    )
    acknowledgment = acknowledged["acknowledgment"]

    assert acknowledged["status"] == "acknowledged"
    assert acknowledgment["verified"] is True
    assert acknowledgment["run_id"] == run_id
    assert acknowledgment["report_id"] == report_id
    assert acknowledgment["approval_id"] == approval_id
    assert acknowledgment["receipt_id"] == receipt["receipt_id"]
    assert acknowledgment["receipt_sha256"] == receipt["receipt_sha256"]
    assert acknowledgment["pdf_sha256"] == artifact["pdf_sha256"]
    assert acknowledgment["receipt_only"] is True
    assert acknowledgment["technical_approval"] is False
    assert token not in repr(acknowledged)

    readiness = approved_delivery_operational_readiness(
        run_id,
        customer_id,
        project_id,
        admin_token=ADMIN_TOKEN,
    )
    review = final_review_status(run_id, customer_id, project_id)

    assert readiness["ready"] is True
    assert readiness["lifecycle"] == "acknowledged"
    assert readiness["summary"]["download_count"] == 1
    assert readiness["summary"]["verified_receipt_count"] == 1
    assert review["approval_id"] == approval_id
    assert review["review_status"] == "approved"
    assert review["approved_delivery"]["pdf_sha256"] == artifact["pdf_sha256"]

    repeated_review = request_final_review(
        {
            "approval_id": approval_id,
            "idempotency_key": f"full-review:{run_id}:{report_id}",
            "run_id": run_id,
            "report_id": report_id,
            "customer_id": customer_id,
            "project_id": project_id,
        }
    )
    repeated_decision = transition_final_review(
        approval_id,
        "approved",
        actor="Senior Technical Reviewer",
        note="Repeated operator action.",
    )

    assert repeated_review["idempotent_reuse"] is True
    assert repeated_review["approval"]["approval_id"] == approval_id
    assert repeated_decision["idempotent_reuse"] is True
    assert repeated_decision["approved_delivery"]["pdf_sha256"] == artifact["pdf_sha256"]
    assert len([item for item in STORE.list("reports") if item.get("report_id") == report_id]) == 1
    assert len([item for item in STORE.list("approvals") if item.get("approval_id") == approval_id]) == 1

    audits = STORE.list("audit_log", customer_id=customer_id, project_id=project_id)
    lifecycle_actions = {
        "final_review.requested",
        "final_review.transitioned",
        "approved_delivery.access_created",
        "approved_delivery.redeemed",
        "approved_delivery.receipt_recorded",
        "approved_delivery.acknowledged",
    }
    recorded_actions = {item.get("action") for item in audits if item.get("payload", {}).get("run_id") == run_id}
    assert lifecycle_actions <= recorded_actions
    assert token not in repr(audits)
