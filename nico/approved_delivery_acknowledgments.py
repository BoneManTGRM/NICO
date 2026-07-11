from __future__ import annotations

import hashlib
import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico import approved_delivery_access as access_store
from nico import approved_delivery_receipts as receipt_store
from nico.admin_security import require_admin_write
from nico.approved_delivery_recovery import approved_delivery_status
from nico.storage import STORE

ACKNOWLEDGMENT_RECORD_TYPE = "approved_delivery_acknowledgment"
ACKNOWLEDGMENT_VERSION = "client-receipt-acknowledgment-v1"
ACKNOWLEDGMENT_ID_PREFIX = "delivery_ack_"
ACKNOWLEDGMENT_STATEMENT = (
    "I acknowledge that I received access to the NICO Full Assessment identified by this delivery receipt. "
    "This acknowledgment confirms receipt only; it is not technical approval, agreement with every finding, "
    "a waiver, legal acceptance, or acceptance of liability."
)

_ACKNOWLEDGMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_delivery_acknowledgments (
  acknowledgment_id TEXT PRIMARY KEY,
  receipt_id TEXT UNIQUE NOT NULL,
  access_id TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  approval_id TEXT NOT NULL,
  acknowledged_by TEXT NOT NULL,
  acknowledged_at TIMESTAMPTZ NOT NULL,
  acknowledgment_sha256 TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approved_delivery_ack_scope
  ON approved_delivery_acknowledgments (customer_id, project_id, run_id, acknowledged_at DESC);
CREATE INDEX IF NOT EXISTS idx_approved_delivery_ack_access
  ON approved_delivery_acknowledgments (access_id, acknowledged_at DESC);
"""

_MEMORY_LOCK = threading.RLock()
_MEMORY_ACKNOWLEDGMENTS: dict[str, dict[str, Any]] = {}


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
            cur.execute(_ACKNOWLEDGMENT_SCHEMA)
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
            "Client delivery acknowledgments are durable."
            if durable
            else "Client delivery acknowledgments use process memory and may disappear after restart because durable Postgres acknowledgment storage is unavailable."
        ),
    }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _row_record(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("payload") or {})
    payload.update(
        {
            "acknowledgment_id": row.get("acknowledgment_id"),
            "receipt_id": row.get("receipt_id"),
            "access_id": row.get("access_id"),
            "customer_id": row.get("customer_id"),
            "project_id": row.get("project_id"),
            "run_id": row.get("run_id"),
            "report_id": row.get("report_id"),
            "approval_id": row.get("approval_id"),
            "acknowledged_by": row.get("acknowledged_by") or "",
            "acknowledged_at": _iso(row.get("acknowledged_at")) if isinstance(row.get("acknowledged_at"), datetime) else str(row.get("acknowledged_at") or ""),
            "acknowledgment_sha256": row.get("acknowledgment_sha256") or "",
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
                    INSERT INTO approved_delivery_acknowledgments
                      (acknowledgment_id, receipt_id, access_id, customer_id, project_id, run_id, report_id, approval_id, acknowledged_by, acknowledged_at, acknowledgment_sha256, payload, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (receipt_id) DO NOTHING
                    RETURNING *
                    """,
                    (
                        record["acknowledgment_id"],
                        record["receipt_id"],
                        record["access_id"],
                        record["customer_id"],
                        record["project_id"],
                        record["run_id"],
                        record["report_id"],
                        record["approval_id"],
                        record["acknowledged_by"],
                        record["acknowledged_at"],
                        record["acknowledgment_sha256"],
                        Jsonb(record),
                        record["created_at"],
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row:
            return _row_record(dict(row))
        return _get_by_receipt(record["receipt_id"])

    with _MEMORY_LOCK:
        for item in _MEMORY_ACKNOWLEDGMENTS.values():
            if item.get("receipt_id") == record["receipt_id"]:
                return deepcopy(item)
        _MEMORY_ACKNOWLEDGMENTS[record["acknowledgment_id"]] = deepcopy(record)
        return deepcopy(record)


def _get_by_receipt(receipt_id: str) -> dict[str, Any]:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM approved_delivery_acknowledgments WHERE receipt_id=%s", (receipt_id,))
                row = cur.fetchone()
        return _row_record(dict(row)) if row else {}
    with _MEMORY_LOCK:
        for item in _MEMORY_ACKNOWLEDGMENTS.values():
            if item.get("receipt_id") == receipt_id:
                return deepcopy(item)
    return {}


def _list_records(run_or_report_id: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM approved_delivery_acknowledgments
                    WHERE (run_id=%s OR report_id=%s)
                      AND customer_id=%s AND project_id=%s
                    ORDER BY acknowledged_at DESC
                    """,
                    (run_or_report_id, run_or_report_id, customer_id, project_id),
                )
                rows = list(cur.fetchall())
        return [_row_record(dict(row)) for row in rows]
    with _MEMORY_LOCK:
        rows = [
            deepcopy(item)
            for item in _MEMORY_ACKNOWLEDGMENTS.values()
            if (item.get("run_id") == run_or_report_id or item.get("report_id") == run_or_report_id)
            and item.get("customer_id") == customer_id
            and item.get("project_id") == project_id
        ]
    rows.sort(key=lambda item: str(item.get("acknowledged_at") or ""), reverse=True)
    return rows


def _receipt_record(receipt_id: str) -> dict[str, Any]:
    if receipt_store._postgres_available():
        with receipt_store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM approved_delivery_receipts WHERE receipt_id=%s", (receipt_id,))
                row = cur.fetchone()
        return receipt_store._row_record(dict(row)) if row else {}
    with receipt_store._MEMORY_LOCK:
        value = receipt_store._MEMORY_RECEIPTS.get(receipt_id)
        return deepcopy(value) if isinstance(value, dict) else {}


def verify_delivery_acknowledgment(value: Any) -> dict[str, Any]:
    record = value if isinstance(value, dict) else {}
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    computed = _sha256_json(identity) if identity else ""
    checks = [
        {"id": "acknowledgment_exists", "passed": bool(record), "message": "The client acknowledgment exists."},
        {"id": "record_type", "passed": record.get("record_type") == ACKNOWLEDGMENT_RECORD_TYPE, "message": "The record is a client delivery acknowledgment."},
        {"id": "acknowledgment_version", "passed": identity.get("acknowledgment_version") == ACKNOWLEDGMENT_VERSION, "message": "The acknowledgment uses the supported version."},
        {"id": "status", "passed": record.get("status") == "acknowledged", "message": "The record represents a completed receipt acknowledgment."},
        {"id": "statement_hash", "passed": identity.get("statement_sha256") == _sha256_text(ACKNOWLEDGMENT_STATEMENT), "message": "The acknowledgment is bound to the exact receipt-only statement."},
        {"id": "identity_complete", "passed": bool(identity) and all(str(identity.get(key) or "") for key in ("acknowledgment_id", "receipt_id", "receipt_sha256", "access_id", "run_id", "report_id", "approval_id", "customer_id", "project_id", "acknowledged_by", "acknowledged_at", "pdf_sha256", "token_fingerprint")), "message": "The acknowledgment identity contains every required binding."},
        {"id": "acknowledgment_id_binding", "passed": identity.get("acknowledgment_id") == record.get("acknowledgment_id"), "message": "The identity is bound to the exact acknowledgment ID."},
        {"id": "acknowledgment_hash", "passed": bool(computed) and computed == record.get("acknowledgment_sha256"), "message": "The acknowledgment SHA-256 matches the canonical identity."},
    ]
    blockers = [item["message"] for item in checks if not item["passed"]]
    return {
        "status": "verified" if not blockers else "blocked",
        "verified": not blockers,
        "acknowledgment_id": record.get("acknowledgment_id") or "",
        "acknowledgment_sha256": record.get("acknowledgment_sha256") or "",
        "computed_acknowledgment_sha256": computed,
        "checks": checks,
        "blockers": blockers,
        "rule": "Client acknowledgment proves receipt only and never substitutes for NICO human technical approval or agreement with report findings.",
    }


def _public_acknowledgment(value: Any) -> dict[str, Any]:
    record = value if isinstance(value, dict) else {}
    if not record:
        return {}
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    verification = verify_delivery_acknowledgment(record)
    return {
        "acknowledgment_id": record.get("acknowledgment_id") or "",
        "status": record.get("status") or "unavailable",
        "acknowledgment_version": identity.get("acknowledgment_version") or "",
        "receipt_id": record.get("receipt_id") or "",
        "receipt_sha256": identity.get("receipt_sha256") or "",
        "access_id": record.get("access_id") or "",
        "run_id": record.get("run_id") or "",
        "report_id": record.get("report_id") or "",
        "approval_id": record.get("approval_id") or "",
        "recipient_label": record.get("recipient_label") or "",
        "acknowledged_by": record.get("acknowledged_by") or "",
        "acknowledged_at": record.get("acknowledged_at") or "",
        "statement": ACKNOWLEDGMENT_STATEMENT,
        "statement_sha256": identity.get("statement_sha256") or "",
        "pdf_sha256": identity.get("pdf_sha256") or "",
        "token_fingerprint": identity.get("token_fingerprint") or "",
        "acknowledgment_sha256": record.get("acknowledgment_sha256") or "",
        "verified": bool(verification.get("verified")),
        "verification": verification,
        "persistence": record.get("persistence") or {},
        "receipt_only": True,
        "technical_approval": False,
        "agreement_with_findings": False,
        "legal_acceptance": False,
    }


def create_delivery_acknowledgment(payload: dict[str, Any]) -> dict[str, Any]:
    if not bool(payload.get("acknowledged")):
        return {"status": "blocked", "error": "The recipient must explicitly confirm the receipt-only acknowledgment statement."}
    token = str(payload.get("token") or "").strip()
    receipt_id = str(payload.get("receipt_id") or "").strip()
    acknowledged_by = " ".join(str(payload.get("acknowledged_by") or "").split())[:160]
    if not token or not receipt_id:
        return {"status": "blocked", "error": "A delivery token and receipt ID are required."}
    if len(acknowledged_by) < 2:
        return {"status": "blocked", "error": "The recipient name or identifying label is required."}

    matched = access_store._record_for_token(token)
    if not matched:
        return {"status": "not_found", "error": "This delivery acknowledgment request is unavailable."}
    access, _ = matched
    receipt = _receipt_record(receipt_id)
    receipt_verification = receipt_store.verify_delivery_receipt(receipt)
    receipt_identity = receipt.get("identity") if isinstance(receipt.get("identity"), dict) else {}
    if not receipt_verification.get("verified"):
        return {"status": "blocked", "error": "The delivery receipt failed integrity verification.", "verification": receipt_verification}
    if (
        receipt.get("access_id") != access.get("access_id")
        or receipt_identity.get("token_fingerprint") != access.get("token_fingerprint")
        or receipt.get("run_id") != access.get("run_id")
        or receipt.get("report_id") != access.get("report_id")
        or receipt.get("approval_id") != access.get("approval_id")
        or receipt.get("customer_id") != access.get("customer_id")
        or receipt.get("project_id") != access.get("project_id")
    ):
        return {"status": "blocked", "error": "The delivery token and receipt do not share the same immutable identity."}

    recovered = approved_delivery_status(
        str(receipt.get("run_id") or ""),
        customer_id=str(receipt.get("customer_id") or "default_customer"),
        project_id=str(receipt.get("project_id") or "default_project"),
        include_pdf=False,
    )
    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    if not recovered.get("verified") or delivery.get("pdf_sha256") != receipt_identity.get("pdf_sha256"):
        return {"status": "blocked", "error": "The approved artifact no longer passes delivery verification."}

    existing = _get_by_receipt(receipt_id)
    if existing:
        verification = verify_delivery_acknowledgment(existing)
        if not verification.get("verified"):
            return {"status": "blocked", "error": "An existing acknowledgment failed integrity verification.", "verification": verification}
        if str(existing.get("acknowledged_by") or "") != acknowledged_by:
            return {"status": "blocked", "error": "This delivery receipt already has an immutable acknowledgment by a different recipient identity."}
        return {"status": "acknowledged", "idempotent_reuse": True, "acknowledgment": _public_acknowledgment(existing)}

    acknowledged_at = _iso(_now())
    acknowledgment_id = f"{ACKNOWLEDGMENT_ID_PREFIX}{uuid4().hex[:24]}"
    identity = {
        "acknowledgment_version": ACKNOWLEDGMENT_VERSION,
        "acknowledgment_id": acknowledgment_id,
        "receipt_id": receipt_id,
        "receipt_sha256": str(receipt.get("receipt_sha256") or ""),
        "access_id": str(access.get("access_id") or ""),
        "run_id": str(receipt.get("run_id") or ""),
        "report_id": str(receipt.get("report_id") or ""),
        "approval_id": str(receipt.get("approval_id") or ""),
        "customer_id": str(receipt.get("customer_id") or "default_customer"),
        "project_id": str(receipt.get("project_id") or "default_project"),
        "recipient_label": str(receipt.get("recipient_label") or "")[:160],
        "acknowledged_by": acknowledged_by,
        "acknowledged_at": acknowledged_at,
        "statement_sha256": _sha256_text(ACKNOWLEDGMENT_STATEMENT),
        "pdf_sha256": str(receipt_identity.get("pdf_sha256") or ""),
        "token_fingerprint": str(access.get("token_fingerprint") or ""),
    }
    acknowledgment_hash = _sha256_json(identity)
    persistence = _persistence_status()
    record = {
        "record_type": ACKNOWLEDGMENT_RECORD_TYPE,
        "acknowledgment_id": acknowledgment_id,
        "status": "acknowledged",
        "receipt_id": receipt_id,
        "access_id": identity["access_id"],
        "customer_id": identity["customer_id"],
        "project_id": identity["project_id"],
        "run_id": identity["run_id"],
        "report_id": identity["report_id"],
        "approval_id": identity["approval_id"],
        "recipient_label": identity["recipient_label"],
        "acknowledged_by": acknowledged_by,
        "acknowledged_at": acknowledged_at,
        "acknowledgment_sha256": acknowledgment_hash,
        "identity": identity,
        "persistence": persistence,
        "created_at": acknowledged_at,
    }
    try:
        stored = _put_record(record)
    except Exception:
        return {"status": "blocked", "error": "The client acknowledgment could not be persisted."}
    verification = verify_delivery_acknowledgment(stored)
    if not verification.get("verified"):
        return {"status": "blocked", "error": "The persisted client acknowledgment failed integrity verification.", "verification": verification}
    if str(stored.get("acknowledged_by") or "") != acknowledged_by:
        return {
            "status": "blocked",
            "error": "This delivery receipt was concurrently acknowledged by a different immutable recipient identity.",
            "verification": verification,
        }

    stored_identity = stored.get("identity") if isinstance(stored.get("identity"), dict) else identity
    STORE.audit(
        "approved_delivery.client_acknowledged",
        {
            "acknowledgment_id": stored.get("acknowledgment_id") or acknowledgment_id,
            "acknowledgment_sha256": stored.get("acknowledgment_sha256") or acknowledgment_hash,
            "receipt_id": receipt_id,
            "receipt_sha256": stored_identity.get("receipt_sha256") or identity["receipt_sha256"],
            "access_id": stored_identity.get("access_id") or identity["access_id"],
            "run_id": stored_identity.get("run_id") or identity["run_id"],
            "report_id": stored_identity.get("report_id") or identity["report_id"],
            "approval_id": stored_identity.get("approval_id") or identity["approval_id"],
            "acknowledged_by": acknowledged_by,
            "statement_sha256": stored_identity.get("statement_sha256") or identity["statement_sha256"],
            "pdf_sha256": stored_identity.get("pdf_sha256") or identity["pdf_sha256"],
            "token_fingerprint": stored_identity.get("token_fingerprint") or identity["token_fingerprint"],
            "persistence_adapter": persistence["adapter"],
            "receipt_only": True,
        },
        customer_id=identity["customer_id"],
        project_id=identity["project_id"],
    )
    return {"status": "acknowledged", "idempotent_reuse": stored.get("acknowledgment_id") != acknowledgment_id, "acknowledgment": _public_acknowledgment(stored)}


def list_delivery_acknowledgments(
    run_or_report_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to list client acknowledgments.", "admin_write": admin}
    lookup = str(run_or_report_id or "").strip()
    if not lookup:
        return {"status": "blocked", "error": "run_id or report_id is required"}
    rows = _list_records(lookup, str(customer_id), str(project_id))
    acknowledgments = [_public_acknowledgment(item) for item in rows]
    return {
        "status": "ok",
        "run_or_report_id": lookup,
        "acknowledgment_count": len(acknowledgments),
        "verified_count": sum(1 for item in acknowledgments if item.get("verified")),
        "acknowledgments": acknowledgments,
        "persistence": _persistence_status(),
        "statement": ACKNOWLEDGMENT_STATEMENT,
        "rule": "Client acknowledgment confirms receipt only. It is not technical approval, agreement with findings, waiver, legal acceptance, or acceptance of liability.",
    }
