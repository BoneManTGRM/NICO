from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import approved_delivery_access as access
from nico import approved_delivery_atomic as atomic
from nico import approved_delivery_receipts as receipts
from nico.api import hosted
from nico.approved_delivery_operational_readiness import approved_delivery_operational_readiness
from nico.full_assessment_delivery import build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_atomic_{suffix}",
        f"report_atomic_{suffix}",
        f"approval_atomic_{suffix}",
        f"customer_atomic_{suffix}",
        f"project_atomic_{suffix}",
    )


def _approved_records() -> tuple[dict, dict]:
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    source_pdf = b"%PDF-1.4\natomic-source\n%%EOF\n"
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
                "executive_summary": "Atomic delivery fixture.",
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
    monkeypatch.delenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", raising=False)
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


def _create_access(report: dict, max_downloads: int = 1) -> dict:
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


def _stored_access(created: dict) -> dict:
    access_id = created["access"]["access_id"]
    with access._MEMORY_LOCK:
        return dict(access._MEMORY_ACCESS[access_id])


def test_atomic_delivery_commits_access_count_and_verified_receipt_together():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=2)

    result = atomic.redeem_approved_delivery_with_receipt(created["token"])
    stored = _stored_access(created)

    assert result["status"] == "recorded"
    assert result["available"] is True
    assert result["atomic"] is True
    assert result["pdf_bytes"].startswith(b"%PDF")
    assert result["receipt"]["verified"] is True
    assert result["receipt"]["download_number"] == 1
    assert result["access"]["download_count"] == 1
    assert stored["download_count"] == 1
    assert stored["last_redeemed_at"] == result["receipt"]["delivered_at"]
    assert len(receipts._MEMORY_RECEIPTS) == 1
    assert created["token"] not in repr(receipts._MEMORY_RECEIPTS)

    readiness = approved_delivery_operational_readiness(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="test-admin-token"
    )
    assert readiness["ready"] is True
    assert readiness["summary"]["download_count"] == 1
    assert readiness["summary"]["verified_receipt_count"] == 1
    assert readiness["summary"]["consumption_mismatch_count"] == 0


def test_invalid_token_does_not_change_access_or_receipt_stores():
    report, _ = _approved_records()
    created = _create_access(report)

    result = atomic.redeem_approved_delivery_with_receipt("invalid-token")

    assert result["status"] == "not_found"
    assert _stored_access(created)["download_count"] == 0
    assert not receipts._MEMORY_RECEIPTS


def test_receipt_precommit_verification_failure_does_not_consume_access(monkeypatch):
    report, _ = _approved_records()
    created = _create_access(report)
    monkeypatch.setattr(atomic, "_validate_receipt_record", lambda record: False)

    result = atomic.redeem_approved_delivery_with_receipt(created["token"])

    assert result["status"] == "blocked"
    assert result["available"] is False
    assert "not consumed" in result["error"]
    assert _stored_access(created)["download_count"] == 0
    assert not receipts._MEMORY_RECEIPTS


def test_memory_receipt_write_failure_rolls_back_access_count(monkeypatch):
    report, _ = _approved_records()
    created = _create_access(report)

    class FailingReceiptStore(dict):
        def __setitem__(self, key, value):
            raise RuntimeError("simulated receipt write failure")

    failing_store = FailingReceiptStore()
    monkeypatch.setattr(receipts, "_MEMORY_RECEIPTS", failing_store)

    result = atomic.redeem_approved_delivery_with_receipt(created["token"])

    assert result["status"] == "blocked"
    assert result["available"] is False
    assert _stored_access(created)["download_count"] == 0
    assert not failing_store


def test_concurrent_single_download_allows_exactly_one_receipt():
    report, _ = _approved_records()
    created = _create_access(report, max_downloads=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: atomic.redeem_approved_delivery_with_receipt(created["token"]), range(2)))

    completed = [item for item in results if item.get("status") == "recorded"]
    unavailable = [item for item in results if item.get("status") == "not_found"]
    assert len(completed) == 1
    assert len(unavailable) == 1
    assert _stored_access(created)["download_count"] == 1
    assert len(receipts._MEMORY_RECEIPTS) == 1
    receipt = next(iter(receipts._MEMORY_RECEIPTS.values()))
    assert receipt["identity"]["download_number"] == 1


def test_hosted_redeem_route_returns_atomic_receipt_headers():
    report, _ = _approved_records()
    created = _create_access(report)
    client = TestClient(hosted.app)

    response = client.post("/delivery/approved/redeem", json={"token": created["token"]})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["x-nico-atomic-delivery"] == "true"
    assert len(response.headers["x-nico-receipt-id"]) > 20
    assert len(response.headers["x-nico-receipt-sha256"]) == 64
    assert response.headers["x-nico-download-number"] == "1"
    assert "x-nico-atomic-delivery" in response.headers["access-control-expose-headers"].lower()
    assert _stored_access(created)["download_count"] == 1
    assert len(receipts._MEMORY_RECEIPTS) == 1


def test_hosted_atomic_failure_returns_no_pdf_and_preserves_download(monkeypatch):
    report, _ = _approved_records()
    created = _create_access(report)
    monkeypatch.setattr(atomic, "_validate_receipt_record", lambda record: False)
    client = TestClient(hosted.app)

    response = client.post("/delivery/approved/redeem", json={"token": created["token"]})

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "blocked"
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert _stored_access(created)["download_count"] == 0
    assert not receipts._MEMORY_RECEIPTS


def test_hosted_registration_replaces_legacy_redeem_route_once():
    target = FastAPI()

    hosted.register_hosted_extension_routes(target)
    hosted.register_hosted_extension_routes(target)

    matching = [
        route
        for route in target.routes
        if getattr(route, "path", "") == "/delivery/approved/redeem"
        and "POST" in (getattr(route, "methods", set()) or set())
    ]
    assert len(matching) == 1
    assert matching[0].endpoint is hosted._atomic_approved_delivery_redeem_response
