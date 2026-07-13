from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from nico.backup_restore_readiness import (
    BACKUP_EVIDENCE_ACTION,
    RESTORE_DRILL_ACTION,
    BackupEvidenceRequest,
    RestoreDrillRequest,
    backup_restore_status,
    build_backup_evidence,
    build_restore_drill,
    record_backup_evidence,
    record_restore_drill,
)
from nico.storage_schema_readiness import storage_schema_contract


class FakeStore:
    def __init__(self, *, durable: bool = True) -> None:
        self.durable = durable
        self.records: list[dict] = []

    def status(self) -> dict:
        return {
            "adapter": "postgres" if self.durable else "memory",
            "persistence_available": self.durable,
        }

    def list(self, table: str, customer_id: str | None = None, project_id: str | None = None) -> list[dict]:
        assert table == "audit_log"
        records = self.records
        if customer_id:
            records = [item for item in records if item.get("customer_id") == customer_id]
        if project_id:
            records = [item for item in records if item.get("project_id") == project_id]
        return deepcopy(records)

    def audit(self, action: str, payload: dict, customer_id: str | None = None, project_id: str | None = None) -> dict:
        record = {
            "action": action,
            "payload": deepcopy(payload),
            "customer_id": customer_id,
            "project_id": project_id,
        }
        self.records.append(record)
        return deepcopy(record)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _backup_request(completed_at: datetime, **overrides) -> BackupEvidenceRequest:
    data = {
        "completed_at": _iso(completed_at),
        "provider": "Railway PostgreSQL",
        "backup_reference_sha256": "a" * 64,
        "successful": True,
        "encrypted_at_rest_verified": True,
        "separated_copy_verified": True,
        "retention_days": 14,
        "pitr_applicable": True,
        "pitr_window_hours": 72,
        "actor": "Operations Reviewer",
        "note": "Reviewed against provider evidence without retaining the provider payload.",
    }
    data.update(overrides)
    return BackupEvidenceRequest(**data)


def _restore_request(completed_at: datetime, **overrides) -> RestoreDrillRequest:
    contract = storage_schema_contract()
    data = {
        "completed_at": _iso(completed_at),
        "provider": "Railway PostgreSQL",
        "source_backup_reference_sha256": "a" * 64,
        "restored_record_set_sha256": "b" * 64,
        "successful": True,
        "isolated_nonproduction_target_verified": True,
        "schema_contract_sha256": contract["contract_sha256"],
        "required_tables_verified": True,
        "application_read_verified": True,
        "actor": "Operations Reviewer",
        "note": "Isolated target and bounded application reads were reviewed.",
    }
    data.update(overrides)
    return RestoreDrillRequest(**data)


def test_evidence_identity_is_hash_bound_and_raw_note_is_not_retained() -> None:
    current = _now() - timedelta(minutes=5)
    secret_note = "review note with sensitive context that must not be retained"
    backup = build_backup_evidence(_backup_request(current, note=secret_note))
    restore = build_restore_drill(_restore_request(current, note=secret_note))

    for evidence in (backup, restore):
        identity = evidence["evidence_sha256"]
        unhashed = dict(evidence)
        unhashed.pop("evidence_sha256")
        assert len(identity) == 64
        assert identity == __import__("hashlib").sha256(
            json.dumps(unhashed, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
        ).hexdigest()
        assert evidence["note_retained"] is False
        assert evidence["note_length"] == len(secret_note)
        assert secret_note not in json.dumps(evidence)
        assert evidence["client_delivery_allowed"] is False


def test_current_verified_backup_and_restore_are_ready() -> None:
    store = FakeStore()
    current = _now()
    record_backup_evidence(_backup_request(current - timedelta(hours=1)), store=store)
    record_restore_drill(_restore_request(current - timedelta(hours=1)), store=store)

    result = backup_restore_status(store=store, now=current)

    assert result["status"] == "ready"
    assert result["backup_restore_ready"] is True
    assert result["blockers"] == []
    assert result["latest_backup"]["present"] is True
    assert result["latest_restore_drill"]["present"] is True
    assert result["automatic_backup"] is False
    assert result["automatic_restore"] is False
    assert result["destructive_action_allowed"] is False
    assert result["client_delivery_allowed"] is False


def test_missing_evidence_and_memory_fallback_never_appear_ready() -> None:
    result = backup_restore_status(store=FakeStore(durable=False), now=_now())

    assert result["status"] == "blocked"
    assert result["backup_restore_ready"] is False
    assert "durable_postgres_required" in result["blockers"]
    assert "backup_evidence_missing" in result["blockers"]
    assert "restore_drill_missing" in result["blockers"]


def test_stale_backup_and_restore_drill_are_explicit_blockers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NICO_BACKUP_MAX_AGE_HOURS", "24")
    monkeypatch.setenv("NICO_RESTORE_DRILL_MAX_AGE_DAYS", "7")
    current = _now()
    store = FakeStore()
    record_backup_evidence(_backup_request(current - timedelta(hours=25)), store=store)
    record_restore_drill(_restore_request(current - timedelta(days=8)), store=store)

    result = backup_restore_status(store=store, now=current)

    assert "backup_evidence_stale" in result["blockers"]
    assert "restore_drill_stale" in result["blockers"]
    assert result["status"] == "blocked"


def test_failed_incomplete_and_contract_mismatched_evidence_is_not_green() -> None:
    current = _now()
    store = FakeStore()
    record_backup_evidence(
        _backup_request(
            current - timedelta(hours=1),
            successful=False,
            encrypted_at_rest_verified=False,
            separated_copy_verified=False,
            retention_days=1,
            pitr_window_hours=1,
        ),
        store=store,
    )
    record_restore_drill(
        _restore_request(
            current - timedelta(hours=1),
            source_backup_reference_sha256="c" * 64,
            successful=False,
            isolated_nonproduction_target_verified=False,
            schema_contract_sha256="d" * 64,
            required_tables_verified=False,
            application_read_verified=False,
        ),
        store=store,
    )

    blockers = set(backup_restore_status(store=store, now=current)["blockers"])

    assert {
        "latest_backup_failed",
        "backup_encryption_unverified",
        "backup_separated_copy_unverified",
        "backup_retention_insufficient",
        "pitr_window_insufficient",
        "latest_restore_drill_failed",
        "restore_target_isolation_unverified",
        "restored_tables_unverified",
        "restored_application_read_unverified",
        "restore_schema_contract_mismatch",
        "restore_source_backup_mismatch",
    } <= blockers


def test_scope_filters_do_not_mix_customer_evidence() -> None:
    current = _now()
    store = FakeStore()
    record_backup_evidence(
        _backup_request(current - timedelta(hours=1)),
        store=store,
        customer_id="customer_a",
        project_id="project_a",
    )
    record_restore_drill(
        _restore_request(current - timedelta(hours=1)),
        store=store,
        customer_id="customer_a",
        project_id="project_a",
    )

    verified = backup_restore_status(
        store=store,
        customer_id="customer_a",
        project_id="project_a",
        now=current,
    )
    missing = backup_restore_status(
        store=store,
        customer_id="customer_b",
        project_id="project_b",
        now=current,
    )

    assert verified["status"] == "ready"
    assert "backup_evidence_missing" in missing["blockers"]
    assert "restore_drill_missing" in missing["blockers"]


def test_recording_is_blocked_without_durable_postgres() -> None:
    with pytest.raises(HTTPException) as caught:
        record_backup_evidence(_backup_request(_now() - timedelta(minutes=1)), store=FakeStore(durable=False))

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "durable_postgres_required"


def test_unsafe_provider_label_and_invalid_hash_are_rejected() -> None:
    with pytest.raises(HTTPException):
        build_backup_evidence(_backup_request(_now() - timedelta(minutes=1), provider="https://provider.example/backup"))
    with pytest.raises(HTTPException):
        build_backup_evidence(_backup_request(_now() - timedelta(minutes=1), backup_reference_sha256="z" * 64))


def test_audit_actions_are_distinct_and_bounded() -> None:
    current = _now()
    store = FakeStore()
    record_backup_evidence(_backup_request(current - timedelta(minutes=2)), store=store)
    record_restore_drill(_restore_request(current - timedelta(minutes=1)), store=store)

    assert [item["action"] for item in store.records] == [BACKUP_EVIDENCE_ACTION, RESTORE_DRILL_ACTION]
    serialized = json.dumps(store.records)
    assert "DATABASE_URL" not in serialized
    assert "postgresql://" not in serialized
    assert "https://" not in serialized
