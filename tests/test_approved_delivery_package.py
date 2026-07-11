from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nico import approved_delivery_access as access
from nico import approved_delivery_acknowledgments as acknowledgments
from nico import approved_delivery_receipts as receipts
from nico.api import hosted
from nico.approved_delivery_package import DELIVERY_PACKAGE_VERSION, build_approved_delivery_package
from nico.full_assessment_delivery import build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_package_{suffix}",
        f"report_package_{suffix}",
        f"approval_package_{suffix}",
        f"customer_package_{suffix}",
        f"project_package_{suffix}",
    )


def _approved_records() -> tuple[dict, dict]:
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    source_pdf = b"%PDF-1.4\npackage-source\n%%EOF\n"
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
                "executive_summary": "Package fixture.",
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


def _delivery_history(report: dict) -> tuple[str, dict, dict]:
    created = access.create_approved_delivery_access(
        {
            "run_id": report["run_id"],
            "customer_id": report["customer_id"],
            "project_id": report["project_id"],
            "recipient_label": "Example Client",
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
    acknowledgment_result = acknowledgments.create_delivery_acknowledgment(
        {
            "token": token,
            "receipt_id": receipt_result["receipt"]["receipt_id"],
            "acknowledged_by": "Example Client",
            "acknowledged": True,
        }
    )
    assert acknowledgment_result["status"] == "acknowledged"
    return token, receipt_result["receipt"], acknowledgment_result["acknowledgment"]


def _zip_files(package_bytes: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(package_bytes), mode="r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_package_contains_verified_pdf_ledgers_disclosures_and_manifest():
    report, approval = _approved_records()
    token, receipt, acknowledgment = _delivery_history(report)

    result = build_approved_delivery_package(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="test-admin-token"
    )
    files = _zip_files(result["package_bytes"])
    manifest = json.loads(files["manifest.json"])

    assert result["status"] == "complete"
    assert result["package_version"] == DELIVERY_PACKAGE_VERSION
    assert result["delivery_receipt_count"] == 1
    assert result["client_acknowledgment_count"] == 1
    assert {
        report["approved_delivery"]["pdf_filename"],
        "approval.json",
        "access-grants.json",
        "delivery-receipts.json",
        "client-acknowledgments.json",
        "storage-readiness.json",
        "README.txt",
        "manifest.json",
    } <= set(files)
    assert files[report["approved_delivery"]["pdf_filename"]].startswith(b"%PDF")
    assert manifest["package_identity"]["approval_id"] == approval["approval_id"]
    assert manifest["package_identity"]["approved_pdf_sha256"] == report["approved_delivery"]["pdf_sha256"]
    assert manifest["contains_raw_access_tokens"] is False
    assert manifest["client_acknowledgment_is_technical_approval"] is False
    for name, evidence in manifest["package_identity"]["files"].items():
        assert hashlib.sha256(files[name]).hexdigest() == evidence["sha256"]
        assert len(files[name]) == evidence["size_bytes"]
    assert token.encode("utf-8") not in result["package_bytes"]
    assert receipt["receipt_id"].encode("utf-8") in files["delivery-receipts.json"]
    assert acknowledgment["acknowledgment_id"].encode("utf-8") in files["client-acknowledgments.json"]


def test_package_is_deterministic_for_unchanged_delivery_state():
    report, _ = _approved_records()
    _delivery_history(report)

    first = build_approved_delivery_package(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="test-admin-token"
    )
    second = build_approved_delivery_package(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="test-admin-token"
    )

    assert first["status"] == "complete"
    assert second["status"] == "complete"
    assert first["package_bytes"] == second["package_bytes"]
    assert first["package_sha256"] == second["package_sha256"]
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert first["package_identity_sha256"] == second["package_identity_sha256"]


def test_package_requires_admin_authentication_and_exact_scope():
    report, _ = _approved_records()

    blocked = build_approved_delivery_package(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="wrong-token"
    )
    wrong_scope = build_approved_delivery_package(
        report["run_id"], "wrong-customer", report["project_id"], admin_token="test-admin-token"
    )

    assert blocked["status"] == "blocked"
    assert blocked["admin_write"]["configured"] is True
    assert wrong_scope["status"] == "blocked"
    assert "failed current identity" in wrong_scope["error"]


def test_package_blocks_tampered_delivery_ledger_record():
    report, _ = _approved_records()
    _, receipt, _ = _delivery_history(report)
    stored = receipts._MEMORY_RECEIPTS[receipt["receipt_id"]]
    stored["identity"]["recipient_label"] = "Tampered Recipient"

    result = build_approved_delivery_package(
        report["run_id"], report["customer_id"], report["project_id"], admin_token="test-admin-token"
    )

    assert result["status"] == "blocked"
    assert receipt["receipt_id"] in result["invalid_receipts"]


def test_hosted_package_endpoint_returns_zip_and_integrity_headers():
    report, _ = _approved_records()
    _delivery_history(report)
    client = TestClient(hosted.app)
    params = {"customer_id": report["customer_id"], "project_id": report["project_id"]}

    response = client.get(
        f"/assessment/full-run/{report['run_id']}/approved-delivery/package",
        params=params,
        headers={"X-NICO-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert response.content.startswith(b"PK")
    assert hashlib.sha256(response.content).hexdigest() == response.headers["x-nico-package-sha256"]
    assert len(response.headers["x-nico-manifest-sha256"]) == 64
    assert len(response.headers["x-nico-package-identity-sha256"]) == 64
    assert response.headers["x-nico-package-version"] == DELIVERY_PACKAGE_VERSION
    assert int(response.headers["x-nico-package-file-count"]) >= 8
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert "x-nico-package-sha256" in response.headers["access-control-expose-headers"].lower()
