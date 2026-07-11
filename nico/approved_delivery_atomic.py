from __future__ import annotations

import base64
import hmac
from copy import deepcopy
from typing import Any
from uuid import uuid4

from nico import approved_delivery_access as access_store
from nico import approved_delivery_receipts as receipt_store
from nico.approved_delivery_recovery import approved_delivery_status
from nico.storage import STORE


def _build_receipt_record(
    access: dict[str, Any],
    delivery: dict[str, Any],
    *,
    delivered_at: str,
    download_number: int,
) -> dict[str, Any]:
    receipt_id = f"{receipt_store.RECEIPT_ID_PREFIX}{uuid4().hex[:24]}"
    identity = {
        "receipt_version": receipt_store.RECEIPT_VERSION,
        "receipt_id": receipt_id,
        "access_id": str(access.get("access_id") or ""),
        "run_id": str(access.get("run_id") or ""),
        "report_id": str(access.get("report_id") or ""),
        "approval_id": str(access.get("approval_id") or ""),
        "customer_id": str(access.get("customer_id") or "default_customer"),
        "project_id": str(access.get("project_id") or "default_project"),
        "recipient_label": str(access.get("recipient_label") or "")[:160],
        "delivered_at": delivered_at,
        "download_number": int(download_number),
        "pdf_sha256": str(delivery.get("pdf_sha256") or ""),
        "source_draft_pdf_sha256": str(delivery.get("source_draft_pdf_sha256") or ""),
        "approval_identity_sha256": str(delivery.get("approval_identity_sha256") or ""),
        "token_fingerprint": str(access.get("token_fingerprint") or ""),
    }
    receipt_hash = receipt_store._sha256_json(identity)
    persistence = receipt_store._persistence_status()
    return {
        "record_type": receipt_store.RECEIPT_RECORD_TYPE,
        "receipt_id": receipt_id,
        "status": "delivered",
        "access_id": identity["access_id"],
        "customer_id": identity["customer_id"],
        "project_id": identity["project_id"],
        "run_id": identity["run_id"],
        "report_id": identity["report_id"],
        "approval_id": identity["approval_id"],
        "recipient_label": identity["recipient_label"],
        "delivered_at": delivered_at,
        "receipt_sha256": receipt_hash,
        "identity": identity,
        "persistence": persistence,
        "created_at": delivered_at,
    }


def _validate_receipt_record(record: dict[str, Any]) -> bool:
    verification = receipt_store.verify_delivery_receipt(record)
    return bool(verification.get("verified"))


def _decode_verified_pdf(delivery: dict[str, Any]) -> bytes:
    encoded = str(delivery.get("pdf_base64") or "")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception:
        return b""
    if not decoded.startswith(b"%PDF"):
        return b""
    if access_store.hashlib.sha256(decoded).hexdigest() != str(delivery.get("pdf_sha256") or ""):
        return b""
    return decoded


def _record_matches_token(record: dict[str, Any], supplied_hash: str) -> bool:
    stored_hash = str(record.get("token_hash") or "")
    return bool(
        record.get("record_type") == access_store.ACCESS_RECORD_TYPE
        and stored_hash
        and hmac.compare_digest(stored_hash, supplied_hash)
    )


def _atomic_memory_delivery(
    access_id: str,
    supplied_hash: str,
    recovered: dict[str, Any],
    delivery: dict[str, Any],
    delivered_at: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    with access_store._MEMORY_LOCK:
        with receipt_store._MEMORY_LOCK:
            current = access_store._MEMORY_ACCESS.get(access_id)
            if not isinstance(current, dict):
                return None
            if not _record_matches_token(current, supplied_hash):
                return None
            if not access_store._record_active(current):
                return None
            if not access_store._artifact_matches(current, recovered):
                return None

            next_count = int(current.get("download_count") or 0) + 1
            receipt = _build_receipt_record(
                current,
                delivery,
                delivered_at=delivered_at,
                download_number=next_count,
            )
            if not _validate_receipt_record(receipt):
                raise RuntimeError("delivery receipt failed pre-commit verification")
            if receipt["receipt_id"] in receipt_store._MEMORY_RECEIPTS:
                raise RuntimeError("delivery receipt identity collision")

            updated = deepcopy(current)
            updated["download_count"] = next_count
            updated["last_redeemed_at"] = delivered_at
            updated["updated_at"] = delivered_at

            previous = deepcopy(current)
            try:
                access_store._MEMORY_ACCESS[access_id] = deepcopy(updated)
                receipt_store._MEMORY_RECEIPTS[receipt["receipt_id"]] = deepcopy(receipt)
            except Exception:
                access_store._MEMORY_ACCESS[access_id] = previous
                receipt_store._MEMORY_RECEIPTS.pop(receipt["receipt_id"], None)
                raise
            return deepcopy(updated), deepcopy(receipt)


def _atomic_postgres_delivery(
    access_id: str,
    supplied_hash: str,
    recovered: dict[str, Any],
    delivery: dict[str, Any],
    delivered_at: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    from psycopg.types.json import Jsonb

    access_store._ensure_schema()
    receipt_store._ensure_schema()
    with access_store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM approved_delivery_access WHERE access_id=%s AND token_hash=%s FOR UPDATE",
                (access_id, supplied_hash),
            )
            row = cur.fetchone()
            if not row:
                return None
            current = access_store._row_record(dict(row))
            if not _record_matches_token(current, supplied_hash):
                return None
            if not access_store._record_active(current):
                return None
            if not access_store._artifact_matches(current, recovered):
                return None

            next_count = int(current.get("download_count") or 0) + 1
            receipt = _build_receipt_record(
                current,
                delivery,
                delivered_at=delivered_at,
                download_number=next_count,
            )
            if not _validate_receipt_record(receipt):
                raise RuntimeError("delivery receipt failed pre-commit verification")

            updated_payload = deepcopy(current)
            updated_payload["download_count"] = next_count
            updated_payload["last_redeemed_at"] = delivered_at
            updated_payload["updated_at"] = delivered_at
            cur.execute(
                """
                UPDATE approved_delivery_access
                SET download_count=%s,
                    updated_at=%s,
                    payload=%s
                WHERE access_id=%s
                  AND token_hash=%s
                  AND status='active'
                  AND expires_at > %s
                  AND download_count=%s
                RETURNING *
                """,
                (
                    next_count,
                    delivered_at,
                    Jsonb(updated_payload),
                    access_id,
                    supplied_hash,
                    delivered_at,
                    next_count - 1,
                ),
            )
            updated_row = cur.fetchone()
            if not updated_row:
                raise RuntimeError("access grant changed during atomic delivery")

            cur.execute(
                """
                INSERT INTO approved_delivery_receipts
                  (receipt_id, access_id, customer_id, project_id, run_id, report_id, approval_id, recipient_label, delivered_at, receipt_sha256, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    receipt["receipt_id"],
                    receipt["access_id"],
                    receipt["customer_id"],
                    receipt["project_id"],
                    receipt["run_id"],
                    receipt["report_id"],
                    receipt["approval_id"],
                    receipt["recipient_label"],
                    receipt["delivered_at"],
                    receipt["receipt_sha256"],
                    Jsonb(receipt),
                    receipt["created_at"],
                ),
            )
        conn.commit()
    return access_store._row_record(dict(updated_row)), receipt


def redeem_approved_delivery_with_receipt(token: Any) -> dict[str, Any]:
    """Consume one download and persist its receipt as one atomic operation."""

    parsed = access_store._parse_token(token)
    if not parsed:
        return access_store._unavailable()
    access_id, supplied_hash = parsed
    record = access_store._get_record(access_id)
    if not isinstance(record, dict) or not _record_matches_token(record, supplied_hash):
        return access_store._unavailable()
    if not access_store._record_active(record):
        return access_store._unavailable()

    recovered = approved_delivery_status(
        str(record.get("run_id") or ""),
        customer_id=str(record.get("customer_id") or "default_customer"),
        project_id=str(record.get("project_id") or "default_project"),
        include_pdf=True,
    )
    if not access_store._artifact_matches(record, recovered):
        STORE.audit(
            "approved_delivery.access_verification_blocked",
            {"access_id": access_id, "reason": "artifact_identity_mismatch"},
            customer_id=record.get("customer_id"),
            project_id=record.get("project_id"),
        )
        return access_store._unavailable()

    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    pdf_bytes = _decode_verified_pdf(delivery)
    if not pdf_bytes:
        return access_store._unavailable()

    delivered_at = access_store._iso(access_store._now())
    try:
        if access_store._postgres_available() and receipt_store._postgres_available():
            committed = _atomic_postgres_delivery(
                access_id,
                supplied_hash,
                recovered,
                delivery,
                delivered_at,
            )
        elif not access_store._database_url() and not receipt_store._database_url():
            committed = _atomic_memory_delivery(
                access_id,
                supplied_hash,
                recovered,
                delivery,
                delivered_at,
            )
        else:
            return {
                "status": "blocked",
                "available": False,
                "error": "Atomic delivery storage is unavailable; the access grant was not consumed.",
            }
    except Exception:
        return {
            "status": "blocked",
            "available": False,
            "error": "Atomic delivery could not be committed; the access grant was not consumed.",
        }
    if not committed:
        return access_store._unavailable()

    consumed, receipt = committed
    verification = receipt_store.verify_delivery_receipt(receipt)
    if not verification.get("verified"):
        return {
            "status": "blocked",
            "available": False,
            "error": "The committed delivery receipt failed integrity verification.",
            "verification": verification,
        }

    try:
        STORE.audit(
            "approved_delivery.access_redeemed",
            {
                "access_id": consumed.get("access_id"),
                "run_id": consumed.get("run_id"),
                "report_id": consumed.get("report_id"),
                "download_count": consumed.get("download_count"),
                "max_downloads": consumed.get("max_downloads"),
                "token_fingerprint": consumed.get("token_fingerprint"),
                "atomic_receipt": True,
            },
            customer_id=consumed.get("customer_id"),
            project_id=consumed.get("project_id"),
        )
        STORE.audit(
            "approved_delivery.receipt_created",
            {
                "receipt_id": receipt.get("receipt_id"),
                "receipt_sha256": receipt.get("receipt_sha256"),
                "access_id": receipt.get("access_id"),
                "run_id": receipt.get("run_id"),
                "report_id": receipt.get("report_id"),
                "approval_id": receipt.get("approval_id"),
                "download_number": (receipt.get("identity") or {}).get("download_number"),
                "pdf_sha256": (receipt.get("identity") or {}).get("pdf_sha256"),
                "token_fingerprint": (receipt.get("identity") or {}).get("token_fingerprint"),
                "persistence_adapter": (receipt.get("persistence") or {}).get("adapter"),
                "atomic_access_consumption": True,
            },
            customer_id=receipt.get("customer_id"),
            project_id=receipt.get("project_id"),
        )
    except Exception:
        pass

    return {
        "status": "recorded",
        "available": True,
        "pdf_bytes": pdf_bytes,
        "pdf_filename": delivery.get("pdf_filename") or "nico-full-assessment-approved.pdf",
        "pdf_sha256": delivery.get("pdf_sha256") or "",
        "access": access_store._public_record(consumed),
        "receipt": receipt_store._public_receipt(receipt),
        "atomic": True,
    }
