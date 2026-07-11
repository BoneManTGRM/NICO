from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nico import approved_delivery_access as access
from nico import approved_delivery_acknowledgments as acknowledgments
from nico import approved_delivery_receipts as receipts
from nico.api import hosted
from nico.approved_delivery_operational_readiness import (
    approved_delivery_operational_readiness,
    reconcile_orphaned_delivery_consumptions,
)
from nico.full_assessment_delivery import build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_ready_{suffix}",
        f"report_ready_{suffix}",
        f"approval_ready_{suffix}",
        f"customer_ready_{suffix}",
        f"project_ready_{suffix}",
    )


def _approved_records() -> tuple[dict, dict]:
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    source_pdf = b"%PDF-1.4\nreadiness-source\n%%EOF\n"
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
                "executive_summary": "Readiness fixture.",
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
            "pdf_filename": artifact["pdf_filename"],
            "pdf_sha256": artifact["pdf_sha256"],
            "source_draft_pdf_sha256": artifact["source_draft_pdf_sha256"],
            "approval_identity_sha256": artifact["approval_identity_sha256"],
            "client_delivery_allowed": True,
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
    monkeypatch.delenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", raising=False)
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


def _create_access(report: dict, max_downloads: int = 2) -> dict:
    result = access.create_approved_delivery_access(
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
    assert result["status"] == "created"
    return result


def _deliver(report: dict, created: dict) -> tuple[dict, dict]:
    redeemed = access.redeem_approved_delivery_access(created["token"])
    assert redeemed["status"] == "redeemed"
    redeemed["customer_id"] = report["customer_id"]
    redeemed["project_id"] = report["project_id"]
    receipt_result = receipts.create_delivery_receipt(redeemed)
    assert receipt_result["status"] == "recorded"
    return redeemed, receipt_result["receipt"]


def _ready(report: dict) -> dict:
    return approved_delivery_operational_readiness(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="test-admin-token"
    )


def test_readiness_tracks_approved_shared_delivered_and_acknowledged_lifecycle():
    report, _ = _approved_records()

    approved = _ready(report)
    created = _create_access(report)
    shared = _ready(report)
    _, receipt = _deliver(report, created)
    delivered = _ready(report)
    acknowledgment = acknowledgments.create_delivery_acknowledgment(
        {
            "token": created["token"],
            "receipt_id": receipt["receipt_id"],
            "acknowledged_by": "Example Client",
            "acknowledged": True,
        }
    )
    acknowledged = _ready(report)

    assert approved["ready"] is True and approved["lifecycle"] == "approved"
    assert shared["ready"] is True and shared["lifecycle"] == "shared"
    assert delivered["ready"] is True and delivered["lifecycle"] == "delivered"
    assert acknowledgment["status"] == "acknowledged"
    assert acknowledged["ready"] is True and acknowledged["lifecycle"] == "acknowledged"
    assert acknowledged["summary"]["download_count"] == 1
    assert acknowledged["summary"]["verified_receipt_count"] == 1
    assert acknowledged["summary"]["verified_acknowledgment_count"] == 1
    assert all(item["passed"] for item in acknowledged["checks"])


def test_readiness_blocks_consumed_download_without_verified_receipt():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)
    redeemed = access.redeem_approved_delivery_access(created["token"])
    assert redeemed["status"] == "redeemed"

    readiness = _ready(report)

    assert readiness["status"] == "blocked"
    assert readiness["ready"] is False
    assert readiness["summary"]["download_count"] == 1
    assert readiness["summary"]["verified_receipt_count"] == 0
    assert readiness["summary"]["consumption_mismatch_count"] == 1
    assert readiness["repairable_orphaned_consumptions"][0]["access_id"] == created["access"]["access_id"]
    reconciliation_check = next(item for item in readiness["checks"] if item["id"] == "download_receipt_reconciliation")
    assert reconciliation_check["passed"] is False


def test_reconciliation_repairs_old_orphaned_consumption_with_conditional_write():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)
    redeemed = access.redeem_approved_delivery_access(created["token"])
    assert redeemed["status"] == "redeemed"
    access_id = created["access"]["access_id"]
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS[access_id]["last_redeemed_at"] = old_time
        access._MEMORY_ACCESS[access_id]["updated_at"] = old_time

    result = reconcile_orphaned_delivery_consumptions(
        report["run_id"],
        report["customer_id"],
        report["project_id"],
        admin_token="test-admin-token",
        actor="owner",
        grace_seconds=300,
    )

    assert result["status"] == "reconciled"
    assert result["repaired_count"] == 1
    assert result["skipped_count"] == 0
    assert result["readiness_before"]["ready"] is False
    assert result["readiness_after"]["ready"] is True
    assert result["readiness_after"]["lifecycle"] == "shared"
    with access._MEMORY_LOCK:
        assert access._MEMORY_ACCESS[access_id]["download_count"] == 0
        assert access._MEMORY_ACCESS[access_id]["last_redeemed_at"] == ""


def test_reconciliation_does_not_touch_recent_inflight_consumption():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)
    redeemed = access.redeem_approved_delivery_access(created["token"])
    assert redeemed["status"] == "redeemed"

    result = reconcile_orphaned_delivery_consumptions(
        report["run_id"],
        report["customer_id"],
        report["project_id"],
        admin_token="test-admin-token",
        actor="owner",
        grace_seconds=300,
    )

    assert result["status"] == "blocked"
    assert result["repaired_count"] == 0
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "within_concurrency_grace_window"
    assert result["readiness_after"]["ready"] is False


def test_readiness_blocks_tampered_receipt_and_hosted_repair_refuses_it():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)
    _, receipt = _deliver(report, created)
    with receipts._MEMORY_LOCK:
        receipts._MEMORY_RECEIPTS[receipt["receipt_id"]]["identity"]["recipient_label"] = "Tampered"

    readiness = _ready(report)
    client = TestClient(hosted.app)
    params = {
        "customer_id": report["customer_id"],
        "project_id": report["project_id"],
        "actor": "owner",
        "grace_seconds": "0",
    }
    response = client.post(
        f"/assessment/full-run/{report['run_id']}/approved-delivery/reconcile",
        params=params,
        headers={"X-NICO-Admin-Token": "test-admin-token"},
    )

    assert readiness["ready"] is False
    assert any(item["id"] == "receipt_integrity" and not item["passed"] for item in readiness["checks"])
    assert response.status_code == 409
    assert "non-repairable" in response.json()["detail"]["message"]


def test_hosted_readiness_and_reconciliation_endpoints():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)
    redeemed = access.redeem_approved_delivery_access(created["token"])
    assert redeemed["status"] == "redeemed"
    access_id = created["access"]["access_id"]
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS[access_id]["last_redeemed_at"] = old_time
        access._MEMORY_ACCESS[access_id]["updated_at"] = old_time
    client = TestClient(hosted.app)
    params = {"customer_id": report["customer_id"], "project_id": report["project_id"]}

    before = client.get(
        f"/assessment/full-run/{report['run_id']}/approved-delivery/readiness",
        params=params,
        headers={"X-NICO-Admin-Token": "test-admin-token"},
    )
    repaired = client.post(
        f"/assessment/full-run/{report['run_id']}/approved-delivery/reconcile",
        params={**params, "actor": "owner", "grace_seconds": "300"},
        headers={"X-NICO-Admin-Token": "test-admin-token"},
    )
    after = client.get(
        f"/assessment/full-run/{report['run_id']}/approved-delivery/readiness",
        params=params,
        headers={"X-NICO-Admin-Token": "test-admin-token"},
    )

    assert before.status_code == 200
    assert before.json()["status"] == "blocked"
    assert repaired.status_code == 200
    assert repaired.json()["status"] == "reconciled"
    assert after.status_code == 200
    assert after.json()["ready"] is True
    assert after.json()["summary"]["download_count"] == 0


def test_readiness_requires_admin_authentication_and_exact_scope():
    report, _ = _approved_records()

    blocked = approved_delivery_operational_readiness(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="wrong-token"
    )
    wrong_scope = approved_delivery_operational_readiness(
        report["run_id"], "wrong-customer", report["project_id"], admin_token="test-admin-token"
    )

    assert blocked["status"] == "blocked"
    assert blocked["admin_write"]["configured"] is True
    assert wrong_scope["ready"] is False
    assert any(item["id"] == "approved_artifact" and not item["passed"] for item in wrong_scope["checks"])
