from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from nico.admin_security import require_admin_write
from nico.storage import STORE, StorageAdapter, utc_now
from nico.storage_schema_readiness import storage_schema_contract

BACKUP_RESTORE_SCHEMA = "nico.backup_restore_readiness.v1"
BACKUP_EVIDENCE_ACTION = "operations.backup_evidence"
RESTORE_DRILL_ACTION = "operations.restore_drill"
BACKUP_RESTORE_STATUS_ROUTE = ("GET", "/operations/backup-restore")
BACKUP_EVIDENCE_ROUTE = ("POST", "/operations/backup-restore/backup-evidence")
RESTORE_DRILL_ROUTE = ("POST", "/operations/backup-restore/restore-drill")
REQUIRED_BACKUP_RESTORE_ROUTES = {
    BACKUP_RESTORE_STATUS_ROUTE,
    BACKUP_EVIDENCE_ROUTE,
    RESTORE_DRILL_ROUTE,
}
REQUIRED_BACKUP_RESTORE_ROUTE_NAMES = {
    "GET /operations/backup-restore",
    "POST /operations/backup-restore/backup-evidence",
    "POST /operations/backup-restore/restore-drill",
}

DEFAULT_BACKUP_MAX_AGE_HOURS = 36
DEFAULT_RESTORE_MAX_AGE_DAYS = 30
DEFAULT_MIN_RETENTION_DAYS = 7
DEFAULT_MIN_PITR_HOURS = 24
MAX_AUDIT_RECORDS = 5000
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,119}$")


class BackupEvidenceRequest(BaseModel):
    completed_at: str = Field(min_length=16, max_length=40)
    provider: str = Field(min_length=1, max_length=120)
    backup_reference_sha256: str = Field(min_length=64, max_length=64)
    successful: bool
    encrypted_at_rest_verified: bool
    separated_copy_verified: bool
    retention_days: int = Field(ge=0, le=3650)
    pitr_applicable: bool = True
    pitr_window_hours: int = Field(default=0, ge=0, le=87600)
    actor: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=1000)


class RestoreDrillRequest(BaseModel):
    completed_at: str = Field(min_length=16, max_length=40)
    provider: str = Field(min_length=1, max_length=120)
    source_backup_reference_sha256: str = Field(min_length=64, max_length=64)
    restored_record_set_sha256: str = Field(min_length=64, max_length=64)
    successful: bool
    isolated_nonproduction_target_verified: bool
    schema_contract_sha256: str = Field(min_length=64, max_length=64)
    required_tables_verified: bool
    application_read_verified: bool
    actor: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=1000)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_datetime(value: Any) -> datetime | None:
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


def _iso(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "blocked",
                "code": "invalid_completed_at",
                "message": "completed_at must be a valid ISO-8601 timestamp.",
            },
        )
    if parsed > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=422,
            detail={
                "status": "blocked",
                "code": "future_completed_at",
                "message": "completed_at cannot be in the future.",
            },
        )
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(value: Any, field_name: str) -> str:
    text = str(value or "").strip().lower()
    if not _HEX_64.fullmatch(text):
        raise HTTPException(
            status_code=422,
            detail={
                "status": "blocked",
                "code": "invalid_sha256",
                "field": field_name,
                "message": f"{field_name} must be a lowercase 64-character SHA-256 value.",
            },
        )
    return text


def _label(value: Any, field_name: str) -> str:
    text = " ".join(str(value or "").split())[:120]
    if not _SAFE_LABEL.fullmatch(text):
        raise HTTPException(
            status_code=422,
            detail={
                "status": "blocked",
                "code": "invalid_safe_label",
                "field": field_name,
                "message": f"{field_name} must be a bounded label without URLs, credentials, or control characters.",
            },
        )
    return text


def _note_identity(note: Any) -> dict[str, Any]:
    text = str(note or "")[:1000]
    return {
        "note_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "note_length": len(text),
        "note_retained": False,
    }


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _storage_state(active: StorageAdapter) -> tuple[str, bool]:
    try:
        status = dict(active.status())
    except Exception:
        return "unknown", False
    return str(status.get("adapter") or "unknown"), bool(status.get("persistence_available"))


def _require_operator(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "status": "blocked",
            "code": "operator_authentication_required",
            "message": "Operator authentication is required for backup and restore evidence.",
            "admin_write": status,
        },
    )


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def backup_max_age_hours() -> int:
    return _bounded_env_int("NICO_BACKUP_MAX_AGE_HOURS", DEFAULT_BACKUP_MAX_AGE_HOURS, 1, 168)


def restore_max_age_days() -> int:
    return _bounded_env_int("NICO_RESTORE_DRILL_MAX_AGE_DAYS", DEFAULT_RESTORE_MAX_AGE_DAYS, 1, 365)


def minimum_retention_days() -> int:
    return _bounded_env_int("NICO_BACKUP_MIN_RETENTION_DAYS", DEFAULT_MIN_RETENTION_DAYS, 1, 3650)


def minimum_pitr_hours() -> int:
    return _bounded_env_int("NICO_BACKUP_MIN_PITR_HOURS", DEFAULT_MIN_PITR_HOURS, 1, 8760)


def _record_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return dict(payload) if isinstance(payload, dict) else {}


def _records_for_action(
    action: str,
    *,
    store: StorageAdapter | None = None,
    customer_id: str | None = None,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    active = _store(store)
    records = active.list("audit_log", customer_id=customer_id, project_id=project_id)[-MAX_AUDIT_RECORDS:]
    matched: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict) or str(item.get("action") or "") != action:
            continue
        payload = _record_payload(item)
        if payload.get("artifact_schema") == BACKUP_RESTORE_SCHEMA:
            matched.append(payload)
    return matched


def _latest(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    ordered = sorted(
        records,
        key=lambda item: _parse_datetime(item.get("completed_at")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    return dict(ordered[-1]) if ordered else None


def _record(
    action: str,
    payload: dict[str, Any],
    *,
    store: StorageAdapter | None = None,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
) -> dict[str, Any]:
    active = _store(store)
    adapter, durable = _storage_state(active)
    if adapter != "postgres" or not durable:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "blocked",
                "code": "durable_postgres_required",
                "message": "Backup and restore evidence cannot be represented as durable while Postgres persistence is unavailable.",
            },
        )
    active.audit(action, payload, customer_id=customer_id, project_id=project_id)
    return dict(payload)


def build_backup_evidence(request: BackupEvidenceRequest) -> dict[str, Any]:
    contract = storage_schema_contract()
    payload: dict[str, Any] = {
        "artifact_schema": BACKUP_RESTORE_SCHEMA,
        "kind": "backup_evidence",
        "completed_at": _iso(request.completed_at),
        "provider": _label(request.provider, "provider"),
        "backup_reference_sha256": _sha256(request.backup_reference_sha256, "backup_reference_sha256"),
        "successful": bool(request.successful),
        "encrypted_at_rest_verified": bool(request.encrypted_at_rest_verified),
        "separated_copy_verified": bool(request.separated_copy_verified),
        "retention_days": int(request.retention_days),
        "pitr_applicable": bool(request.pitr_applicable),
        "pitr_window_hours": int(request.pitr_window_hours),
        "actor": _label(request.actor, "actor"),
        "schema_contract_version": contract["version"],
        "schema_contract_sha256": contract["contract_sha256"],
        "recorded_at": utc_now(),
        "automatic_backup": False,
        "client_delivery_allowed": False,
        **_note_identity(request.note),
    }
    payload["evidence_sha256"] = _canonical_hash(payload)
    return payload


def build_restore_drill(request: RestoreDrillRequest) -> dict[str, Any]:
    contract = storage_schema_contract()
    payload: dict[str, Any] = {
        "artifact_schema": BACKUP_RESTORE_SCHEMA,
        "kind": "restore_drill",
        "completed_at": _iso(request.completed_at),
        "provider": _label(request.provider, "provider"),
        "source_backup_reference_sha256": _sha256(request.source_backup_reference_sha256, "source_backup_reference_sha256"),
        "restored_record_set_sha256": _sha256(request.restored_record_set_sha256, "restored_record_set_sha256"),
        "successful": bool(request.successful),
        "isolated_nonproduction_target_verified": bool(request.isolated_nonproduction_target_verified),
        "schema_contract_sha256": _sha256(request.schema_contract_sha256, "schema_contract_sha256"),
        "required_tables_verified": bool(request.required_tables_verified),
        "application_read_verified": bool(request.application_read_verified),
        "actor": _label(request.actor, "actor"),
        "expected_schema_contract_version": contract["version"],
        "expected_schema_contract_sha256": contract["contract_sha256"],
        "recorded_at": utc_now(),
        "automatic_restore": False,
        "isolated_restore_only": True,
        "client_delivery_allowed": False,
        **_note_identity(request.note),
    }
    payload["evidence_sha256"] = _canonical_hash(payload)
    return payload


def record_backup_evidence(
    request: BackupEvidenceRequest,
    *,
    store: StorageAdapter | None = None,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
) -> dict[str, Any]:
    payload = build_backup_evidence(request)
    return _record(
        BACKUP_EVIDENCE_ACTION,
        payload,
        store=store,
        customer_id=customer_id,
        project_id=project_id,
    )


def record_restore_drill(
    request: RestoreDrillRequest,
    *,
    store: StorageAdapter | None = None,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
) -> dict[str, Any]:
    payload = build_restore_drill(request)
    return _record(
        RESTORE_DRILL_ACTION,
        payload,
        store=store,
        customer_id=customer_id,
        project_id=project_id,
    )


def _age_seconds(completed_at: Any, *, now: datetime) -> float | None:
    completed = _parse_datetime(completed_at)
    if completed is None:
        return None
    return max(0.0, (now - completed).total_seconds())


def backup_restore_status(
    *,
    store: StorageAdapter | None = None,
    customer_id: str | None = None,
    project_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active = _store(store)
    current = now or datetime.now(timezone.utc)
    adapter, durable = _storage_state(active)
    contract = storage_schema_contract()
    backup = _latest(_records_for_action(
        BACKUP_EVIDENCE_ACTION,
        store=active,
        customer_id=customer_id,
        project_id=project_id,
    ))
    restore = _latest(_records_for_action(
        RESTORE_DRILL_ACTION,
        store=active,
        customer_id=customer_id,
        project_id=project_id,
    ))

    blockers: list[str] = []
    warnings: list[str] = []
    backup_age = _age_seconds(backup.get("completed_at"), now=current) if backup else None
    restore_age = _age_seconds(restore.get("completed_at"), now=current) if restore else None

    if adapter != "postgres" or not durable:
        blockers.append("durable_postgres_required")
    if not backup:
        blockers.append("backup_evidence_missing")
    else:
        if not backup.get("successful"):
            blockers.append("latest_backup_failed")
        if not backup.get("encrypted_at_rest_verified"):
            blockers.append("backup_encryption_unverified")
        if not backup.get("separated_copy_verified"):
            blockers.append("backup_separated_copy_unverified")
        if int(backup.get("retention_days") or 0) < minimum_retention_days():
            blockers.append("backup_retention_insufficient")
        if backup_age is None or backup_age > backup_max_age_hours() * 3600:
            blockers.append("backup_evidence_stale")
        if backup.get("schema_contract_sha256") != contract["contract_sha256"]:
            blockers.append("backup_schema_contract_stale")
        if backup.get("pitr_applicable"):
            if int(backup.get("pitr_window_hours") or 0) < minimum_pitr_hours():
                blockers.append("pitr_window_insufficient")
        else:
            warnings.append("pitr_not_applicable_or_unverified")

    if not restore:
        blockers.append("restore_drill_missing")
    else:
        if not restore.get("successful"):
            blockers.append("latest_restore_drill_failed")
        if not restore.get("isolated_nonproduction_target_verified"):
            blockers.append("restore_target_isolation_unverified")
        if not restore.get("required_tables_verified"):
            blockers.append("restored_tables_unverified")
        if not restore.get("application_read_verified"):
            blockers.append("restored_application_read_unverified")
        if restore.get("schema_contract_sha256") != contract["contract_sha256"]:
            blockers.append("restore_schema_contract_mismatch")
        if restore_age is None or restore_age > restore_max_age_days() * 86400:
            blockers.append("restore_drill_stale")
        if backup and restore.get("source_backup_reference_sha256") != backup.get("backup_reference_sha256"):
            blockers.append("restore_source_backup_mismatch")

    status = "blocked" if blockers else "degraded" if warnings else "ready"
    return {
        "artifact_schema": BACKUP_RESTORE_SCHEMA,
        "status": status,
        "backup_restore_ready": status == "ready",
        "adapter": adapter,
        "persistence_available": durable,
        "customer_id": customer_id,
        "project_id": project_id,
        "thresholds": {
            "backup_max_age_hours": backup_max_age_hours(),
            "restore_drill_max_age_days": restore_max_age_days(),
            "minimum_retention_days": minimum_retention_days(),
            "minimum_pitr_hours": minimum_pitr_hours(),
        },
        "latest_backup": {
            "present": bool(backup),
            "completed_at": backup.get("completed_at") if backup else None,
            "age_seconds": round(backup_age, 3) if backup_age is not None else None,
            "provider": backup.get("provider") if backup else None,
            "backup_reference_sha256": backup.get("backup_reference_sha256") if backup else None,
            "evidence_sha256": backup.get("evidence_sha256") if backup else None,
            "successful": backup.get("successful") if backup else None,
            "encrypted_at_rest_verified": backup.get("encrypted_at_rest_verified") if backup else None,
            "separated_copy_verified": backup.get("separated_copy_verified") if backup else None,
            "retention_days": backup.get("retention_days") if backup else None,
            "pitr_applicable": backup.get("pitr_applicable") if backup else None,
            "pitr_window_hours": backup.get("pitr_window_hours") if backup else None,
        },
        "latest_restore_drill": {
            "present": bool(restore),
            "completed_at": restore.get("completed_at") if restore else None,
            "age_seconds": round(restore_age, 3) if restore_age is not None else None,
            "provider": restore.get("provider") if restore else None,
            "source_backup_reference_sha256": restore.get("source_backup_reference_sha256") if restore else None,
            "restored_record_set_sha256": restore.get("restored_record_set_sha256") if restore else None,
            "evidence_sha256": restore.get("evidence_sha256") if restore else None,
            "successful": restore.get("successful") if restore else None,
            "isolated_nonproduction_target_verified": restore.get("isolated_nonproduction_target_verified") if restore else None,
            "required_tables_verified": restore.get("required_tables_verified") if restore else None,
            "application_read_verified": restore.get("application_read_verified") if restore else None,
            "schema_contract_matches": bool(restore and restore.get("schema_contract_sha256") == contract["contract_sha256"]),
        },
        "schema_contract_version": contract["version"],
        "schema_contract_sha256": contract["contract_sha256"],
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "checked_at": current.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "automatic_backup": False,
        "automatic_restore": False,
        "destructive_action_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "next_action": (
            "Backup and isolated restore evidence are current and match the active storage schema contract."
            if status == "ready"
            else "Record real reviewed backup evidence and a successful isolated restore drill; do not represent provider capability or documentation as completed operational evidence."
        ),
        "guardrail": "This control records bounded evidence only. It does not create backups, execute restores, authorize failover, mutate production data, or permit client delivery.",
    }


def backup_restore_status_response(
    customer_id: str | None = Query(default=None, max_length=120),
    project_id: str | None = Query(default=None, max_length=120),
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    return backup_restore_status(customer_id=customer_id, project_id=project_id)


def backup_evidence_response(
    request: BackupEvidenceRequest,
    customer_id: str = Query(default="default_customer", min_length=1, max_length=120),
    project_id: str = Query(default="default_project", min_length=1, max_length=120),
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    record = record_backup_evidence(request, customer_id=customer_id, project_id=project_id)
    return {"status": "recorded", "backup_evidence": record, "backup_restore": backup_restore_status(customer_id=customer_id, project_id=project_id)}


def restore_drill_response(
    request: RestoreDrillRequest,
    customer_id: str = Query(default="default_customer", min_length=1, max_length=120),
    project_id: str = Query(default="default_project", min_length=1, max_length=120),
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    record = record_restore_drill(request, customer_id=customer_id, project_id=project_id)
    return {"status": "recorded", "restore_drill": record, "backup_restore": backup_restore_status(customer_id=customer_id, project_id=project_id)}


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def install_backup_restore_readiness(target: FastAPI) -> dict[str, Any]:
    existing = _route_pairs(target)
    present = existing & REQUIRED_BACKUP_RESTORE_ROUTES
    if present and present != REQUIRED_BACKUP_RESTORE_ROUTES:
        raise RuntimeError(
            f"Partial backup/restore route registration detected; missing={sorted(REQUIRED_BACKUP_RESTORE_ROUTES - present)}"
        )
    if present == REQUIRED_BACKUP_RESTORE_ROUTES:
        return {"installed": True, "idempotent_reuse": True, "routes": sorted(REQUIRED_BACKUP_RESTORE_ROUTE_NAMES)}

    target.add_api_route(
        BACKUP_RESTORE_STATUS_ROUTE[1],
        backup_restore_status_response,
        methods=[BACKUP_RESTORE_STATUS_ROUTE[0]],
        tags=["operations"],
    )
    target.add_api_route(
        BACKUP_EVIDENCE_ROUTE[1],
        backup_evidence_response,
        methods=[BACKUP_EVIDENCE_ROUTE[0]],
        tags=["operations"],
    )
    target.add_api_route(
        RESTORE_DRILL_ROUTE[1],
        restore_drill_response,
        methods=[RESTORE_DRILL_ROUTE[0]],
        tags=["operations"],
    )
    target.openapi_schema = None
    return {"installed": True, "idempotent_reuse": False, "routes": sorted(REQUIRED_BACKUP_RESTORE_ROUTE_NAMES)}


__all__ = [
    "BACKUP_RESTORE_SCHEMA",
    "BACKUP_EVIDENCE_ACTION",
    "RESTORE_DRILL_ACTION",
    "REQUIRED_BACKUP_RESTORE_ROUTES",
    "REQUIRED_BACKUP_RESTORE_ROUTE_NAMES",
    "BackupEvidenceRequest",
    "RestoreDrillRequest",
    "build_backup_evidence",
    "build_restore_drill",
    "record_backup_evidence",
    "record_restore_drill",
    "backup_restore_status",
    "install_backup_restore_readiness",
]
