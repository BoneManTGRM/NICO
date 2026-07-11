from __future__ import annotations

import base64
from datetime import timedelta
from uuid import uuid4

import pytest

from nico import approved_delivery_access as access
from nico.full_assessment_api import ApprovedDeliveryTokenRequest, approved_delivery_access_redeem_response
from nico.full_assessment_delivery import build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_access_{suffix}",
        f"report_access_{suffix}",
        f"approval_access_{suffix}",
        f"customer_access_{suffix}",
        f"project_access_{suffix}",
    )


def _source_pdf() -> bytes:
    return b"%PDF-1.4\nsecure-access-source\n%%EOF\n"


def _approved_records() -> tuple[dict, dict]:
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = {
        "status": "complete",
        "report_id": report_id,
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "formats": {
            "pdf": base64.b64encode(_source_pdf()).decode("ascii"),
            "json": {
                "status": "draft",
                "report_path": "full_run",
                "run_id": run_id,
                "report_id": report_id,
                "customer_id": customer_id,
                "project_id": project_id,
                "repository": "BoneManTGRM/NICO",
                "executive_summary": "Secure access fixture.",
                "maturity_signal": {"level": "Senior", "score": 92},
                "evidence_ledger": {"status": "complete"},
                "client_delivery_verdict": {"status": "human_review_required", "blockers": []},
                "sections": [],
                "unavailable_data_notes": [],
            },
        },
    }
    approved_at = "2026-07-11T19:00:00Z"
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
def isolated_access_store(monkeypatch):
    monkeypatch.setattr(access, "_database_url", lambda: "")
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS.clear()
    yield
    with access._MEMORY_LOCK:
        access._MEMORY_ACCESS.clear()


def _create(report: dict, **overrides) -> dict:
    payload = {
        "run_id": report["run_id"],
        "customer_id": report["customer_id"],
        "project_id": report["project_id"],
        "recipient_label": "Example Client",
        "created_by": "technical_reviewer",
        "expires_in_hours": 24,
        "max_downloads": 1,
        **overrides,
    }
    result = access.create_approved_delivery_access(payload, admin_token="test-admin-token")
    assert result["status"] == "created"
    return result


def test_access_creation_requires_admin_authentication():
    report, _ = _approved_records()

    result = access.create_approved_delivery_access(
        {"run_id": report["run_id"], "customer_id": report["customer_id"], "project_id": report["project_id"]},
        admin_token="wrong-token",
    )

    assert result["status"] == "blocked"
    assert "Admin authentication" in result["error"]
    assert access._MEMORY_ACCESS == {}


def test_raw_token_is_returned_once_but_never_stored_or_audited():
    report, _ = _approved_records()

    created = _create(report)
    token = created["token"]
    record = access._MEMORY_ACCESS[created["access"]["access_id"]]
    audit_rows = STORE.list("audit_log", customer_id=report["customer_id"], project_id=report["project_id"])
    relevant = [row for row in audit_rows if row.get("action") == "approved_delivery.access_created" and row.get("payload", {}).get("access_id") == record["access_id"]]

    assert token.startswith(record["access_id"] + ".")
    assert token not in repr(record)
    assert record["token_hash"] == access._sha256_text(token)
    assert created["fragment_path"].startswith("/delivery#token=")
    assert relevant
    assert token not in repr(relevant)


def test_valid_link_can_be_inspected_and_redeemed_once():
    report, _ = _approved_records()
    created = _create(report, max_downloads=1)

    inspected = access.inspect_approved_delivery_access(created["token"])
    redeemed = access.redeem_approved_delivery_access(created["token"])
    repeated = access.redeem_approved_delivery_access(created["token"])

    assert inspected["status"] == "available"
    assert inspected["delivery"]["pdf_sha256"] == report["approved_delivery"]["pdf_sha256"]
    assert redeemed["status"] == "redeemed"
    assert redeemed["pdf_bytes"].startswith(b"%PDF")
    assert redeemed["access"]["download_count"] == 1
    assert redeemed["access"]["downloads_remaining"] == 0
    assert repeated["status"] == "not_found"
    assert repeated["message"] == "This approved-delivery link is unavailable."


def test_wrong_token_returns_same_generic_public_failure():
    report, _ = _approved_records()
    created = _create(report)
    access_id = created["access"]["access_id"]

    wrong = access.inspect_approved_delivery_access(f"{access_id}.{'x' * 48}")
    malformed = access.inspect_approved_delivery_access("not-a-token")

    assert wrong == malformed == {
        "status": "not_found",
        "available": False,
        "message": "This approved-delivery link is unavailable.",
    }


def test_expired_link_never_returns_pdf():
    report, _ = _approved_records()
    created = _create(report)
    record = access._MEMORY_ACCESS[created["access"]["access_id"]]
    record["expires_at"] = access._iso(access._now() - timedelta(seconds=1))

    inspected = access.inspect_approved_delivery_access(created["token"])
    redeemed = access.redeem_approved_delivery_access(created["token"])

    assert inspected["status"] == "not_found"
    assert redeemed["status"] == "not_found"
    assert "pdf_bytes" not in redeemed
    assert record["download_count"] == 0


def test_revoked_link_never_returns_pdf():
    report, _ = _approved_records()
    created = _create(report, max_downloads=3)

    revoked = access.revoke_approved_delivery_access(created["access"]["access_id"], admin_token="test-admin-token", actor="security_admin")
    redeemed = access.redeem_approved_delivery_access(created["token"])

    assert revoked["status"] == "revoked"
    assert revoked["access"]["status"] == "revoked"
    assert redeemed["status"] == "not_found"


def test_tampered_artifact_blocks_redemption_without_consuming_download():
    report, _ = _approved_records()
    created = _create(report, max_downloads=2)
    stored_report = STORE.get("reports", report["report_id"])
    assert stored_report is not None
    stored_report["approved_delivery"]["pdf_base64"] = base64.b64encode(b"%PDF-1.4\ntampered\n%%EOF\n").decode("ascii")
    STORE.put("reports", report["report_id"], stored_report)

    redeemed = access.redeem_approved_delivery_access(created["token"])
    record = access._MEMORY_ACCESS[created["access"]["access_id"]]

    assert redeemed["status"] == "not_found"
    assert "pdf_bytes" not in redeemed
    assert record["download_count"] == 0


def test_download_limit_is_consumed_sequentially_and_never_exceeded():
    report, _ = _approved_records()
    created = _create(report, max_downloads=2)

    first = access.redeem_approved_delivery_access(created["token"])
    second = access.redeem_approved_delivery_access(created["token"])
    third = access.redeem_approved_delivery_access(created["token"])

    assert first["status"] == "redeemed"
    assert second["status"] == "redeemed"
    assert second["access"]["download_count"] == 2
    assert third["status"] == "not_found"
    assert access._MEMORY_ACCESS[created["access"]["access_id"]]["download_count"] == 2


def test_admin_list_omits_token_hash_and_raw_token():
    report, _ = _approved_records()
    created = _create(report)

    listed = access.list_approved_delivery_access(
        report["run_id"],
        customer_id=report["customer_id"],
        project_id=report["project_id"],
        admin_token="test-admin-token",
    )

    assert listed["status"] == "ok"
    assert listed["access"][0]["access_id"] == created["access"]["access_id"]
    assert "token_hash" not in listed["access"][0]
    assert created["token"] not in repr(listed)


def test_pdf_route_response_sets_no_store_and_security_headers():
    report, _ = _approved_records()
    created = _create(report)

    response = approved_delivery_access_redeem_response(ApprovedDeliveryTokenRequest(token=created["token"]))

    assert response.media_type == "application/pdf"
    assert bytes(response.body).startswith(b"%PDF")
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-nico-pdf-sha256"] == report["approved_delivery"]["pdf_sha256"]
