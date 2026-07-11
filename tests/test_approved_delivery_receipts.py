from __future__ import annotations

import base64
from uuid import uuid4

import pytest
from fastapi import HTTPException

from nico import approved_delivery_access as access
from nico import approved_delivery_receipts as receipts
from nico import full_assessment_api as api
from nico.full_assessment_api import ApprovedDeliveryTokenRequest
from nico.full_assessment_delivery import build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_receipt_{suffix}",
        f"report_receipt_{suffix}",
        f"approval_receipt_{suffix}",
        f"customer_receipt_{suffix}",
        f"project_receipt_{suffix}",
    )


def _approved_records() -> tuple[dict, dict]:
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    source_pdf = b"%PDF-1.4\nreceipt-source\n%%EOF\n"
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
                "executive_summary": "Receipt fixture.",
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
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS.clear()
    with receipts._MEMORY_LOCK:
        receipts._MEMORY_RECEIPTS.clear()
    yield
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS.clear()
    with receipts._MEMORY_LOCK:
        receipts._MEMORY_RECEIPTS.clear()


def _create_access(report: dict, *, max_downloads: int = 2) -> dict:
    created = access.create_approved_delivery_access(
        {
            "run_id": report["run_id"],
            "customer_id": report["customer_id"],
            "project_id": report["project_id"],
            "recipient_label": "Example Client",
            "created_by": "technical_reviewer",
            "expires_in_hours": 24,
            "max_downloads": max_downloads,
        },
        admin_token="test-admin-token",
    )
    assert created["status"] == "created"
    return created


def _redeemed_with_scope(report: dict, token: str) -> dict:
    redeemed = access.redeem_approved_delivery_access(token)
    assert redeemed["status"] == "redeemed"
    redeemed["customer_id"] = report["customer_id"]
    redeemed["project_id"] = report["project_id"]
    return redeemed


def test_completed_redemption_creates_verified_hash_bound_receipt():
    report, _ = _approved_records()
    created = _create_access(report)
    redeemed = _redeemed_with_scope(report, created["token"])

    result = receipts.create_delivery_receipt(redeemed)
    receipt = result["receipt"]

    assert result["status"] == "recorded"
    assert receipt["verified"] is True
    assert receipt["receipt_version"] == receipts.RECEIPT_VERSION
    assert receipt["access_id"] == created["access"]["access_id"]
    assert receipt["run_id"] == report["run_id"]
    assert receipt["report_id"] == report["report_id"]
    assert receipt["download_number"] == 1
    assert receipt["pdf_sha256"] == report["approved_delivery"]["pdf_sha256"]
    assert len(receipt["receipt_sha256"]) == 64
    assert receipt["persistence"]["adapter"] == "memory"


def test_receipt_never_contains_or_audits_raw_access_token():
    report, _ = _approved_records()
    created = _create_access(report)
    token = created["token"]
    redeemed = _redeemed_with_scope(report, token)

    result = receipts.create_delivery_receipt(redeemed)
    audit_rows = STORE.list("audit_log", customer_id=report["customer_id"], project_id=report["project_id"])
    relevant = [row for row in audit_rows if row.get("action") == "approved_delivery.receipt_created" and row.get("payload", {}).get("receipt_id") == result["receipt"]["receipt_id"]]

    assert token not in repr(result)
    assert token not in repr(receipts._MEMORY_RECEIPTS)
    assert relevant
    assert token not in repr(relevant)
    assert result["receipt"]["token_fingerprint"] == created["access"]["token_fingerprint"]


def test_admin_receipt_ledger_requires_authentication_and_verifies_rows():
    report, _ = _approved_records()
    created = _create_access(report)
    redeemed = _redeemed_with_scope(report, created["token"])
    recorded = receipts.create_delivery_receipt(redeemed)

    blocked = receipts.list_delivery_receipts(
        report["run_id"],
        report["customer_id"],
        report["project_id"],
        admin_token="wrong-token",
    )
    listed = receipts.list_delivery_receipts(
        report["run_id"],
        report["customer_id"],
        report["project_id"],
        admin_token="test-admin-token",
    )

    assert blocked["status"] == "blocked"
    assert listed["status"] == "ok"
    assert listed["receipt_count"] == 1
    assert listed["verified_count"] == 1
    assert listed["receipts"][0]["receipt_id"] == recorded["receipt"]["receipt_id"]
    assert "token_hash" not in repr(listed)


def test_receipt_tampering_is_detected_by_canonical_hash_verification():
    report, _ = _approved_records()
    created = _create_access(report)
    redeemed = _redeemed_with_scope(report, created["token"])
    recorded = receipts.create_delivery_receipt(redeemed)
    receipt_id = recorded["receipt"]["receipt_id"]
    stored = receipts._MEMORY_RECEIPTS[receipt_id]
    stored["identity"]["recipient_label"] = "Changed Recipient"

    verification = receipts.verify_delivery_receipt(stored)
    listed = receipts.list_delivery_receipts(
        report["run_id"],
        report["customer_id"],
        report["project_id"],
        admin_token="test-admin-token",
    )

    assert verification["status"] == "blocked"
    assert verification["verified"] is False
    assert verification["computed_receipt_sha256"] != verification["receipt_sha256"]
    assert listed["verified_count"] == 0
    assert listed["receipts"][0]["verified"] is False


def test_pdf_route_records_receipt_and_exposes_integrity_headers():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)

    response = api.approved_delivery_access_redeem_response(ApprovedDeliveryTokenRequest(token=created["token"]))

    assert response.media_type == "application/pdf"
    assert bytes(response.body).startswith(b"%PDF")
    assert response.headers["x-nico-pdf-sha256"] == report["approved_delivery"]["pdf_sha256"]
    assert response.headers["x-nico-receipt-id"].startswith(receipts.RECEIPT_ID_PREFIX)
    assert len(response.headers["x-nico-receipt-sha256"]) == 64
    assert response.headers["x-nico-receipt-version"] == receipts.RECEIPT_VERSION
    assert response.headers["x-nico-delivered-at"].endswith("Z")
    assert response.headers["x-nico-download-number"] == "1"
    assert response.headers["x-nico-receipt-persistence"] == "memory"
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "x-nico-receipt-id" in exposed
    assert "x-nico-receipt-sha256" in exposed
    assert len(receipts._MEMORY_RECEIPTS) == 1


def test_pdf_route_fails_closed_when_receipt_cannot_be_persisted(monkeypatch):
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)
    monkeypatch.setattr(api, "create_delivery_receipt", lambda redeemed: {"status": "blocked", "error": "receipt storage unavailable"})

    with pytest.raises(HTTPException) as exc_info:
        api.approved_delivery_access_redeem_response(ApprovedDeliveryTokenRequest(token=created["token"]))

    assert exc_info.value.status_code == 503
    assert "receipt could not be persisted" in exc_info.value.detail["message"]


def test_receipt_ledger_is_scoped_to_customer_and_project():
    report, _ = _approved_records()
    created = _create_access(report)
    redeemed = _redeemed_with_scope(report, created["token"])
    receipts.create_delivery_receipt(redeemed)

    wrong_customer = receipts.list_delivery_receipts(
        report["run_id"],
        "wrong-customer",
        report["project_id"],
        admin_token="test-admin-token",
    )
    wrong_project = receipts.list_delivery_receipts(
        report["run_id"],
        report["customer_id"],
        "wrong-project",
        admin_token="test-admin-token",
    )

    assert wrong_customer["receipt_count"] == 0
    assert wrong_project["receipt_count"] == 0
