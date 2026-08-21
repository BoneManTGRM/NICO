from __future__ import annotations

import pytest

from nico import approved_delivery_access as access
from nico import approved_delivery_receipts as receipts
from nico import approved_delivery_recovery as recovery


def test_approved_delivery_recovery_requires_explicit_tenant_scope(monkeypatch):
    def unexpected_lookup(_: str):
        raise AssertionError("report lookup must not occur without explicit tenant scope")

    monkeypatch.setattr(recovery, "get_report", unexpected_lookup)

    result = recovery.approved_delivery_status("fullrun_missing_scope")

    assert result["status"] == "blocked"
    assert result["verified"] is False
    assert result["client_delivery_allowed"] is False
    assert result["human_review_required"] is True
    assert result["client_ready"] is False
    assert "customer_id and project_id are required" in result["error"]


@pytest.mark.parametrize(
    ("customer_id", "project_id"),
    [
        ("", "project-real"),
        ("customer-real", ""),
        ("default_customer", "project-real"),
        ("customer-real", "default_project"),
    ],
)
def test_approved_delivery_recovery_rejects_missing_or_placeholder_scope(
    monkeypatch,
    customer_id: str,
    project_id: str,
):
    def unexpected_lookup(_: str):
        raise AssertionError("report lookup must not occur with incomplete tenant scope")

    monkeypatch.setattr(recovery, "get_report", unexpected_lookup)

    result = recovery.approved_delivery_status(
        "fullrun_invalid_scope",
        customer_id=customer_id,
        project_id=project_id,
    )

    assert result["status"] == "blocked"
    assert result["verified"] is False
    assert result["client_delivery_allowed"] is False


def test_approved_delivery_recovery_rejects_stored_report_without_tenant_identity(monkeypatch):
    monkeypatch.setattr(
        recovery,
        "get_report",
        lambda _: {
            "status": "complete",
            "run_id": "fullrun_unscoped_report",
            "report_id": "report_unscoped_report",
        },
    )

    result = recovery.approved_delivery_status(
        "fullrun_unscoped_report",
        customer_id="customer-real",
        project_id="project-real",
    )

    assert result["status"] == "blocked"
    assert result["verified"] is False
    assert result["client_delivery_allowed"] is False
    assert "stored report package is missing mandatory" in result["error"]


def test_failed_recovery_clears_stale_delivery_truth():
    result = {
        "status": "complete",
        "run_id": "fullrun_stale_delivery",
        "client_ready": True,
        "client_delivery_allowed": True,
        "human_review_required": False,
        "client_delivery_status": "Approved for Client Delivery",
        "delivery_verdict": "approved",
        "approved_delivery": {"pdf_base64": "stale"},
        "reports": {
            "client_delivery_allowed": True,
            "human_review_required": False,
            "approved_delivery": {"pdf_base64": "stale"},
        },
    }

    attached = recovery.attach_verified_approved_delivery(result)

    assert attached["approved_delivery_recovery"]["status"] == "blocked"
    assert attached["approved_delivery_recovery"]["verified"] is False
    assert attached["client_ready"] is False
    assert attached["client_delivery_allowed"] is False
    assert attached["human_review_required"] is True
    assert attached["client_delivery_status"] == "Client Delivery Blocked"
    assert attached["delivery_verdict"] == "blocked"
    assert "approved_delivery" not in attached
    assert attached["reports"]["client_delivery_allowed"] is False
    assert attached["reports"]["human_review_required"] is True
    assert "approved_delivery" not in attached["reports"]


def test_failed_recovery_without_run_identity_clears_stale_delivery_truth():
    result = {
        "status": "complete",
        "customer_id": "customer-real",
        "project_id": "project-real",
        "client_ready": True,
        "client_delivery_allowed": True,
        "human_review_required": False,
        "delivery_verdict": "approved",
        "approved_delivery": {"pdf_base64": "stale"},
        "reports": {
            "client_delivery_allowed": True,
            "human_review_required": False,
            "approved_delivery": {"pdf_base64": "stale"},
        },
    }

    attached = recovery.attach_verified_approved_delivery(result)

    assert attached["approved_delivery_recovery"]["status"] == "blocked"
    assert attached["approved_delivery_recovery"]["verified"] is False
    assert attached["client_ready"] is False
    assert attached["client_delivery_allowed"] is False
    assert attached["human_review_required"] is True
    assert attached["delivery_verdict"] == "blocked"
    assert "approved_delivery" not in attached
    assert attached["reports"]["client_delivery_allowed"] is False
    assert "approved_delivery" not in attached["reports"]


def test_access_creation_cannot_substitute_default_tenant_identity(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "phase4-admin-token")
    monkeypatch.setattr(access, "_database_url", lambda: "")
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS.clear()

    result = access.create_approved_delivery_access(
        {"run_id": "fullrun_missing_scope"},
        admin_token="phase4-admin-token",
    )

    assert result["status"] == "blocked"
    assert "currently verified approved artifact" in result["error"]
    with access._MEMORY_LOCK:
        assert access._MEMORY_ACCESS == {}


def test_receipt_creation_cannot_substitute_default_tenant_identity(monkeypatch):
    monkeypatch.setattr(receipts, "_database_url", lambda: "")
    with receipts._MEMORY_LOCK:
        receipts._MEMORY_RECEIPTS.clear()

    result = receipts.create_delivery_receipt(
        {
            "status": "redeemed",
            "available": True,
            "access": {
                "access_id": "delivery_access_missing_scope",
                "run_id": "fullrun_missing_scope",
                "report_id": "report_missing_scope",
                "approval_id": "approval_missing_scope",
                "last_redeemed_at": "2026-08-21T17:00:00Z",
                "download_count": 1,
                "token_fingerprint": "fingerprint",
            },
        }
    )

    assert result["status"] == "blocked"
    assert "no longer passes approved-delivery verification" in result["error"]
    with receipts._MEMORY_LOCK:
        assert receipts._MEMORY_RECEIPTS == {}
