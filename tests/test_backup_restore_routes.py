from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.backup_restore_readiness as backup_restore
from nico.storage_schema_readiness import storage_schema_contract


class FakeStore:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def status(self) -> dict:
        return {"adapter": "postgres", "persistence_available": True}

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


def _iso(minutes_ago: int = 1) -> str:
    value = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=minutes_ago)
    return value.isoformat().replace("+00:00", "Z")


def _backup_payload() -> dict:
    return {
        "completed_at": _iso(2),
        "provider": "Railway PostgreSQL",
        "backup_reference_sha256": "a" * 64,
        "successful": True,
        "encrypted_at_rest_verified": True,
        "separated_copy_verified": True,
        "retention_days": 14,
        "pitr_applicable": True,
        "pitr_window_hours": 72,
        "actor": "Operations Reviewer",
        "note": "Reviewed bounded provider evidence.",
    }


def _restore_payload() -> dict:
    return {
        "completed_at": _iso(1),
        "provider": "Railway PostgreSQL",
        "source_backup_reference_sha256": "a" * 64,
        "restored_record_set_sha256": "b" * 64,
        "successful": True,
        "isolated_nonproduction_target_verified": True,
        "schema_contract_sha256": storage_schema_contract()["contract_sha256"],
        "required_tables_verified": True,
        "application_read_verified": True,
        "actor": "Operations Reviewer",
        "note": "Isolated restore target was reviewed.",
    }


def _app() -> FastAPI:
    app = FastAPI()
    backup_restore.install_backup_restore_readiness(app)
    return app


def _route_pairs(app: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in app.routes:
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), str(getattr(route, "path", ""))))
    return pairs


def test_route_group_is_complete_and_idempotent() -> None:
    app = _app()
    first_count = len(app.routes)
    result = backup_restore.install_backup_restore_readiness(app)

    assert backup_restore.REQUIRED_BACKUP_RESTORE_ROUTES <= _route_pairs(app)
    assert len(app.routes) == first_count
    assert result["idempotent_reuse"] is True


def test_partial_route_group_fails_closed() -> None:
    app = FastAPI()
    app.add_api_route("/operations/backup-restore", lambda: {}, methods=["GET"])

    try:
        backup_restore.install_backup_restore_readiness(app)
    except RuntimeError as exc:
        assert "Partial backup/restore route registration" in str(exc)
    else:
        raise AssertionError("Partial route registration must fail closed")


def test_operator_authentication_is_required(monkeypatch) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "correct-token")
    monkeypatch.setattr(backup_restore, "STORE", FakeStore())
    client = TestClient(_app())

    response = client.get("/operations/backup-restore")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "operator_authentication_required"


def test_backup_and_restore_evidence_routes_record_only_explicit_evidence(monkeypatch) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "correct-token")
    store = FakeStore()
    monkeypatch.setattr(backup_restore, "STORE", store)
    client = TestClient(_app())
    headers = {"X-NICO-Admin-Token": "correct-token"}
    scope = "?customer_id=customer_a&project_id=project_a"

    backup_response = client.post(
        f"/operations/backup-restore/backup-evidence{scope}",
        headers=headers,
        json=_backup_payload(),
    )
    restore_response = client.post(
        f"/operations/backup-restore/restore-drill{scope}",
        headers=headers,
        json=_restore_payload(),
    )
    status_response = client.get(
        f"/operations/backup-restore{scope}",
        headers=headers,
    )

    assert backup_response.status_code == 200
    assert backup_response.json()["status"] == "recorded"
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "recorded"
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "ready"
    assert status_response.json()["automatic_backup"] is False
    assert status_response.json()["automatic_restore"] is False
    assert status_response.json()["destructive_action_allowed"] is False
    assert [item["action"] for item in store.records] == [
        backup_restore.BACKUP_EVIDENCE_ACTION,
        backup_restore.RESTORE_DRILL_ACTION,
    ]


def test_recording_rejects_memory_fallback(monkeypatch) -> None:
    class MemoryStore(FakeStore):
        def status(self) -> dict:
            return {"adapter": "memory", "persistence_available": False}

    monkeypatch.setenv("NICO_ADMIN_TOKEN", "correct-token")
    monkeypatch.setattr(backup_restore, "STORE", MemoryStore())
    client = TestClient(_app())

    response = client.post(
        "/operations/backup-restore/backup-evidence",
        headers={"X-NICO-Admin-Token": "correct-token"},
        json=_backup_payload(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "durable_postgres_required"


def test_openapi_exposes_no_backup_creation_or_restore_execution_route() -> None:
    schema = _app().openapi()
    paths = set(schema["paths"])

    assert "/operations/backup-restore" in paths
    assert "/operations/backup-restore/backup-evidence" in paths
    assert "/operations/backup-restore/restore-drill" in paths
    assert not any("execute" in path or "create-backup" in path or "failover" in path for path in paths)
