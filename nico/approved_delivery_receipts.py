from __future__ import annotations

import hashlib
import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.admin_security import require_admin_write
from nico.approved_delivery_recovery import approved_delivery_status
from nico.storage import STORE

RECEIPT_RECORD_TYPE = "approved_delivery_receipt"
RECEIPT_VERSION = "approved-delivery-receipt-v1"
RECEIPT_ID_PREFIX = "delivery_receipt_"

_RECEIPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_delivery_receipts (
  receipt_id TEXT PRIMARY KEY,
  access_id TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  approval_id TEXT NOT NULL,
  recipient_label TEXT,
  delivered_at TIMESTAMPTZ NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approved_delivery_receipts_scope
  ON approved_delivery_receipts (customer_id, project_id, run_id, delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_approved_delivery_receipts_access
  ON approved_delivery_receipts (access_id, delivered_at DESC);
"""

_MEMORY_LOCK = threading.RLock()
_MEMORY_RECEIPTS: dict[str, dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _database_url() -> str:
    if os.getenv("NICO_DISABLE_POSTGRES", "false").lower() == "true":
        return ""
    return os.getenv("DATABASE_URL", "").strip()


def _connect() -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_database_url(), row_factory=dict_row)


def _ensure_schema() -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_RECEIPT_SCHEMA)
        conn.commit()


def _postgres_available() -> bool:
    if not _database_url():
        return False
    try:
        _ensure_schema()
        return True
    except Exception:
        return False


def _persistence_status() -> dict[str, Any]:
    durable = _postgres_available()
    return {
        "durable": durable,
        "adapter": "postgres" if durable else "memory",
        "note": (
            "Approved-delivery receipts are durable."
            if durable
            else "Approved-delivery receipts use process memory and may disappear after restart because durable Postgres receipt storage is unavailable."
        ),
    }


def _sha256_json(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _row_record(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("payload") or {})
    payload.update(
        {
            "receipt_id": row.get("receipt_id"),
            "access_id": row.get("access_id"),
            "customer_id": row.get("customer_id"),
            "project_id": row.get("project_id"),
            "run_id": row.get("run_id"),
            "report_id": row.get("report_id"),
            "approval_id": row.get("approval_id"),
            "recipient_label": row.get("recipient_label") or "",
            "delivered_at": _iso(row.get("delivered_at")) if isinstance(row.get("delivered_at"), datetime) else str(row.get("delivered_at") or ""),
            "receipt_sha256": row.get("receipt_sha256") or "",
            "created_at": _iso(row.get("created_at")) if isinstance(row.get("created_at"), datetime) else str(row.get("created_at") or ""),
        }
    )
    return payload


def _put_record(record: dict[str, Any]) -> dict[str, Any]:
    if _postgres_available():
        from psycopg.types.json import Jsonb

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO approved_delivery_receipts
                      (receipt_id, access_id, customer_id, project_id, run_id, report_id, approval_id, recipient_label, delivered_at, receipt_sha256, payload, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (receipt_id) DO NOTHING
                    RETURNING *
                    """,
                    (
                        record["receipt_id"],
                        record["access_id"],
                        record["customer_id"],
                        record["project_id"],
                        record["run_id"],
                        record["report_id"],
                        record["approval_id"],
                        record["recipient_label"],
                        record["delivered_at"],
                        record["receipt_sha256"],
                        Jsonb(record),
                        record["created_at"],
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row:
            return _row_record(dict(row))
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM approved_delivery_receipts WHERE receipt_id=%s", (record["receipt_id"],))
                existing = cur.fetchone()
        return _row_record(dict(existing)) if existing else {}

    with _MEMORY_LOCK:
        existing = _MEMORY_RECEIPTS.get(record["receipt_id"])
        if existing:
            return deepcopy(existing)
        _MEMORY_RECEIPTS[record["receipt_id"]] = deepcopy(record)
        return deepcopy(record)


def _list_records(run_or_report_id: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM approved_delivery_receipts
                    WHERE (run_id=%s OR report_id=%s)
                      AND customer_id=%s AND project_id=%s
                    ORDER BY delivered_at DESC
                    """,
                    (run_or_report_id, run_or_report_id, customer_id, project_id),
                )
                rows = list(cur.fetchall())
        return [_row_record(dict(row)) for row in rows]

    with _MEMORY_LOCK:
        rows = [
            deepcopy(item)
            for item in _MEMORY_RECEIPTS.values()
            if (item.get("run_id") == run_or_report_id or item.get("report_id") == run_or_report_id)
            and item.get("customer_id") == customer_id
            and item.get("project_id") == project_id
        ]
    rows.sort(key=lambda item: str(item.get("delivered_at") or ""), reverse=True)
    return rows


def verify_delivery_receipt(receipt: Any) -> dict[str, Any]:
    value = receipt if isinstance(receipt, dict) else {}
    identity = value.get("identity") if isinstance(value.get("identity"), dict) else {}
    computed = _sha256_json(identity) if identity else ""
    checks = [
        {"id": "receipt_exists", "passed": bool(value), "message": "The delivery receipt exists."},
        {"id": "record_type", "passed": value.get("record_type") == RECEIPT_RECORD_TYPE, "message": "The record is an approved-delivery receipt."},
        {"id": "receipt_version", "passed": identity.get("receipt_version") == RECEIPT_VERSION, "message": "The receipt uses the supported version."},
        {"id": "delivery_status", "passed": value.get("status") == "delivered", "message": "The receipt records a completed delivery."},
        {"id": "identity_complete", "passed": bool(identity) and all(str(identity.get(key) or "") for key in ("receipt_id", "access_id", "run_id", "report_id", "approval_id", "customer_id", "project_id", "delivered_at", "pdf_sha256", "source_draft_pdf_sha256", "approval_identity_sha256", "token_fingerprint")), "message": "The receipt identity contains every required binding."},
        {"id": "receipt_id_binding", "passed": bool(identity) and identity.get("receipt_id") == value.get("receipt_id"), "message": "The identity is bound to the exact receipt ID."},
        {"id": "receipt_hash", "passed": bool(computed) and computed == value.get("receipt_sha256"), "message": "The receipt SHA-256 matches the canonical identity."},
    ]
    blockers = [item["message"] for item in checks if not item["passed"]]
    return {
        "status": "verified" if not blockers else "blocked",
        "verified": not blockers,
        "receipt_id": value.get("receipt_id") or "",
        "receipt_sha256": value.get("receipt_sha256") or "",
        "computed_receipt_sha256": computed,
        "checks": checks,
        "blockers": blockers,
        "rule": "A delivery receipt is valid only when its complete canonical identity recomputes to the stored SHA-256.",
    }


def _public_receipt(receipt: Any) -> dict[str, Any]:
    value = receipt if isinstance(receipt, dict) else {}
    if not value:
        return {}
    identity = value.get("identity") if isinstance(value.get("identity"), dict) else {}
    verification = verify_delivery_receipt(value)
    return {
        "receipt_id": value.get("receipt_id") or "",
        "status": value.get("status") or "unavailable",
        "receipt_version": identity.get("receipt_version") or "",
        "access_id": value.get("access_id") or "",
        "run_id": value.get("run_id") or "",
        "report_id": value.get("report_id") or "",
        "approval_id": value.get("approval_id") or "",
        "recipient_label": value.get("recipient_label") or "",
        "delivered_at": value.get("delivered_at") or "",
        "download_number": identity.get("download_number") or 0,
        "pdf_sha256": identity.get("pdf_sha256") or "",
        "source_draft_pdf_sha256": identity.get("source_draft_pdf_sha256") or "",
        "approval_identity_sha256": identity.get("approval_identity_sha256") or "",
        "token_fingerprint": identity.get("token_fingerprint") or "",
        "receipt_sha256": value.get("receipt_sha256") or "",
        "verified": bool(verification.get("verified")),
        "verification": verification,
        "persistence": value.get("persistence") or {},
    }


def create_delivery_receipt(redeemed: dict[str, Any]) -> dict[str, Any]:
    """Persist a hash-bound receipt after an access grant is atomically consumed."""

    if not isinstance(redeemed, dict) or redeemed.get("status") != "redeemed" or not redeemed.get("available"):
        return {"status": "blocked", "error": "A delivery receipt requires a completed approved-PDF redemption."}
    access = redeemed.get("access") if isinstance(redeemed.get("access"), dict) else {}
    run_id = str(access.get("run_id") or "")
    report_id = str(access.get("report_id") or "")
    approval_id = str(access.get("approval_id") or "")
    customer_id = str(access.get("customer_id") or redeemed.get("customer_id") or "default_customer")
    project_id = str(access.get("project_id") or redeemed.get("project_id") or "default_project")
    if not run_id or not report_id or not approval_id:
        return {"status": "blocked", "error": "The consumed access grant is missing report identity bindings."}

    recovered = approved_delivery_status(run_id, customer_id=customer_id, project_id=project_id, include_pdf=False)
    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    if not recovered.get("verified") or delivery.get("pdf_sha256") != redeemed.get("pdf_sha256"):
        return {"status": "blocked", "error": "The delivered artifact no longer passes approved-delivery verification."}

    delivered_at = str(access.get("last_redeemed_at") or _iso(_now()))
    receipt_id = f"{RECEIPT_ID_PREFIX}{uuid4().hex[:24]}"
    identity = {
        "receipt_version": RECEIPT_VERSION,
        "receipt_id": receipt_id,
        "access_id": str(access.get("access_id") or ""),
        "run_id": run_id,
        "report_id": report_id,
        "approval_id": approval_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "recipient_label": str(access.get("recipient_label") or "")[:160],
        "delivered_at": delivered_at,
        "download_number": int(access.get("download_count") or 0),
        "pdf_sha256": str(delivery.get("pdf_sha256") or ""),
        "source_draft_pdf_sha256": str(delivery.get("source_draft_pdf_sha256") or ""),
        "approval_identity_sha256": str(delivery.get("approval_identity_sha256") or ""),
        "token_fingerprint": str(access.get("token_fingerprint") or ""),
    }
    if not identity["access_id"] or not identity["token_fingerprint"] or identity["download_number"] < 1:
        return {"status": "blocked", "error": "The consumed access grant is missing receipt identity evidence."}

    receipt_hash = _sha256_json(identity)
    persistence = _persistence_status()
    record = {
        "record_type": RECEIPT_RECORD_TYPE,
        "receipt_id": receipt_id,
        "status": "delivered",
        "access_id": identity["access_id"],
        "customer_id": customer_id,
        "project_id": project_id,
        "run_id": run_id,
        "report_id": report_id,
        "approval_id": approval_id,
        "recipient_label": identity["recipient_label"],
        "delivered_at": delivered_at,
        "receipt_sha256": receipt_hash,
        "identity": identity,
        "persistence": persistence,
        "created_at": delivered_at,
    }
    try:
        stored = _put_record(record)
    except Exception:
        return {"status": "blocked", "error": "The delivery receipt could not be persisted; PDF delivery was stopped."}
    verification = verify_delivery_receipt(stored)
    if not verification.get("verified"):
        return {"status": "blocked", "error": "The persisted delivery receipt failed integrity verification.", "verification": verification}

    STORE.audit(
        "approved_delivery.receipt_created",
        {
            "receipt_id": receipt_id,
            "receipt_sha256": receipt_hash,
            "access_id": identity["access_id"],
            "run_id": run_id,
            "report_id": report_id,
            "approval_id": approval_id,
            "download_number": identity["download_number"],
            "pdf_sha256": identity["pdf_sha256"],
            "token_fingerprint": identity["token_fingerprint"],
            "persistence_adapter": persistence["adapter"],
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return {"status": "recorded", "receipt": _public_receipt(stored)}


def list_delivery_receipts(
    run_or_report_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to list delivery receipts.", "admin_write": admin}
    lookup = str(run_or_report_id or "").strip()
    if not lookup:
        return {"status": "blocked", "error": "run_id or report_id is required"}
    rows = _list_records(lookup, str(customer_id), str(project_id))
    receipts = [_public_receipt(item) for item in rows]
    return {
        "status": "ok",
        "run_or_report_id": lookup,
        "receipt_count": len(receipts),
        "verified_count": sum(1 for item in receipts if item.get("verified")),
        "receipts": receipts,
        "persistence": _persistence_status(),
        "rule": "Receipt records never contain the raw access token; only its short hash fingerprint is retained.",
    }
