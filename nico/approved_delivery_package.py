from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from typing import Any

from nico.admin_security import require_admin_write
from nico.approved_delivery_access import list_approved_delivery_access
from nico.approved_delivery_acknowledgments import list_delivery_acknowledgments
from nico.approved_delivery_receipts import list_delivery_receipts
from nico.approved_delivery_recovery import approved_delivery_status
from nico.approved_delivery_storage_policy import delivery_storage_readiness
from nico.storage import STORE

DELIVERY_PACKAGE_VERSION = "approved-delivery-package-v1"
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "assessment").replace("/", "-"))
    return normalized.strip("-._") or "assessment"


def _decode_pdf(value: Any) -> bytes:
    encoded = str(value or "").strip()
    if not encoded:
        return b""
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception:
        return b""
    return decoded if decoded.startswith(b"%PDF") else b""


def _snapshot_time(delivery: dict[str, Any], access: list[dict[str, Any]], receipts: list[dict[str, Any]], acknowledgments: list[dict[str, Any]]) -> str:
    candidates = [str(delivery.get("approved_at") or "")]
    for item in access:
        candidates.extend([str(item.get("updated_at") or ""), str(item.get("last_redeemed_at") or ""), str(item.get("revoked_at") or "")])
    candidates.extend(str(item.get("delivered_at") or "") for item in receipts)
    candidates.extend(str(item.get("acknowledged_at") or "") for item in acknowledgments)
    return max((item for item in candidates if item), default="not_recorded")


def _approval_export(value: Any) -> dict[str, Any]:
    approval = value if isinstance(value, dict) else {}
    decision = approval.get("review_decision") if isinstance(approval.get("review_decision"), dict) else {}
    approved_delivery = approval.get("approved_delivery") if isinstance(approval.get("approved_delivery"), dict) else {}
    return {
        "approval_id": approval.get("approval_id") or "",
        "status": approval.get("status") or "",
        "requested_action": approval.get("requested_action") or "",
        "run_id": approval.get("run_id") or "",
        "report_id": approval.get("report_id") or "",
        "approver": approval.get("approver") or decision.get("actor") or "",
        "review_decision": {
            "state": decision.get("state") or "",
            "actor": decision.get("actor") or approval.get("approver") or "",
            "note": decision.get("note") or "",
            "decided_at": decision.get("decided_at") or "",
            "client_delivery_allowed": bool(decision.get("client_delivery_allowed")),
        },
        "approved_delivery": {
            "status": approved_delivery.get("status") or "",
            "pdf_filename": approved_delivery.get("pdf_filename") or "",
            "pdf_sha256": approved_delivery.get("pdf_sha256") or "",
            "source_draft_pdf_sha256": approved_delivery.get("source_draft_pdf_sha256") or "",
            "approval_identity_sha256": approved_delivery.get("approval_identity_sha256") or "",
            "client_delivery_allowed": bool(approved_delivery.get("client_delivery_allowed")),
        },
        "rule": "Human technical approval is distinct from secure delivery, delivery receipts, and optional client receipt acknowledgments.",
    }


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[name])
    return buffer.getvalue()


def build_approved_delivery_package(
    run_or_report_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
) -> dict[str, Any]:
    """Build a deterministic, hash-manifested ZIP for one approved Full Assessment."""

    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to export an approved-delivery package.", "admin_write": admin}
    lookup = str(run_or_report_id or "").strip()
    if not lookup:
        return {"status": "blocked", "error": "run_id or report_id is required"}

    storage = delivery_storage_readiness()
    if storage.get("durable_storage_required") and not storage.get("ready"):
        return {
            "status": "blocked",
            "error": "The package cannot be exported because required durable delivery storage is not ready.",
            "storage_readiness": storage,
        }

    recovered = approved_delivery_status(
        lookup,
        customer_id=str(customer_id),
        project_id=str(project_id),
        include_pdf=True,
    )
    if not recovered.get("verified"):
        return {
            "status": "blocked",
            "error": "The approved Full Assessment failed current identity or integrity verification.",
            "verification": recovered.get("verification") or {},
        }
    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    pdf_bytes = _decode_pdf(delivery.get("pdf_base64"))
    if not pdf_bytes or _sha256(pdf_bytes) != str(delivery.get("pdf_sha256") or ""):
        return {"status": "blocked", "error": "The approved PDF failed package-time integrity verification."}

    access_result = list_approved_delivery_access(
        str(recovered.get("run_id") or lookup),
        customer_id=str(customer_id),
        project_id=str(project_id),
        admin_token=admin_token,
    )
    receipt_result = list_delivery_receipts(
        str(recovered.get("run_id") or lookup),
        customer_id=str(customer_id),
        project_id=str(project_id),
        admin_token=admin_token,
    )
    acknowledgment_result = list_delivery_acknowledgments(
        str(recovered.get("run_id") or lookup),
        customer_id=str(customer_id),
        project_id=str(project_id),
        admin_token=admin_token,
    )
    for label, result in (
        ("access grants", access_result),
        ("delivery receipts", receipt_result),
        ("client acknowledgments", acknowledgment_result),
    ):
        if result.get("status") != "ok":
            return {"status": "blocked", "error": f"The {label} ledger could not be loaded for package export."}

    access = access_result.get("access") if isinstance(access_result.get("access"), list) else []
    receipts = receipt_result.get("receipts") if isinstance(receipt_result.get("receipts"), list) else []
    acknowledgments = acknowledgment_result.get("acknowledgments") if isinstance(acknowledgment_result.get("acknowledgments"), list) else []
    invalid_receipts = [str(item.get("receipt_id") or "unknown") for item in receipts if not item.get("verified")]
    invalid_acknowledgments = [str(item.get("acknowledgment_id") or "unknown") for item in acknowledgments if not item.get("verified")]
    if invalid_receipts or invalid_acknowledgments:
        return {
            "status": "blocked",
            "error": "The delivery ledger contains records that failed integrity verification.",
            "invalid_receipts": invalid_receipts,
            "invalid_acknowledgments": invalid_acknowledgments,
        }

    run_id = str(recovered.get("run_id") or "")
    report_id = str(recovered.get("report_id") or "")
    approval_id = str(recovered.get("approval_id") or "")
    snapshot_at = _snapshot_time(delivery, access, receipts, acknowledgments)
    pdf_name = str(delivery.get("pdf_filename") or "nico-full-assessment-approved.pdf")
    files: dict[str, bytes] = {
        pdf_name: pdf_bytes,
        "approval.json": _canonical_json_bytes(_approval_export(recovered.get("approval"))),
        "access-grants.json": _canonical_json_bytes({"status": "ok", "access": access, "rule": "Raw access tokens are never stored or exported."}),
        "delivery-receipts.json": _canonical_json_bytes(receipt_result),
        "client-acknowledgments.json": _canonical_json_bytes(acknowledgment_result),
        "storage-readiness.json": _canonical_json_bytes(storage),
        "README.txt": (
            "NICO APPROVED FULL ASSESSMENT DELIVERY PACKAGE\n\n"
            "This package is bound to one human-approved Full Assessment and includes the approved PDF, approval metadata, secure-access metadata, hash-bound delivery receipts, optional receipt-only client acknowledgments, and a cryptographic file manifest.\n\n"
            "A client acknowledgment confirms receipt only. It is not technical approval, agreement with every finding, a waiver, legal acceptance, or acceptance of liability.\n\n"
            "No raw secure-link token is included. Verify every file against manifest.json before relying on this package.\n"
        ).encode("utf-8"),
    }
    file_hashes = {
        name: {"sha256": _sha256(content), "size_bytes": len(content)}
        for name, content in sorted(files.items())
    }
    identity = {
        "package_version": DELIVERY_PACKAGE_VERSION,
        "run_id": run_id,
        "report_id": report_id,
        "approval_id": approval_id,
        "customer_id": str(customer_id),
        "project_id": str(project_id),
        "snapshot_at": snapshot_at,
        "approved_pdf_sha256": str(delivery.get("pdf_sha256") or ""),
        "source_draft_pdf_sha256": str(delivery.get("source_draft_pdf_sha256") or ""),
        "approval_identity_sha256": str(delivery.get("approval_identity_sha256") or ""),
        "access_grant_count": len(access),
        "delivery_receipt_count": len(receipts),
        "client_acknowledgment_count": len(acknowledgments),
        "files": file_hashes,
    }
    identity_sha256 = _sha256(_canonical_json_bytes(identity))
    manifest = {
        "status": "verified",
        "package_identity": identity,
        "package_identity_sha256": identity_sha256,
        "verification_rule": "Every included file must match its listed SHA-256. The approved PDF hash must also match the independently verified approved-delivery record.",
        "contains_raw_access_tokens": False,
        "client_acknowledgment_is_technical_approval": False,
    }
    manifest_bytes = _canonical_json_bytes(manifest)
    files["manifest.json"] = manifest_bytes
    package_bytes = _zip_bytes(files)
    package_sha256 = _sha256(package_bytes)
    repository = str((recovered.get("approved_delivery") or {}).get("repository") or "assessment")
    filename = f"nico-approved-delivery-{_safe_filename(repository)}-{_safe_filename(run_id)}.zip"

    STORE.audit(
        "approved_delivery.package_exported",
        {
            "package_version": DELIVERY_PACKAGE_VERSION,
            "run_id": run_id,
            "report_id": report_id,
            "approval_id": approval_id,
            "package_sha256": package_sha256,
            "manifest_sha256": _sha256(manifest_bytes),
            "package_identity_sha256": identity_sha256,
            "access_grant_count": len(access),
            "delivery_receipt_count": len(receipts),
            "client_acknowledgment_count": len(acknowledgments),
        },
        customer_id=str(customer_id),
        project_id=str(project_id),
    )
    return {
        "status": "complete",
        "package_version": DELIVERY_PACKAGE_VERSION,
        "run_id": run_id,
        "report_id": report_id,
        "approval_id": approval_id,
        "filename": filename,
        "package_bytes": package_bytes,
        "package_sha256": package_sha256,
        "manifest_sha256": _sha256(manifest_bytes),
        "package_identity_sha256": identity_sha256,
        "file_count": len(files),
        "access_grant_count": len(access),
        "delivery_receipt_count": len(receipts),
        "client_acknowledgment_count": len(acknowledgments),
    }
