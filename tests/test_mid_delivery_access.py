from __future__ import annotations

import base64
import hashlib
from uuid import uuid4

import pytest
from fastapi import HTTPException

import nico.mid_delivery_access as delivery_store
from nico.mid_delivery_access import (
    create_mid_delivery_access,
    inspect_mid_delivery_access,
    list_mid_delivery_access,
    list_mid_delivery_receipts,
    redeem_mid_delivery_access,
    revoke_mid_delivery_access,
)
from nico.mid_delivery_api import (
    MidDeliveryCreateRequest,
    MidDeliveryInspectRequest,
    MidDeliveryRedeemRequest,
    mid_delivery_create_response,
    mid_delivery_inspect_response,
    mid_delivery_redeem_response,
)
from nico.storage import STORE


ACK = "I acknowledge receipt of this NICO Mid Assessment and the disclosed evidence limitations."


def _run_id() -> str:
    return f"midrun_delivery_{uuid4().hex[:12]}"


def _approved_run(run_id: str) -> dict[str, str]:
    customer_id = "customer_delivery"
    project_id = "project_delivery"
    approval_id = f"mid_approval_{uuid4().hex[:16]}"
    report_id = f"mid_approved_report_{uuid4().hex[:16]}"
    pdf = b"%PDF-1.4\n% NICO approved Mid test artifact\n%%EOF\n"
    pdf_sha = hashlib.sha256(pdf).hexdigest()
    approval_identity_sha = "b" * 64
    review_packet_sha = "c" * 64
    snapshot_sha = "a" * 40
    report = {
        "record_type": "mid_approved_report",
        "status": "complete",
        "approval_status": "approved",
        "report_version": "mid-assessment-approved-v1",
        "report_type": "mid_assessment",
        "report_path": "mid_run",
        "report_id": report_id,
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "repository": "BoneManTGRM/NICO",
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": snapshot_sha,
        "source_draft_report_id": f"mid_report_{uuid4().hex[:16]}",
        "source_draft_pdf_sha256": "d" * 64,
        "review_packet_id": f"mid_review_{uuid4().hex[:16]}",
        "review_packet_sha256": review_packet_sha,
        "approval_id": approval_id,
        "approved_by": "Senior Technical Reviewer",
        "approved_at": "2026-07-11T22:20:00Z",
        "approval_identity_sha256": approval_identity_sha,
        "pdf_sha256": pdf_sha,
        "pdf_filename": f"nico-mid-{run_id}-APPROVED.pdf",
        "formats": {"json": {"approved": True}, "pdf": base64.b64encode(pdf).decode("ascii")},
        "human_review_required": False,
        "approved": True,
        "delivery_eligible": True,
        "client_delivery_allowed": False,
        "unsupported_claims_permitted": 0,
    }
    approval = {
        "record_type": "mid_report_approval",
        "approval_id": approval_id,
        "approval_version": "mid-report-approval-v2",
        "status": "approved",
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": snapshot_sha,
        "review_decision": {"state": "approved", "actor": "Senior Technical Reviewer"},
        "approved_report": {
            "status": "complete",
            "report_id": report_id,
            "pdf_sha256": pdf_sha,
            "approval_identity_sha256": approval_identity_sha,
            "delivery_eligible": True,
            "client_delivery_allowed": False,
        },
    }
    run = {
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "workflow": "mid_assessment",
        "service_tier": "mid",
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": snapshot_sha,
        "approval_id": approval_id,
        "approved_report_id": report_id,
        "request": {"mode": "mid"},
        "response": {"status": "complete"},
    }
    STORE.put("reports", report_id, report)
    STORE.put("approvals", approval_id, approval)
    STORE.put("assessment_runs", run_id, run)
    return {
        "customer_id": customer_id,
        "project_id": project_id,
        "approval_id": approval_id,
        "report_id": report_id,
        "pdf_sha256": pdf_sha,
        "approval_identity_sha256": approval_identity_sha,
        "review_packet_sha256": review_packet_sha,
    }


@pytest.fixture(autouse=True)
def delivery_environment(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("NICO_DISABLE_POSTGRES", "true")


def _create(run_id: str, *, max_downloads: int = 1) -> dict:
    return create_mid_delivery_access(
        {
            "run_id": run_id,
            "customer_id": "customer_delivery",
            "project_id": "project_delivery",
            "recipient_label": "Example Client",
            "created_by": "Technical Reviewer",
            "expires_in_hours": 24,
            "max_downloads": max_downloads,
        },
        admin_token="test-admin-token",
    )


def test_create_requires_admin_exact_scope_and_approved_artifact():
    run_id = _run_id()
    _approved_run(run_id)

    unauthorized = create_mid_delivery_access({"run_id": run_id}, admin_token="wrong")
    wrong_scope = create_mid_delivery_access(
        {
            "run_id": run_id,
            "customer_id": "wrong",
            "project_id": "project_delivery",
            "recipient_label": "Client",
            "created_by": "Reviewer",
        },
        admin_token="test-admin-token",
    )
    missing_recipient = create_mid_delivery_access(
        {
            "run_id": run_id,
            "customer_id": "customer_delivery",
            "project_id": "project_delivery",
            "created_by": "Reviewer",
        },
        admin_token="test-admin-token",
    )

    assert unauthorized["status"] == "blocked"
    assert unauthorized["admin_write"]["configured"] is True
    assert wrong_scope["status"] == "not_found"
    assert missing_recipient["status"] == "blocked"
    assert "recipient" in missing_recipient["error"].lower()


def test_create_returns_raw_token_once_but_stores_and_audits_only_hash_material():
    run_id = _run_id()
    _approved_run(run_id)

    result = _create(run_id)
    token = result["token"]
    access_id = result["access"]["access_id"]
    stored = delivery_store._MEMORY_ACCESS[access_id]
    audits = [item for item in STORE.list("audit_log") if item.get("action") == "mid.delivery_access_created"]

    assert result["status"] == "created"
    assert result["fragment_path"].startswith("/mid-delivery#token=")
    assert token.startswith(f"{access_id}.")
    assert token not in repr(stored)
    assert stored["token_hash"] == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert stored["token_fingerprint"] == stored["token_hash"][:12]
    assert token not in repr(audits)
    assert audits[-1]["payload"]["token_fingerprint"] == stored["token_fingerprint"]


def test_inspect_returns_verified_identity_without_pdf_or_token_echo():
    run_id = _run_id()
    fixture = _approved_run(run_id)
    created = _create(run_id)

    inspected = inspect_mid_delivery_access(created["token"])
    invalid = inspect_mid_delivery_access(created["token"] + "wrong")

    assert inspected["status"] == "available"
    assert inspected["delivery"]["report_id"] == fixture["report_id"]
    assert inspected["delivery"]["pdf_sha256"] == fixture["pdf_sha256"]
    assert inspected["delivery"]["approval_identity_sha256"] == fixture["approval_identity_sha256"]
    assert inspected["delivery"]["review_packet_sha256"] == fixture["review_packet_sha256"]
    assert inspected["delivery"]["acknowledgement_required"] is True
    assert "pdf" not in inspected
    assert created["token"] not in repr(inspected)
    assert invalid == {"status": "not_found", "available": False, "message": "This Mid delivery link is unavailable."}


def test_redeem_requires_named_recipient_and_explicit_acknowledgement():
    run_id = _run_id()
    _approved_run(run_id)
    created = _create(run_id)

    unnamed = redeem_mid_delivery_access(created["token"], "", True, ACK)
    unchecked = redeem_mid_delivery_access(created["token"], "Client Recipient", False, ACK)
    short_ack = redeem_mid_delivery_access(created["token"], "Client Recipient", True, "received")

    assert unnamed["status"] == "blocked"
    assert unchecked["status"] == "blocked"
    assert short_ack["status"] == "blocked"
    assert inspect_mid_delivery_access(created["token"])["access"]["downloads_remaining"] == 1


def test_redeem_returns_exact_pdf_and_creates_integrity_bound_receipt():
    run_id = _run_id()
    fixture = _approved_run(run_id)
    created = _create(run_id, max_downloads=2)

    result = redeem_mid_delivery_access(created["token"], "Client Recipient", True, ACK)
    receipts = list_mid_delivery_receipts(run_id, "customer_delivery", "project_delivery", admin_token="test-admin-token")
    access = list_mid_delivery_access(run_id, "customer_delivery", "project_delivery", admin_token="test-admin-token")

    assert result["status"] == "downloaded"
    assert result["pdf"].startswith(b"%PDF")
    assert hashlib.sha256(result["pdf"]).hexdigest() == fixture["pdf_sha256"]
    assert result["receipt"]["receipt_id"].startswith("mid_receipt_")
    assert len(result["receipt"]["receipt_sha256"]) == 64
    assert result["receipt"]["acknowledgement_sha256"] == hashlib.sha256(ACK.encode("utf-8")).hexdigest()
    assert result["receipt"]["recipient_name"] == "Client Recipient"
    assert result["receipt"]["download_ordinal"] == 1
    assert result["access"]["downloads_remaining"] == 1
    assert receipts["receipts"][0]["receipt_id"] == result["receipt"]["receipt_id"]
    assert access["access"][0]["download_count"] == 1


def test_download_limit_and_expiry_are_enforced_without_extra_receipts():
    run_id = _run_id()
    _approved_run(run_id)
    created = _create(run_id, max_downloads=1)

    first = redeem_mid_delivery_access(created["token"], "Client Recipient", True, ACK)
    second = redeem_mid_delivery_access(created["token"], "Client Recipient", True, ACK)
    receipts = list_mid_delivery_receipts(run_id, "customer_delivery", "project_delivery", admin_token="test-admin-token")

    assert first["status"] == "downloaded"
    assert second["status"] == "not_found"
    assert len(receipts["receipts"]) == 1

    second_run = _run_id()
    _approved_run(second_run)
    expiring = _create(second_run)
    access_id = expiring["access"]["access_id"]
    delivery_store._MEMORY_ACCESS[access_id]["expires_at"] = "2000-01-01T00:00:00Z"
    assert inspect_mid_delivery_access(expiring["token"])["status"] == "not_found"


def test_revocation_is_audited_idempotent_and_blocks_access():
    run_id = _run_id()
    _approved_run(run_id)
    created = _create(run_id)

    revoked = revoke_mid_delivery_access(
        created["access"]["access_id"],
        actor="Technical Reviewer",
        reason="Client requested link cancellation.",
        admin_token="test-admin-token",
    )
    repeated = revoke_mid_delivery_access(
        created["access"]["access_id"],
        actor="Technical Reviewer",
        reason="Client requested link cancellation.",
        admin_token="test-admin-token",
    )

    assert revoked["status"] == "revoked"
    assert revoked["access"]["status"] == "revoked"
    assert repeated["idempotent_reuse"] is True
    assert inspect_mid_delivery_access(created["token"])["status"] == "not_found"
    assert redeem_mid_delivery_access(created["token"], "Client Recipient", True, ACK)["status"] == "not_found"


def test_artifact_tamper_invalidates_existing_link_before_download():
    run_id = _run_id()
    fixture = _approved_run(run_id)
    created = _create(run_id)
    report = STORE.get("reports", fixture["report_id"])
    report["formats"]["pdf"] = base64.b64encode(b"%PDF-tampered").decode("ascii")
    STORE.put("reports", fixture["report_id"], report)

    inspected = inspect_mid_delivery_access(created["token"])
    redeemed = redeem_mid_delivery_access(created["token"], "Client Recipient", True, ACK)

    assert inspected["status"] == "not_found"
    assert redeemed["status"] == "not_found"
    assert list_mid_delivery_receipts(run_id, "customer_delivery", "project_delivery", admin_token="test-admin-token")["receipts"] == []


def test_api_redeem_returns_no_store_pdf_with_receipt_and_identity_headers():
    run_id = _run_id()
    fixture = _approved_run(run_id)
    created = mid_delivery_create_response(
        run_id,
        MidDeliveryCreateRequest(
            customer_id="customer_delivery",
            project_id="project_delivery",
            recipient_label="Example Client",
            created_by="Technical Reviewer",
            max_downloads=2,
        ),
        x_nico_admin_token="test-admin-token",
    )
    inspected = mid_delivery_inspect_response(MidDeliveryInspectRequest(token=created["token"]))
    response = mid_delivery_redeem_response(
        MidDeliveryRedeemRequest(
            token=created["token"],
            recipient_name="Client Recipient",
            acknowledged=True,
            acknowledgement_text=ACK,
        )
    )

    assert inspected["available"] is True
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert response.headers["x-nico-report-id"] == fixture["report_id"]
    assert response.headers["x-nico-pdf-sha256"] == fixture["pdf_sha256"]
    assert response.headers["x-nico-approval-id"] == fixture["approval_id"]
    assert response.headers["x-nico-delivery-access-id"] == created["access"]["access_id"]
    assert response.headers["x-nico-delivery-receipt-id"].startswith("mid_receipt_")
    assert len(response.headers["x-nico-delivery-receipt-sha256"]) == 64
    assert response.headers["cache-control"] == "no-store, private, max-age=0"


def test_api_uses_generic_errors_for_invalid_tokens_and_authentication():
    with pytest.raises(HTTPException) as invalid:
        mid_delivery_inspect_response(MidDeliveryInspectRequest(token="invalid"))
    assert invalid.value.status_code == 404
    assert invalid.value.detail["message"] == "This Mid delivery link is unavailable."

    run_id = _run_id()
    _approved_run(run_id)
    with pytest.raises(HTTPException) as unauthorized:
        mid_delivery_create_response(
            run_id,
            MidDeliveryCreateRequest(recipient_label="Client", created_by="Reviewer"),
            x_nico_admin_token="wrong",
        )
    assert unauthorized.value.status_code == 403
