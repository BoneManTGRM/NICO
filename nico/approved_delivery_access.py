from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from nico.admin_security import require_admin_write
from nico.approved_delivery_recovery import approved_delivery_status
from nico.storage import STORE

ACCESS_RECORD_TYPE = "approved_delivery_access"
ACCESS_ID_PREFIX = "delivery_access_"
MIN_EXPIRY_HOURS = 1
MAX_EXPIRY_HOURS = 168
MIN_DOWNLOADS = 1
MAX_DOWNLOADS = 20

_ACCESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_delivery_access (
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
CREATE INDEX IF NOT EXISTS idx_approved_delivery_access_scope
  ON approved_delivery_access (customer_id, project_id, run_id);
"""

_MEMORY_LOCK = threading.RLock()
_MEMORY_ACCESS: dict[str, dict[str, Any]] = {}


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


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


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


def _ensure_schema() -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_ACCESS_SCHEMA)
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
        "note": "Approved-delivery access grants are durable." if durable else "Approved-delivery access grants use process memory and will expire on restart because durable Postgres access storage is unavailable.",
    }


def _row_record(row: dict[str, Any]) -> dict[str, Any]:
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


def _put_record(record: dict[str, Any]) -> dict[str, Any]:
    if _postgres_available():
        from psycopg.types.json import Jsonb

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO approved_delivery_access
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
                        record["access_id"],
                        record["customer_id"],
                        record["project_id"],
                        record["run_id"],
                        record["report_id"],
                        record["approval_id"],
                        record["token_hash"],
                        record["status"],
                        record["expires_at"],
                        record["max_downloads"],
                        record["download_count"],
                        Jsonb(record),
                        record["created_at"],
                        record["updated_at"],
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return _row_record(dict(row or {}))

    with _MEMORY_LOCK:
        _MEMORY_ACCESS[record["access_id"]] = deepcopy(record)
        return deepcopy(record)


def _get_record(access_id: str) -> dict[str, Any] | None:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM approved_delivery_access WHERE access_id=%s", (access_id,))
                row = cur.fetchone()
        return _row_record(dict(row)) if row else None
    with _MEMORY_LOCK:
        value = _MEMORY_ACCESS.get(access_id)
        return deepcopy(value) if value else None


def _list_records(run_id: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM approved_delivery_access
                    WHERE run_id=%s AND customer_id=%s AND project_id=%s
                    ORDER BY created_at DESC
                    """,
                    (run_id, customer_id, project_id),
                )
                rows = list(cur.fetchall())
        return [_row_record(dict(row)) for row in rows]
    with _MEMORY_LOCK:
        rows = [
            deepcopy(item)
            for item in _MEMORY_ACCESS.values()
            if item.get("run_id") == run_id
            and item.get("customer_id") == customer_id
            and item.get("project_id") == project_id
        ]
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return rows


def _revoke_record(access_id: str, revoked_at: str, revoked_by: str) -> dict[str, Any] | None:
    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approved_delivery_access
                    SET status='revoked', updated_at=%s,
                        payload=jsonb_set(jsonb_set(payload, '{status}', to_jsonb('revoked'::text)), '{revoked_at}', to_jsonb(%s::text))
                    WHERE access_id=%s AND status='active'
                    RETURNING *
                    """,
                    (revoked_at, revoked_at, access_id),
                )
                row = cur.fetchone()
            conn.commit()
        record = _row_record(dict(row)) if row else _get_record(access_id)
        if record:
            record["revoked_at"] = revoked_at
            record["revoked_by"] = revoked_by
        return record

    with _MEMORY_LOCK:
        record = _MEMORY_ACCESS.get(access_id)
        if not record:
            return None
        if record.get("status") == "active":
            record["status"] = "revoked"
            record["revoked_at"] = revoked_at
            record["revoked_by"] = revoked_by
            record["updated_at"] = revoked_at
        return deepcopy(record)


def _consume_record(access_id: str, token_hash: str, redeemed_at: str) -> dict[str, Any] | None:
    """Atomically consume one permitted download in Postgres or under a memory lock."""

    if _postgres_available():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approved_delivery_access
                    SET download_count=download_count + 1,
                        updated_at=%s,
                        payload=jsonb_set(payload, '{last_redeemed_at}', to_jsonb(%s::text))
                    WHERE access_id=%s
                      AND token_hash=%s
                      AND status='active'
                      AND expires_at > %s
                      AND download_count < max_downloads
                    RETURNING *
                    """,
                    (redeemed_at, redeemed_at, access_id, token_hash, redeemed_at),
                )
                row = cur.fetchone()
            conn.commit()
        record = _row_record(dict(row)) if row else None
        if record:
            record["last_redeemed_at"] = redeemed_at
        return record

    with _MEMORY_LOCK:
        record = _MEMORY_ACCESS.get(access_id)
        if not record:
            return None
        expires_at = _parse_iso(record.get("expires_at"))
        valid = (
            hmac.compare_digest(str(record.get("token_hash") or ""), token_hash)
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


def _public_record(record: Any) -> dict[str, Any]:
    value = record if isinstance(record, dict) else {}
    if not value:
        return {}
    max_downloads = int(value.get("max_downloads") or 0)
    download_count = int(value.get("download_count") or 0)
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
        "max_downloads": max_downloads,
        "download_count": download_count,
        "downloads_remaining": max(0, max_downloads - download_count),
        "last_redeemed_at": value.get("last_redeemed_at") or "",
        "token_fingerprint": value.get("token_fingerprint") or "",
        "persistence": value.get("persistence") or {},
    }


def _unavailable() -> dict[str, Any]:
    return {
        "status": "not_found",
        "available": False,
        "message": "This approved-delivery link is unavailable.",
    }


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
    record = _get_record(access_id)
    if not record or record.get("record_type") != ACCESS_RECORD_TYPE:
        return None
    stored_hash = str(record.get("token_hash") or "")
    if not stored_hash or not hmac.compare_digest(stored_hash, supplied_hash):
        return None
    return record, supplied_hash


def _record_active(record: dict[str, Any]) -> bool:
    expires_at = _parse_iso(record.get("expires_at"))
    return (
        record.get("status") == "active"
        and expires_at is not None
        and expires_at > _now()
        and int(record.get("download_count") or 0) < int(record.get("max_downloads") or 0)
    )


def _artifact_matches(record: dict[str, Any], recovered: dict[str, Any]) -> bool:
    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    expected = record.get("artifact_identity") if isinstance(record.get("artifact_identity"), dict) else {}
    return bool(
        recovered.get("verified")
        and recovered.get("run_id") == record.get("run_id")
        and recovered.get("report_id") == record.get("report_id")
        and recovered.get("approval_id") == record.get("approval_id")
        and delivery.get("pdf_sha256") == expected.get("pdf_sha256")
        and delivery.get("source_draft_pdf_sha256") == expected.get("source_draft_pdf_sha256")
        and delivery.get("approval_identity_sha256") == expected.get("approval_identity_sha256")
    )


def create_approved_delivery_access(payload: dict[str, Any], admin_token: str = "") -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to create a client delivery link.", "admin_write": admin}

    run_id = str(payload.get("run_id") or payload.get("report_id") or "").strip()
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")
    if not run_id:
        return {"status": "blocked", "error": "run_id or report_id is required"}

    recovered = approved_delivery_status(run_id, customer_id=customer_id, project_id=project_id, include_pdf=False)
    if not recovered.get("verified"):
        return {
            "status": "blocked",
            "error": "A client delivery link can be created only for a currently verified approved artifact.",
            "verification": recovered.get("verification") or {},
        }

    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    expires_in_hours = _clamp_int(payload.get("expires_in_hours"), MIN_EXPIRY_HOURS, MAX_EXPIRY_HOURS, 24)
    max_downloads = _clamp_int(payload.get("max_downloads"), MIN_DOWNLOADS, MAX_DOWNLOADS, 1)
    created_at = _now()
    access_id = f"{ACCESS_ID_PREFIX}{uuid4().hex[:24]}"
    raw_token = f"{access_id}.{secrets.token_urlsafe(32)}"
    token_hash = _sha256_text(raw_token)
    persistence = _persistence_status()
    record = {
        "record_type": ACCESS_RECORD_TYPE,
        "access_id": access_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "run_id": recovered.get("run_id") or run_id,
        "report_id": recovered.get("report_id") or "",
        "approval_id": recovered.get("approval_id") or "",
        "status": "active",
        "token_hash": token_hash,
        "token_fingerprint": token_hash[:12],
        "recipient_label": str(payload.get("recipient_label") or "").strip()[:160],
        "created_by": str(payload.get("created_by") or "human_reviewer").strip()[:160],
        "created_at": _iso(created_at),
        "updated_at": _iso(created_at),
        "expires_at": _iso(created_at + timedelta(hours=expires_in_hours)),
        "max_downloads": max_downloads,
        "download_count": 0,
        "last_redeemed_at": "",
        "revoked_at": "",
        "persistence": persistence,
        "artifact_identity": {
            "pdf_sha256": delivery.get("pdf_sha256") or "",
            "source_draft_pdf_sha256": delivery.get("source_draft_pdf_sha256") or "",
            "approval_identity_sha256": delivery.get("approval_identity_sha256") or "",
            "style_version": delivery.get("style_version") or "",
        },
    }
    stored = _put_record(record)
    STORE.audit(
        "approved_delivery.access_created",
        {
            "access_id": access_id,
            "run_id": record["run_id"],
            "report_id": record["report_id"],
            "approval_id": record["approval_id"],
            "expires_at": record["expires_at"],
            "max_downloads": max_downloads,
            "token_fingerprint": record["token_fingerprint"],
            "persistence_adapter": persistence["adapter"],
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return {
        "status": "created",
        "token": raw_token,
        "fragment_path": f"/delivery#token={quote(raw_token, safe='')}",
        "access": _public_record(stored),
        "warning": "The raw token is returned once and is never stored or written to the audit log.",
    }


def list_approved_delivery_access(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to list client delivery links.", "admin_write": admin}
    rows = _list_records(str(run_id), str(customer_id), str(project_id))
    return {"status": "ok", "access": [_public_record(item) for item in rows]}


def inspect_approved_delivery_access(token: Any) -> dict[str, Any]:
    matched = _record_for_token(token)
    if not matched:
        return _unavailable()
    record, _ = matched
    if not _record_active(record):
        return _unavailable()
    recovered = approved_delivery_status(
        str(record.get("run_id") or ""),
        customer_id=str(record.get("customer_id") or "default_customer"),
        project_id=str(record.get("project_id") or "default_project"),
        include_pdf=False,
    )
    if not _artifact_matches(record, recovered):
        STORE.audit(
            "approved_delivery.access_verification_blocked",
            {"access_id": record.get("access_id"), "reason": "artifact_identity_mismatch"},
            customer_id=record.get("customer_id"),
            project_id=record.get("project_id"),
        )
        return _unavailable()
    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    return {
        "status": "available",
        "available": True,
        "access": _public_record(record),
        "delivery": {
            "pdf_filename": delivery.get("pdf_filename") or "nico-full-assessment-approved.pdf",
            "approver": delivery.get("approver") or "",
            "approved_at": delivery.get("approved_at") or "",
            "disclosure": delivery.get("disclosure") or "",
            "pdf_sha256": delivery.get("pdf_sha256") or "",
        },
    }


def redeem_approved_delivery_access(token: Any) -> dict[str, Any]:
    matched = _record_for_token(token)
    if not matched:
        return _unavailable()
    record, supplied_hash = matched
    if not _record_active(record):
        return _unavailable()

    recovered = approved_delivery_status(
        str(record.get("run_id") or ""),
        customer_id=str(record.get("customer_id") or "default_customer"),
        project_id=str(record.get("project_id") or "default_project"),
        include_pdf=True,
    )
    if not _artifact_matches(record, recovered):
        STORE.audit(
            "approved_delivery.access_verification_blocked",
            {"access_id": record.get("access_id"), "reason": "artifact_identity_mismatch"},
            customer_id=record.get("customer_id"),
            project_id=record.get("project_id"),
        )
        return _unavailable()

    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}
    encoded = str(delivery.get("pdf_base64") or "")
    try:
        pdf_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        return _unavailable()
    if not pdf_bytes.startswith(b"%PDF"):
        return _unavailable()

    redeemed_at = _iso(_now())
    consumed = _consume_record(str(record.get("access_id") or ""), supplied_hash, redeemed_at)
    if not consumed:
        return _unavailable()
    STORE.audit(
        "approved_delivery.access_redeemed",
        {
            "access_id": consumed.get("access_id"),
            "run_id": consumed.get("run_id"),
            "report_id": consumed.get("report_id"),
            "download_count": consumed.get("download_count"),
            "max_downloads": consumed.get("max_downloads"),
            "token_fingerprint": consumed.get("token_fingerprint"),
        },
        customer_id=consumed.get("customer_id"),
        project_id=consumed.get("project_id"),
    )
    return {
        "status": "redeemed",
        "available": True,
        "pdf_bytes": pdf_bytes,
        "pdf_filename": delivery.get("pdf_filename") or "nico-full-assessment-approved.pdf",
        "pdf_sha256": delivery.get("pdf_sha256") or "",
        "access": _public_record(consumed),
    }


def revoke_approved_delivery_access(access_id: str, admin_token: str = "", actor: str = "admin") -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to revoke a client delivery link.", "admin_write": admin}
    record = _get_record(str(access_id or ""))
    if not record or record.get("record_type") != ACCESS_RECORD_TYPE:
        return {"status": "not_found", "access_id": access_id}
    revoked_at = _iso(_now())
    updated = _revoke_record(str(access_id), revoked_at, str(actor or "admin")[:160])
    if not updated:
        return {"status": "not_found", "access_id": access_id}
    STORE.audit(
        "approved_delivery.access_revoked",
        {
            "access_id": access_id,
            "run_id": updated.get("run_id"),
            "report_id": updated.get("report_id"),
            "actor": str(actor or "admin")[:160],
        },
        customer_id=updated.get("customer_id"),
        project_id=updated.get("project_id"),
    )
    return {"status": "revoked", "access": _public_record(updated)}
