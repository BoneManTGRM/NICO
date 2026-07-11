from __future__ import annotations

import base64
from uuid import uuid4

import pytest
from fastapi import HTTPException

from nico import approved_delivery_access as access
from nico import approved_delivery_acknowledgments as acknowledgments
from nico import approved_delivery_receipts as receipts
from nico import full_assessment_api as api
from nico.full_assessment_api import ApprovedDeliveryAcknowledgmentRequest
from nico.full_assessment_delivery import build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_ack_{suffix}",
        f"report_ack_{suffix}",
        f"approval_ack_{suffix}",
        f"customer_ack_{suffix}",
        f"project_ack_{suffix}",
    )


def _approved_records() -> tuple[dict, dict]:
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    source_pdf = b"%PDF-1.4\nack-source\n%%EOF\n"
    report = {
        "status": "complete",
        "report_id": report_id,
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "formats": {
            "pdf": base64.b64encode(source_pdf).decode("ascii"),
            "json": {
                "status": "draft",
                "report_path": "full_run",
                "run_id": run_id,
                "report_id": report_id,
                "customer_id": customer_id,
                "project_id": project_id,
                "repository": "BoneManTGRM/NICO",
                "executive_summary": "Acknowledgment fixture.",
                "maturity_signal": {"level": "Senior", "score": 92},
                "evidence_ledger": {"status": "complete"},
                "client_delivery_verdict": {"status": "human_review_required", "blockers": []},
                "sections": [],
                "unavailable_data_notes": [],
            },
        },
    }
    approved_at = "2026-07-11T20:00:00Z"
    candidate = {
        "approval_id": approval_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "requested_action": "final_report_approval",
        "status": "pending",
        "run_id": run_id,
        "report_id": report_id,
        "approver": "technical_reviewer",
        "review_decision": {
            "state": "approved",
            "actor": "technical_reviewer",
            "note": "Reviewed exact draft.",
            "decided_at": approved_at,
            "client_delivery_allowed": True,
        },
    }
    artifact = build_approved_delivery_artifact(report, candidate, approved_at=approved_at)
    assert artifact["status"] == "complete"
    report["approved_delivery"] = artifact
    report["delivery_status"] = "approved"
    report["client_delivery_allowed"] = True
    approval = {
        **candidate,
        "status": "approved",
        "approved_delivery": {
            "status": artifact["status"],
            "pdf_sha256": artifact["pdf_sha256"],
            "source_draft_pdf_sha256": artifact["source_draft_pdf_sha256"],
            "approval_identity_sha256": artifact["approval_identity_sha256"],
        },
    }
    STORE.put("reports", report_id, report)
    STORE.put("approvals", approval_id, approval)
    return report, approval


@pytest.fixture(autouse=True)
def isolated_delivery_stores(monkeypatch):
    monkeypatch.setattr(access, "_database_url", lambda: "")
    monkeypatch.setattr(receipts, "_database_url", lambda: "")
    monkeypatch.setattr(acknowledgments, "_database_url", lambda: "")
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")
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


def _delivered(report: dict, *, recipient: str = "Example Client") -> tuple[dict, dict, str]:
    created = access.create_approved_delivery_access(
        {
            "run_id": report["run_id"],
            "customer_id": report["customer_id"],
            "project_id": report["project_id"],
            "recipient_label": recipient,
            "created_by": "technical_reviewer",
            "expires_in_hours": 24,
            "max_downloads": 1,
        },
        admin_token="test-admin-token",
    )
    assert created["status"] == "created"
    token = created["token"]
    redeemed = access.redeem_approved_delivery_access(token)
    assert redeemed["status"] == "redeemed"
    redeemed["customer_id"] = report["customer_id"]
    redeemed["project_id"] = report["project_id"]
    receipt_result = receipts.create_delivery_receipt(redeemed)
    assert receipt_result["status"] == "recorded"
    return created, receipt_result["receipt"], token


def test_acknowledgment_requires_explicit_receipt_only_confirmation():
    report, _ = _approved_records()
    _, receipt, token = _delivered(report)

    result = acknowledgments.create_delivery_acknowledgment(
        {"token": token, "receipt_id": receipt["receipt_id"], "acknowledged_by": "Example Client", "acknowledged": False}
    )

    assert result["status"] == "blocked"
    assert "explicitly confirm" in result["error"]
    assert not acknowledgments._MEMORY_ACKNOWLEDGMENTS


def test_verified_acknowledgment_binds_receipt_and_never_stores_raw_token():
    report, _ = _approved_records()
    created, receipt, token = _delivered(report)

    result = acknowledgments.create_delivery_acknowledgment(
        {"token": token, "receipt_id": receipt["receipt_id"], "acknowledged_by": "Example Client", "acknowledged": True}
    )
    acknowledgment = result["acknowledgment"]

    assert result["status"] == "acknowledged"
    assert result["idempotent_reuse"] is False
    assert acknowledgment["verified"] is True
    assert acknowledgment["receipt_id"] == receipt["receipt_id"]
    assert acknowledgment["receipt_sha256"] == receipt["receipt_sha256"]
    assert acknowledgment["access_id"] == created["access"]["access_id"]
    assert acknowledgment["pdf_sha256"] == report["approved_delivery"]["pdf_sha256"]
    assert acknowledgment["receipt_only"] is True
    assert acknowledgment["technical_approval"] is False
    assert acknowledgment["agreement_with_findings"] is False
    assert acknowledgment["legal_acceptance"] is False
    assert len(acknowledgment["acknowledgment_sha256"]) == 64
    assert token not in repr(result)
    assert token not in repr(acknowledgments._MEMORY_ACKNOWLEDGMENTS)


def test_acknowledgment_is_idempotent_for_same_identity_and_immutable_for_different_identity():
    report, _ = _approved_records()
    _, receipt, token = _delivered(report)
    payload = {"token": token, "receipt_id": receipt["receipt_id"], "acknowledged_by": "Example Client", "acknowledged": True}

    first = acknowledgments.create_delivery_acknowledgment(payload)
    repeated = acknowledgments.create_delivery_acknowledgment(payload)
    changed = acknowledgments.create_delivery_acknowledgment({**payload, "acknowledged_by": "Different Person"})

    assert first["status"] == "acknowledged"
    assert repeated["status"] == "acknowledged"
    assert repeated["idempotent_reuse"] is True
    assert repeated["acknowledgment"]["acknowledgment_sha256"] == first["acknowledgment"]["acknowledgment_sha256"]
    assert changed["status"] == "blocked"
    assert "immutable acknowledgment" in changed["error"]
    assert len(acknowledgments._MEMORY_ACKNOWLEDGMENTS) == 1


def test_wrong_delivery_token_cannot_acknowledge_another_receipt():
    report_one, _ = _approved_records()
    report_two, _ = _approved_records()
    _, receipt_one, _ = _delivered(report_one, recipient="Client One")
    _, _, token_two = _delivered(report_two, recipient="Client Two")

    result = acknowledgments.create_delivery_acknowledgment(
        {"token": token_two, "receipt_id": receipt_one["receipt_id"], "acknowledged_by": "Client Two", "acknowledged": True}
    )

    assert result["status"] == "blocked"
    assert "same immutable identity" in result["error"]
    assert not acknowledgments._MEMORY_ACKNOWLEDGMENTS


def test_acknowledgment_tampering_is_detected():
    report, _ = _approved_records()
    _, receipt, token = _delivered(report)
    created = acknowledgments.create_delivery_acknowledgment(
        {"token": token, "receipt_id": receipt["receipt_id"], "acknowledged_by": "Example Client", "acknowledged": True}
    )
    acknowledgment_id = created["acknowledgment"]["acknowledgment_id"]
    stored = acknowledgments._MEMORY_ACKNOWLEDGMENTS[acknowledgment_id]
    stored["identity"]["acknowledged_by"] = "Changed Name"

    verification = acknowledgments.verify_delivery_acknowledgment(stored)

    assert verification["status"] == "blocked"
    assert verification["verified"] is False
    assert verification["computed_acknowledgment_sha256"] != verification["acknowledgment_sha256"]


def test_admin_acknowledgment_ledger_requires_authentication_and_scope():
    report, _ = _approved_records()
    _, receipt, token = _delivered(report)
    acknowledgments.create_delivery_acknowledgment(
        {"token": token, "receipt_id": receipt["receipt_id"], "acknowledged_by": "Example Client", "acknowledged": True}
    )

    blocked = acknowledgments.list_delivery_acknowledgments(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="wrong-token"
    )
    listed = acknowledgments.list_delivery_acknowledgments(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="test-admin-token"
    )
    wrong_scope = acknowledgments.list_delivery_acknowledgments(
        report["run_id"], "wrong-customer", report["project_id"], admin_token="test-admin-token"
    )

    assert blocked["status"] == "blocked"
    assert listed["status"] == "ok"
    assert listed["acknowledgment_count"] == 1
    assert listed["verified_count"] == 1
    assert listed["acknowledgments"][0]["technical_approval"] is False
    assert wrong_scope["acknowledgment_count"] == 0
    assert "raw" not in repr(listed).lower() or "raw access token" not in repr(listed).lower()


def test_public_api_returns_verified_acknowledgment_and_generic_not_found():
    report, _ = _approved_records()
    _, receipt, token = _delivered(report)

    response = api.approved_delivery_acknowledge_response(
        ApprovedDeliveryAcknowledgmentRequest(
            token=token,
            receipt_id=receipt["receipt_id"],
            acknowledged_by="Example Client",
            acknowledged=True,
        )
    )

    assert response["status"] == "acknowledged"
    assert response["acknowledgment"]["verified"] is True

    with pytest.raises(HTTPException) as exc_info:
        api.approved_delivery_acknowledge_response(
            ApprovedDeliveryAcknowledgmentRequest(
                token="invalid-token",
                receipt_id=receipt["receipt_id"],
                acknowledged_by="Example Client",
                acknowledged=True,
            )
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["message"] == "This delivery acknowledgment request is unavailable."
