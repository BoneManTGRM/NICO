from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from nico.admin_security import require_admin_write
from nico.mid_assessment_runs import load_mid_assessment_run
from nico.storage import STORE

ACCESS_RECORD_TYPE = "mid_delivery_access"
RECEIPT_RECORD_TYPE = "mid_delivery_receipt"
ACCESS_ID_PREFIX = "mid_delivery_"
RECEIPT_ID_PREFIX = "mid_receipt_"
MIN_EXPIRY_HOURS = 1
MAX_EXPIRY_HOURS = 168
MIN_DOWNLOADS = 1
MAX_DOWNLOADS = 20
ACKNOWLEDGEMENT_MIN_LENGTH = 20

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mid_delivery_access (
  access_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  approval_id TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  max_downloads INTEGER NOT NULL,
  download_count INTEGER NOT NULL DEFAULT 0,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mid_delivery_access_scope
  ON mid_delivery_access (customer_id, project_id, run_id);
CREATE TABLE IF NOT EXISTS mid_delivery_receipts (
  receipt_id TEXT PRIMARY KEY,
  access_id TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  approval_id TEXT NOT NULL,
  downloaded_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mid_delivery_receipts_scope
  ON mid_delivery_receipts (customer_id, project_id, run_id);
"""

_MEMORY_LOCK = threading.RLock()
_MEMORY_ACCESS: dict[str, dict[str, Any]] = {}
_MEMORY_RECEIPTS: dict[str, dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _database_url() -> str:
    if os.getenv("NICO_DISABLE_POSTGRES", "false").lower() == "true":
        return ""
    return os.getenv("DATABASE_URL", "").strip()


def _connect() -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_database_url(), row_factory=dict_row)


def _postgres_available() -> bool:
    if not _database_url():
        return False
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA)
            conn.commit()
        return True
    except Exception:
        return False


def _persistence_status() -> dict[str, Any]:
    durable = _postgres_available()
    return {
        "durable": durable,
        "adapter": "postgres" if durable else "memory",
        "note": (
            "Mid delivery grants and receipts are durable."
            if durable
            else "Mid delivery grants and receipts use process memory because durable Postgres delivery storage is unavailable."
        ),
    }


def _row_access(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("payload") or {})
    payload.update(
        {
            "access_id": row.get("access_id"),
            "customer_id": row.get("customer_id"),
            "project_id": row.get("project_id"),
            "run_id": row.get("run_id"),
            "report_id": row.get("report_id"),
            "approval_id": row.get("approval_id"),
            "token_hash": row.get("token_hash"),
            "status": row.get("status"),
            "expires_at": _iso(row.get("expires_at")) if isinstance(row.get("expires_at"), datetime) else str(row.get("expires_at") or ""),
            "max_downloads": int(row.get("max_downloads") or 0),
            "download_count": int(row.get("download_count") or 0),
            "created_at": _iso(row.get("created_at")) if isinstance(row.get("created_at"), datetime) else str(row.get("created_at") or ""),
            "updated_at": _iso(row.get("updated_at")) if isinstance(row.get("updated_at"), datetime) else str(row.get("updated_at") or ""),
        }
    )
    return payload


def _row_receipt(row: dict[str, Any]) -> dict[str, Any]:
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
            "downloaded_at": _iso(row.get("downloaded_at")) if isinstance(row.get("downloaded_at"), datetime) else str(row.get("downloaded_at") or ""),
        }
    )
    return payload


def _put_access(record: dict[str, Any]) -> dict[str, Any]:
    if _postgres_available():
        from psycopg.types.json import Jsonb

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mid_delivery_access
                      (access_id, customer_id, project_id, run_id, report_id, approval_id, token_hash, status, expires_at, max_downloads, download_count, payload, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (access_id) DO UPDATE SET
                      status=EXCLUDED.status,
                      expires_at=EXCLUDED.expires_at,
                      max_downloads=EXCLUDED.max_downloads,
                      download_count=EXCLUDED.download_count,
                      payload=EXCLUDED.payload,
                      updated_at=EXCLUDED.updated_at
                    RETURNING *
                    """,
                    (
                        record["access_id"], record["customer_id"], record["project_id"], record["run_id"],
                        record["report_id"], record["approval_id"], record["token_hash"], record["status"],
                        record["expires_at"], record["max_downloads"], record["download_count"], Jsonb(record),
                        record["created_at"], record["updated_at"],
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return _row_access(dict(row or {}))
    with _MEMORY_LOCK:
        _MEMORY_ACCESS[record["access_id"]] = deepcopy(record)
        return deepcopy(record)


def _get_access(access_id: str) -> dict[str, Any] | None:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM mid_delivery_access WHERE access_id=%s", (access_id,))
                row = cur.fetchone()
        return _row_access(dict(row)) if row else None
    with _MEMORY_LOCK:
        value = _MEMORY_ACCESS.get(access_id)
        return deepcopy(value) if value else None


def _list_access(run_id: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM mid_delivery_access WHERE run_id=%s AND customer_id=%s AND project_id=%s ORDER BY created_at DESC",
                    (run_id, customer_id, project_id),
                )
                rows = list(cur.fetchall())
        return [_row_access(dict(row)) for row in rows]
    with _MEMORY_LOCK:
        rows = [
            deepcopy(item)
            for item in _MEMORY_ACCESS.values()
            if item.get("run_id") == run_id and item.get("customer_id") == customer_id and item.get("project_id") == project_id
        ]
    return sorted(rows, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def _consume_access(access_id: str, token_hash: str, redeemed_at: str) -> dict[str, Any] | None:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE mid_delivery_access
                    SET download_count=download_count + 1,
                        updated_at=%s,
                        payload=jsonb_set(payload, '{last_redeemed_at}', to_jsonb(%s::text))
                    WHERE access_id=%s AND token_hash=%s AND status='active'
                      AND expires_at > %s AND download_count < max_downloads
                    RETURNING *
                    """,
                    (redeemed_at, redeemed_at, access_id, token_hash, redeemed_at),
                )
                row = cur.fetchone()
            conn.commit()
        return _row_access(dict(row)) if row else None
    with _MEMORY_LOCK:
        record = _MEMORY_ACCESS.get(access_id)
        expires_at = _parse_iso(_dict(record).get("expires_at"))
        valid = bool(
            record
            and hmac.compare_digest(str(record.get("token_hash") or ""), token_hash)
            and record.get("status") == "active"
            and expires_at is not None
            and expires_at > _now()
            and int(record.get("download_count") or 0) < int(record.get("max_downloads") or 0)
        )
        if not valid:
            return None
        record["download_count"] = int(record.get("download_count") or 0) + 1
        record["last_redeemed_at"] = redeemed_at
        record["updated_at"] = redeemed_at
        return deepcopy(record)


def _revoke_access(access_id: str, actor: str, reason: str, revoked_at: str) -> dict[str, Any] | None:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE mid_delivery_access
                    SET status='revoked', updated_at=%s,
                        payload=jsonb_set(jsonb_set(jsonb_set(payload, '{status}', to_jsonb('revoked'::text)), '{revoked_at}', to_jsonb(%s::text)), '{revoked_by}', to_jsonb(%s::text))
                    WHERE access_id=%s AND status='active'
                    RETURNING *
                    """,
                    (revoked_at, revoked_at, actor, access_id),
                )
                row = cur.fetchone()
            conn.commit()
        record = _row_access(dict(row)) if row else _get_access(access_id)
        if record:
            record["revoked_at"] = revoked_at
            record["revoked_by"] = actor
            record["revoke_reason"] = reason
        return record
    with _MEMORY_LOCK:
        record = _MEMORY_ACCESS.get(access_id)
        if not record:
            return None
        if record.get("status") == "active":
            record["status"] = "revoked"
            record["revoked_at"] = revoked_at
            record["revoked_by"] = actor
            record["revoke_reason"] = reason
            record["updated_at"] = revoked_at
        return deepcopy(record)


def _put_receipt(record: dict[str, Any]) -> dict[str, Any]:
    if _postgres_available():
        from psycopg.types.json import Jsonb

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mid_delivery_receipts
                      (receipt_id, access_id, customer_id, project_id, run_id, report_id, approval_id, downloaded_at, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (receipt_id) DO NOTHING
                    RETURNING *
                    """,
                    (
                        record["receipt_id"], record["access_id"], record["customer_id"], record["project_id"],
                        record["run_id"], record["report_id"], record["approval_id"], record["downloaded_at"], Jsonb(record),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return _row_receipt(dict(row or {})) if row else record
    with _MEMORY_LOCK:
        _MEMORY_RECEIPTS[record["receipt_id"]] = deepcopy(record)
        return deepcopy(record)


def _list_receipts(run_id: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM mid_delivery_receipts WHERE run_id=%s AND customer_id=%s AND project_id=%s ORDER BY downloaded_at DESC",
                    (run_id, customer_id, project_id),
                )
                rows = list(cur.fetchall())
        return [_row_receipt(dict(row)) for row in rows]
    with _MEMORY_LOCK:
        rows = [
            deepcopy(item)
            for item in _MEMORY_RECEIPTS.values()
            if item.get("run_id") == run_id and item.get("customer_id") == customer_id and item.get("project_id") == project_id
        ]
    return sorted(rows, key=lambda item: str(item.get("downloaded_at") or ""), reverse=True)


def _decode_report_pdf(report: dict[str, Any]) -> bytes:
    formats = _dict(report.get("formats"))
    try:
        pdf = base64.b64decode(str(formats.get("pdf") or ""), validate=True)
    except Exception:
        return b""
    return pdf if pdf.startswith(b"%PDF") else b""


def _approved_artifact(run_id: str, customer_id: str, project_id: str) -> dict[str, Any]:
    run = load_mid_assessment_run(run_id)
    if not run or run.get("customer_id") != customer_id or run.get("project_id") != project_id:
        return {"status": "not_found"}
    approval = _dict(STORE.get("approvals", str(run.get("approval_id") or "")))
    report = _dict(STORE.get("reports", str(run.get("approved_report_id") or "")))
    pdf = _decode_report_pdf(report)
    approval_report = _dict(approval.get("approved_report"))
    valid = bool(
        approval.get("record_type") == "mid_report_approval"
        and approval.get("status") == "approved"
        and report.get("record_type") == "mid_approved_report"
        and report.get("status") == "complete"
        and report.get("approved") is True
        and report.get("delivery_eligible") is True
        and int(report.get("unsupported_claims_permitted") or 0) == 0
        and report.get("run_id") == run_id
        and report.get("customer_id") == customer_id
        and report.get("project_id") == project_id
        and report.get("snapshot_id") == run.get("snapshot_id")
        and report.get("snapshot_commit_sha") == run.get("snapshot_commit_sha")
        and report.get("approval_id") == approval.get("approval_id")
        and approval_report.get("report_id") == report.get("report_id")
        and approval_report.get("pdf_sha256") == report.get("pdf_sha256")
        and bool(pdf)
        and hashlib.sha256(pdf).hexdigest() == report.get("pdf_sha256")
    )
    if not valid:
        return {"status": "blocked", "error": "The approved Mid artifact failed current integrity verification."}
    return {"status": "verified", "run": run, "approval": approval, "report": report, "pdf": pdf}


def _artifact_identity(report: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": report.get("run_id") or "",
        "report_id": report.get("report_id") or "",
        "approval_id": approval.get("approval_id") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "pdf_sha256": report.get("pdf_sha256") or "",
        "source_draft_report_id": report.get("source_draft_report_id") or "",
        "source_draft_pdf_sha256": report.get("source_draft_pdf_sha256") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "approval_identity_sha256": report.get("approval_identity_sha256") or "",
        "unsupported_claims_permitted": int(report.get("unsupported_claims_permitted") or 0),
    }


def _artifact_matches(record: dict[str, Any], artifact: dict[str, Any]) -> bool:
    if artifact.get("status") != "verified":
        return False
    expected = _dict(record.get("artifact_identity"))
    current = _artifact_identity(_dict(artifact.get("report")), _dict(artifact.get("approval")))
    return bool(expected and hmac.compare_digest(_canonical_hash(expected), _canonical_hash(current)))


def _parse_token(token: Any) -> tuple[str, str] | None:
    text = str(token or "").strip()
    if len(text) > 240 or "." not in text:
        return None
    access_id, secret = text.split(".", 1)
    if not access_id.startswith(ACCESS_ID_PREFIX) or len(secret) < 32:
        return None
    return access_id, _sha256_text(text)


def _record_for_token(token: Any) -> tuple[dict[str, Any], str] | None:
    parsed = _parse_token(token)
    if not parsed:
        return None
    access_id, supplied_hash = parsed
    record = _get_access(access_id)
    if not record or record.get("record_type") != ACCESS_RECORD_TYPE:
        return None
    stored_hash = str(record.get("token_hash") or "")
    if not stored_hash or not hmac.compare_digest(stored_hash, supplied_hash):
        return None
    return record, supplied_hash


def _active(record: dict[str, Any]) -> bool:
    expires_at = _parse_iso(record.get("expires_at"))
    return bool(
        record.get("status") == "active"
        and expires_at is not None
        and expires_at > _now()
        and int(record.get("download_count") or 0) < int(record.get("max_downloads") or 0)
    )


def _public_access(record: Any) -> dict[str, Any]:
    value = record if isinstance(record, dict) else {}
    if not value:
        return {}
    maximum = int(value.get("max_downloads") or 0)
    count = int(value.get("download_count") or 0)
    return {
        "access_id": value.get("access_id") or "",
        "status": value.get("status") or "unavailable",
        "run_id": value.get("run_id") or "",
        "report_id": value.get("report_id") or "",
        "approval_id": value.get("approval_id") or "",
        "recipient_label": value.get("recipient_label") or "",
        "created_by": value.get("created_by") or "",
        "created_at": value.get("created_at") or "",
        "expires_at": value.get("expires_at") or "",
        "revoked_at": value.get("revoked_at") or "",
        "revoked_by": value.get("revoked_by") or "",
        "revoke_reason": value.get("revoke_reason") or "",
        "max_downloads": maximum,
        "download_count": count,
        "downloads_remaining": max(0, maximum - count),
        "last_redeemed_at": value.get("last_redeemed_at") or "",
        "token_fingerprint": value.get("token_fingerprint") or "",
        "artifact_identity_sha256": value.get("artifact_identity_sha256") or "",
        "persistence": value.get("persistence") or {},
    }


def _public_receipt(record: Any) -> dict[str, Any]:
    value = record if isinstance(record, dict) else {}
    if not value:
        return {}
    return {
        "receipt_id": value.get("receipt_id") or "",
        "receipt_sha256": value.get("receipt_sha256") or "",
        "access_id": value.get("access_id") or "",
        "run_id": value.get("run_id") or "",
        "report_id": value.get("report_id") or "",
        "approval_id": value.get("approval_id") or "",
        "recipient_label": value.get("recipient_label") or "",
        "recipient_name": value.get("recipient_name") or "",
        "acknowledgement_text": value.get("acknowledgement_text") or "",
        "acknowledgement_sha256": value.get("acknowledgement_sha256") or "",
        "downloaded_at": value.get("downloaded_at") or "",
        "download_ordinal": int(value.get("download_ordinal") or 0),
        "pdf_sha256": value.get("pdf_sha256") or "",
        "approval_identity_sha256": value.get("approval_identity_sha256") or "",
        "review_packet_sha256": value.get("review_packet_sha256") or "",
        "token_fingerprint": value.get("token_fingerprint") or "",
    }


def _unavailable() -> dict[str, Any]:
    return {"status": "not_found", "available": False, "message": "This Mid delivery link is unavailable."}


def create_mid_delivery_access(payload: dict[str, Any], admin_token: str = "") -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to create a Mid delivery link.", "admin_write": admin}
    run_id = str(payload.get("run_id") or "").strip()
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")
    recipient_label = " ".join(str(payload.get("recipient_label") or "").split())[:160]
    created_by = " ".join(str(payload.get("created_by") or "").split())[:160]
    if not run_id:
        return {"status": "blocked", "error": "run_id is required."}
    if len(recipient_label) < 2:
        return {"status": "blocked", "error": "A recipient label is required."}
    if len(created_by) < 2:
        return {"status": "blocked", "error": "The grant creator identity is required."}
    artifact = _approved_artifact(run_id, customer_id, project_id)
    if artifact.get("status") == "not_found":
        return artifact
    if artifact.get("status") != "verified":
        return {"status": "blocked", "error": str(artifact.get("error") or "The approved Mid artifact is unavailable.")}
    report = _dict(artifact.get("report"))
    approval = _dict(artifact.get("approval"))
    expires_in_hours = _clamp_int(payload.get("expires_in_hours"), MIN_EXPIRY_HOURS, MAX_EXPIRY_HOURS, 24)
    max_downloads = _clamp_int(payload.get("max_downloads"), MIN_DOWNLOADS, MAX_DOWNLOADS, 1)
    created_at = _now()
    access_id = f"{ACCESS_ID_PREFIX}{uuid4().hex[:24]}"
    raw_token = f"{access_id}.{secrets.token_urlsafe(32)}"
    token_hash = _sha256_text(raw_token)
    identity = _artifact_identity(report, approval)
    persistence = _persistence_status()
    record = {
        "record_type": ACCESS_RECORD_TYPE,
        "access_id": access_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "run_id": run_id,
        "report_id": report.get("report_id") or "",
        "approval_id": approval.get("approval_id") or "",
        "status": "active",
        "token_hash": token_hash,
        "token_fingerprint": token_hash[:12],
        "recipient_label": recipient_label,
        "created_by": created_by,
        "created_at": _iso(created_at),
        "updated_at": _iso(created_at),
        "expires_at": _iso(created_at + timedelta(hours=expires_in_hours)),
        "max_downloads": max_downloads,
        "download_count": 0,
        "last_redeemed_at": "",
        "revoked_at": "",
        "persistence": persistence,
        "artifact_identity": identity,
        "artifact_identity_sha256": _canonical_hash(identity),
        "acknowledgement_required": True,
    }
    stored = _put_access(record)
    STORE.audit(
        "mid.delivery_access_created",
        {
            "access_id": access_id,
            "run_id": run_id,
            "report_id": record["report_id"],
            "approval_id": record["approval_id"],
            "recipient_label": recipient_label,
            "expires_at": record["expires_at"],
            "max_downloads": max_downloads,
            "token_fingerprint": record["token_fingerprint"],
            "artifact_identity_sha256": record["artifact_identity_sha256"],
            "persistence_adapter": persistence["adapter"],
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return {
        "status": "created",
        "token": raw_token,
        "fragment_path": f"/mid-delivery#token={quote(raw_token, safe='')}",
        "access": _public_access(stored),
        "warning": "The raw token is returned once. Only its SHA-256 hash and fingerprint are stored or audited.",
    }


def list_mid_delivery_access(run_id: str, customer_id: str, project_id: str, admin_token: str = "") -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to list Mid delivery links.", "admin_write": admin}
    run = load_mid_assessment_run(run_id)
    if not run or run.get("customer_id") != customer_id or run.get("project_id") != project_id:
        return {"status": "not_found", "error": "Mid Assessment run not found."}
    return {"status": "ok", "access": [_public_access(item) for item in _list_access(run_id, customer_id, project_id)]}


def revoke_mid_delivery_access(access_id: str, actor: str, reason: str, admin_token: str = "") -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to revoke a Mid delivery link.", "admin_write": admin}
    reviewer = " ".join(str(actor or "").split())[:160]
    revoke_reason = str(reason or "").strip()[:1000]
    if len(reviewer) < 2:
        return {"status": "blocked", "error": "Revocation actor is required."}
    if len(revoke_reason) < 5:
        return {"status": "blocked", "error": "A revocation reason is required."}
    existing = _get_access(str(access_id or ""))
    if not existing or existing.get("record_type") != ACCESS_RECORD_TYPE:
        return {"status": "not_found", "error": "Mid delivery link not found."}
    record = _revoke_access(str(access_id), reviewer, revoke_reason, _iso(_now()))
    STORE.audit(
        "mid.delivery_access_revoked",
        {
            "access_id": access_id,
            "run_id": existing.get("run_id") or "",
            "report_id": existing.get("report_id") or "",
            "approval_id": existing.get("approval_id") or "",
            "revoked_by": reviewer,
            "reason": revoke_reason,
        },
        customer_id=existing.get("customer_id"),
        project_id=existing.get("project_id"),
    )
    return {"status": "revoked", "access": _public_access(record), "idempotent_reuse": existing.get("status") == "revoked"}


def inspect_mid_delivery_access(token: Any) -> dict[str, Any]:
    matched = _record_for_token(token)
    if not matched:
        return _unavailable()
    record, _ = matched
    if not _active(record):
        return _unavailable()
    artifact = _approved_artifact(
        str(record.get("run_id") or ""),
        str(record.get("customer_id") or "default_customer"),
        str(record.get("project_id") or "default_project"),
    )
    if not _artifact_matches(record, artifact):
        STORE.audit(
            "mid.delivery_access_verification_blocked",
            {"access_id": record.get("access_id"), "reason": "artifact_identity_mismatch"},
            customer_id=record.get("customer_id"),
            project_id=record.get("project_id"),
        )
        return _unavailable()
    report = _dict(artifact.get("report"))
    return {
        "status": "available",
        "available": True,
        "access": _public_access(record),
        "delivery": {
            "report_id": report.get("report_id") or "",
            "pdf_filename": report.get("pdf_filename") or "nico-mid-assessment-APPROVED.pdf",
            "pdf_sha256": report.get("pdf_sha256") or "",
            "approval_id": report.get("approval_id") or "",
            "approval_identity_sha256": report.get("approval_identity_sha256") or "",
            "review_packet_sha256": report.get("review_packet_sha256") or "",
            "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
            "approved_by": report.get("approved_by") or "",
            "approved_at": report.get("approved_at") or "",
            "disclosure": "This is the human-approved Mid artifact. Download requires recipient acknowledgement and creates an auditable receipt.",
            "acknowledgement_required": True,
        },
    }


def redeem_mid_delivery_access(
    token: Any,
    recipient_name: str,
    acknowledged: bool,
    acknowledgement_text: str,
) -> dict[str, Any]:
    matched = _record_for_token(token)
    if not matched:
        return _unavailable()
    record, supplied_hash = matched
    recipient = " ".join(str(recipient_name or "").split())[:160]
    acknowledgement = " ".join(str(acknowledgement_text or "").split())[:2000]
    if len(recipient) < 2:
        return {"status": "blocked", "error": "Recipient name is required before download."}
    if acknowledged is not True or len(acknowledgement) < ACKNOWLEDGEMENT_MIN_LENGTH:
        return {"status": "blocked", "error": "Explicit acknowledgement of receipt and disclosed limitations is required before download."}
    if not _active(record):
        return _unavailable()
    artifact = _approved_artifact(
        str(record.get("run_id") or ""),
        str(record.get("customer_id") or "default_customer"),
        str(record.get("project_id") or "default_project"),
    )
    if not _artifact_matches(record, artifact):
        return _unavailable()
    redeemed_at = _iso(_now())
    consumed = _consume_access(str(record.get("access_id") or ""), supplied_hash, redeemed_at)
    if not consumed:
        return _unavailable()
    report = _dict(artifact.get("report"))
    pdf = bytes(artifact.get("pdf") or b"")
    if not pdf or hashlib.sha256(pdf).hexdigest() != report.get("pdf_sha256"):
        return {"status": "blocked", "error": "The approved Mid PDF failed final download integrity verification."}
    receipt_id = f"{RECEIPT_ID_PREFIX}{uuid4().hex[:24]}"
    receipt_core = {
        "record_type": RECEIPT_RECORD_TYPE,
        "receipt_id": receipt_id,
        "access_id": consumed.get("access_id") or "",
        "customer_id": consumed.get("customer_id") or "default_customer",
        "project_id": consumed.get("project_id") or "default_project",
        "run_id": consumed.get("run_id") or "",
        "report_id": consumed.get("report_id") or "",
        "approval_id": consumed.get("approval_id") or "",
        "recipient_label": consumed.get("recipient_label") or "",
        "recipient_name": recipient,
        "acknowledgement_text": acknowledgement,
        "acknowledgement_sha256": _sha256_text(acknowledgement),
        "downloaded_at": redeemed_at,
        "download_ordinal": int(consumed.get("download_count") or 0),
        "pdf_sha256": report.get("pdf_sha256") or "",
        "approval_identity_sha256": report.get("approval_identity_sha256") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "token_fingerprint": consumed.get("token_fingerprint") or "",
    }
    receipt = dict(receipt_core)
    receipt["receipt_sha256"] = _canonical_hash(receipt_core)
    stored_receipt = _put_receipt(receipt)
    STORE.audit(
        "mid.delivery_downloaded",
        {
            "receipt_id": receipt_id,
            "receipt_sha256": receipt["receipt_sha256"],
            "access_id": receipt["access_id"],
            "run_id": receipt["run_id"],
            "report_id": receipt["report_id"],
            "approval_id": receipt["approval_id"],
            "recipient_label": receipt["recipient_label"],
            "recipient_name": recipient,
            "download_ordinal": receipt["download_ordinal"],
            "pdf_sha256": receipt["pdf_sha256"],
            "acknowledgement_sha256": receipt["acknowledgement_sha256"],
            "token_fingerprint": receipt["token_fingerprint"],
        },
        customer_id=receipt["customer_id"],
        project_id=receipt["project_id"],
    )
    return {
        "status": "downloaded",
        "pdf": pdf,
        "pdf_filename": report.get("pdf_filename") or "nico-mid-assessment-APPROVED.pdf",
        "pdf_sha256": report.get("pdf_sha256") or "",
        "report_id": report.get("report_id") or "",
        "approval_id": report.get("approval_id") or "",
        "approval_identity_sha256": report.get("approval_identity_sha256") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "receipt": _public_receipt(stored_receipt),
        "access": _public_access(consumed),
    }


def list_mid_delivery_receipts(run_id: str, customer_id: str, project_id: str, admin_token: str = "") -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to list Mid delivery receipts.", "admin_write": admin}
    run = load_mid_assessment_run(run_id)
    if not run or run.get("customer_id") != customer_id or run.get("project_id") != project_id:
        return {"status": "not_found", "error": "Mid Assessment run not found."}
    return {"status": "ok", "receipts": [_public_receipt(item) for item in _list_receipts(run_id, customer_id, project_id)]}


__all__ = [
    "create_mid_delivery_access",
    "list_mid_delivery_access",
    "revoke_mid_delivery_access",
    "inspect_mid_delivery_access",
    "redeem_mid_delivery_access",
    "list_mid_delivery_receipts",
]
