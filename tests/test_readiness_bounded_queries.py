from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nico.assessment_recovery import assessment_recovery_status
from nico.backup_restore_readiness import (
    BACKUP_EVIDENCE_ACTION,
    BACKUP_RESTORE_SCHEMA,
    RESTORE_DRILL_ACTION,
    backup_restore_status,
)
from nico.scanner_recovery_status import scanner_recovery_status
from nico.scanner_recovery import scanner_recovery_inventory
from nico.storage import POSTGRES_SCHEMA
from nico.storage_schema_readiness import storage_schema_contract


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class _BoundedPostgresAdapter:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.calls: list[tuple[str, tuple]] = []

    def _query(self, sql: str, params: tuple) -> list[dict]:
        self.calls.append((" ".join(sql.split()), params))
        if "FROM scanner_runs" in sql:
            return [
                {
                    "scan_id": "scan-recovery",
                    "customer_id": "customer-a",
                    "project_id": "project-a",
                    "status": "recovery_required",
                    "created_at": _iso(self.now - timedelta(hours=2)),
                    "updated_at": _iso(self.now - timedelta(hours=1)),
                }
            ]
        if "FROM assessment_runs" in sql:
            return [
                {
                    "run_id": "run-active",
                    "customer_id": "customer-a",
                    "project_id": "project-a",
                    "workflow": "full_assessment",
                    "status": "running",
                    "created_at": _iso(self.now - timedelta(hours=2)),
                    "heartbeat_at": _iso(self.now - timedelta(minutes=1)),
                }
            ]
        if "FROM audit_log" in sql:
            action = params[0]
            contract = storage_schema_contract()
            if action == BACKUP_EVIDENCE_ACTION:
                payload = {
                    "artifact_schema": BACKUP_RESTORE_SCHEMA,
                    "completed_at": _iso(self.now - timedelta(hours=1)),
                    "provider": "Railway PostgreSQL",
                    "backup_reference_sha256": "a" * 64,
                    "successful": True,
                    "encrypted_at_rest_verified": True,
                    "separated_copy_verified": True,
                    "retention_days": 14,
                    "pitr_applicable": True,
                    "pitr_window_hours": 72,
                    "schema_contract_sha256": contract["contract_sha256"],
                }
            else:
                assert action == RESTORE_DRILL_ACTION
                payload = {
                    "artifact_schema": BACKUP_RESTORE_SCHEMA,
                    "completed_at": _iso(self.now - timedelta(minutes=30)),
                    "provider": "Railway PostgreSQL",
                    "source_backup_reference_sha256": "a" * 64,
                    "restored_record_set_sha256": "b" * 64,
                    "successful": True,
                    "isolated_nonproduction_target_verified": True,
                    "schema_contract_sha256": contract["contract_sha256"],
                    "required_tables_verified": True,
                    "application_read_verified": True,
                }
            return [
                {
                    "audit_id": f"audit-{action}",
                    "customer_id": "customer-a",
                    "project_id": "project-a",
                    "action": action,
                    "payload": payload,
                    "created_at": payload["completed_at"],
                }
            ]
        raise AssertionError(f"Unexpected query: {sql}")

    @staticmethod
    def _normalize_jsonb(table: str, row: dict) -> dict:
        assert table == "audit_log"
        payload = dict(row.get("payload") or {})
        payload.update(
            {
                "action": row.get("action"),
                "customer_id": row.get("customer_id"),
                "project_id": row.get("project_id"),
                "created_at": row.get("created_at"),
            }
        )
        return payload


class _PostgresStore:
    def __init__(self, now: datetime) -> None:
        self.adapter = _BoundedPostgresAdapter(now)

    @staticmethod
    def status() -> dict:
        return {"adapter": "postgres", "persistence_available": True}

    @staticmethod
    def list(*_args, **_kwargs) -> list[dict]:
        raise AssertionError("Readiness must not deserialize unbounded JSON payload tables")


def test_live_readiness_uses_bounded_metadata_queries_instead_of_full_payload_scans() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    store = _PostgresStore(now)

    scanner = scanner_recovery_status(store=store)
    inventory = scanner_recovery_inventory(store=store)
    assessment = assessment_recovery_status(store=store)
    backup = backup_restore_status(
        store=store,
        customer_id="customer-a",
        project_id="project-a",
        now=now,
    )

    assert scanner["status"] == "attention_required"
    assert scanner["recovery_required"] == 1
    assert inventory["counts"]["recovery_required"] == 1
    assert assessment["status"] == "clear"
    assert assessment["active"] == 1
    assert backup["status"] == "ready"
    assert len(store.adapter.calls) == 5
    for sql, _params in store.adapter.calls:
        assert "LIMIT" in sql
    assert any("SELECT scan_id" in sql and "payload" not in sql for sql, _ in store.adapter.calls)
    assert any("SELECT run_id" in sql and "payload #>>" in sql for sql, _ in store.adapter.calls)
    assert all("SELECT *" not in sql for sql, _ in store.adapter.calls)


def test_readiness_metadata_queries_have_matching_postgres_indexes() -> None:
    assert "scanner_runs_recovery_status_updated_idx" in POSTGRES_SCHEMA
    assert "ON scanner_runs (status, updated_at DESC)" in POSTGRES_SCHEMA
    assert "assessment_runs_recovery_status_created_idx" in POSTGRES_SCHEMA
    assert "ON assessment_runs (workflow, status, created_at DESC)" in POSTGRES_SCHEMA
    assert "audit_log_action_scope_created_idx" in POSTGRES_SCHEMA
    assert "ON audit_log (action, customer_id, project_id, created_at DESC)" in POSTGRES_SCHEMA
    assert "audit_log_action_created_idx" in POSTGRES_SCHEMA
    assert "ON audit_log (action, created_at DESC)" in POSTGRES_SCHEMA
