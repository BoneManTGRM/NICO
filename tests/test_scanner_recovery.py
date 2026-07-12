from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.scanner_recovery as recovery
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES
from nico.scanner_recovery import (
    RECOVERY_REQUIRED_STATUS,
    REQUIRED_SCANNER_RECOVERY_ROUTE_NAMES,
    SCANNER_RECOVERY_ROUTE,
    SCANNER_RESUME_ROUTE,
    atomic_scanner_transition,
    install_scanner_recovery,
    reconcile_interrupted_scanner_runs,
    resume_interrupted_scanner_run,
    scanner_is_stale,
    scanner_recovery_inventory,
)


NOW = datetime(2026, 7, 12, 20, 45, 0, tzinfo=timezone.utc)


def _scan(
    scan_id: str = "scan_1234567890abcdef",
    *,
    status: str = "running",
    updated_at: str = "2026-07-12T20:20:00Z",
) -> dict[str, Any]:
    return {
        "scan_id": scan_id,
        "id": scan_id,
        "run_id": "midrun_1234567890abcdef",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "repository": "BoneManTGRM/NICO",
        "status": status,
        "created_at": "2026-07-12T20:00:00Z",
        "updated_at": updated_at,
        "authorized_by": "customer_owner",
        "authorization_scope": "repository assessment only",
        "draft_pr_creation_allowed": False,
        "tools_requested": ["pip-audit", "bandit"],
        "tools_run": [],
        "human_review_required": True,
    }


class _MemoryStore:
    def __init__(self, records: list[dict[str, Any]], *, durable: bool = False) -> None:
        self.records = {str(item["scan_id"]): deepcopy(item) for item in records}
        self.durable = durable
        self.audit_events: list[tuple[str, dict[str, Any]]] = []
        self.adapter = self

    def status(self) -> dict[str, Any]:
        return {
            "adapter": "postgres" if self.durable else "memory",
            "persistence_available": self.durable,
        }

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        assert table == "scanner_runs"
        value = self.records.get(item_id)
        return deepcopy(value) if value else None

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert table == "scanner_runs"
        self.records[item_id] = deepcopy(payload)
        return deepcopy(payload)

    def list(self, table: str, customer_id=None, project_id=None) -> list[dict[str, Any]]:
        assert table == "scanner_runs"
        values = list(self.records.values())
        if customer_id:
            values = [item for item in values if item.get("customer_id") == customer_id]
        if project_id:
            values = [item for item in values if item.get("project_id") == project_id]
        return deepcopy(values)

    def audit(self, action: str, payload: dict[str, Any], customer_id=None, project_id=None) -> dict[str, Any]:
        self.audit_events.append((action, deepcopy(payload)))
        return {"action": action, "payload": deepcopy(payload)}


class _FakeJsonb:
    def __init__(self, value: dict[str, Any]) -> None:
        self.obj = deepcopy(value)


class _PostgresAdapter:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = {str(item["scan_id"]): deepcopy(item) for item in records}
        self._jsonb = _FakeJsonb
        self.transition_calls = 0

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        assert "UPDATE scanner_runs" in sql
        self.transition_calls += 1
        new_status, patch_jsonb, updated_at, scan_id, expected = params
        current = self.records.get(str(scan_id))
        if not current or str(current.get("status")) not in set(expected):
            return []
        current.update(deepcopy(patch_jsonb.obj))
        current["status"] = new_status
        current["updated_at"] = updated_at
        self.records[str(scan_id)] = current
        return [
            {
                "scan_id": scan_id,
                "customer_id": current.get("customer_id"),
                "project_id": current.get("project_id"),
                "status": new_status,
                "payload": deepcopy(current),
                "created_at": current.get("created_at"),
                "updated_at": updated_at,
            }
        ]

    def _normalize_jsonb(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        assert table == "scanner_runs"
        payload = deepcopy(row["payload"])
        payload.update(
            {
                "scan_id": row["scan_id"],
                "customer_id": row["customer_id"],
                "project_id": row["project_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
        return payload


class _PostgresStore(_MemoryStore):
    def __init__(self, records: list[dict[str, Any]]) -> None:
        super().__init__(records, durable=True)
        self.adapter = _PostgresAdapter(records)
        self.records = self.adapter.records


class _FakeThread:
    starts = 0
    targets: list[Any] = []

    def __init__(self, *, target, args, daemon) -> None:
        assert daemon is True
        self.target = target
        self.args = args
        _FakeThread.targets.append((target, args))

    def start(self) -> None:
        _FakeThread.starts += 1


def test_scanner_staleness_requires_active_status_and_age_evidence() -> None:
    stale = _scan(status="running", updated_at="2026-07-12T20:20:00Z")
    fresh = _scan(status="running", updated_at="2026-07-12T20:44:30Z")
    complete = _scan(status="complete", updated_at="2026-07-12T20:20:00Z")

    assert scanner_is_stale(stale, stale_seconds=600, now=NOW) is True
    assert scanner_is_stale(fresh, stale_seconds=600, now=NOW) is False
    assert scanner_is_stale(complete, stale_seconds=600, now=NOW) is False


def test_memory_fallback_is_not_reconciled_as_durable_recovery() -> None:
    store = _MemoryStore([_scan()], durable=False)

    result = reconcile_interrupted_scanner_runs(store=store, stale_seconds=600, now=NOW)

    assert result["status"] == "blocked"
    assert result["blockers"] == ["durable_postgres_required"]
    assert store.records["scan_1234567890abcdef"]["status"] == "running"


def test_stale_postgres_scanner_becomes_recovery_required_but_fresh_work_is_preserved() -> None:
    stale = _scan("scan_1234567890abcdef", updated_at="2026-07-12T20:20:00Z")
    fresh = _scan("scan_abcdef1234567890", updated_at="2026-07-12T20:44:30Z")
    store = _PostgresStore([stale, fresh])

    result = reconcile_interrupted_scanner_runs(store=store, stale_seconds=600, now=NOW)

    assert result["status"] == "attention_required"
    assert result["reconciled"] == 1
    assert result["fresh_active"] == 1
    assert result["recovery_required"] == 1
    recovered = store.records[stale["scan_id"]]
    assert recovered["status"] == RECOVERY_REQUIRED_STATUS
    assert recovered["recovery"]["previous_status"] == "running"
    assert recovered["recovery"]["resume_allowed"] is True
    assert recovered["recovery"]["automatic_resume"] is False
    assert store.records[fresh["scan_id"]]["status"] == "running"
    assert store.audit_events[0][0] == "scanner.recovery_required"


def test_postgres_transition_is_compare_and_set() -> None:
    store = _PostgresStore([_scan(status=RECOVERY_REQUIRED_STATUS)])

    first = atomic_scanner_transition(
        "scan_1234567890abcdef",
        {RECOVERY_REQUIRED_STATUS},
        "queued",
        {"updated_at": "2026-07-12T20:46:00Z", "claim": "one"},
        store=store,
    )
    second = atomic_scanner_transition(
        "scan_1234567890abcdef",
        {RECOVERY_REQUIRED_STATUS},
        "queued",
        {"updated_at": "2026-07-12T20:46:01Z", "claim": "two"},
        store=store,
    )

    assert first is not None
    assert first["status"] == "queued"
    assert first["claim"] == "one"
    assert second is None
    assert store.records["scan_1234567890abcdef"]["claim"] == "one"


def test_resume_claim_reuses_same_scan_id_and_duplicate_call_does_not_start_second_thread(monkeypatch) -> None:
    _FakeThread.starts = 0
    _FakeThread.targets = []
    record = _scan(status=RECOVERY_REQUIRED_STATUS)
    record["recovery"] = {
        "state": RECOVERY_REQUIRED_STATUS,
        "reason": "stale_process_local_execution",
        "attempt": 0,
        "resume_allowed": True,
    }
    store = _PostgresStore([record])

    first = resume_interrupted_scanner_run(
        record["scan_id"],
        actor="operator-one",
        store=store,
        thread_factory=_FakeThread,
    )
    second = resume_interrupted_scanner_run(
        record["scan_id"],
        actor="operator-two",
        store=store,
        thread_factory=_FakeThread,
    )

    assert first["status"] == "queued"
    assert first["idempotent_reuse"] is False
    assert first["resume"]["same_scan_id"] is True
    assert first["scan"]["scan_id"] == record["scan_id"]
    assert second["status"] == "queued"
    assert second["idempotent_reuse"] is True
    assert _FakeThread.starts == 1
    assert store.records[record["scan_id"]]["recovery"]["attempt"] == 1


def test_resume_is_blocked_when_original_authorization_metadata_is_missing() -> None:
    record = _scan(status=RECOVERY_REQUIRED_STATUS)
    record["authorized_by"] = ""
    store = _PostgresStore([record])

    result = resume_interrupted_scanner_run(
        record["scan_id"],
        actor="operator",
        store=store,
        thread_factory=_FakeThread,
    )

    assert result["status"] == "blocked"
    assert result["code"] == "authorized_by_missing"
    assert store.records[record["scan_id"]]["status"] == RECOVERY_REQUIRED_STATUS


def test_inventory_is_bounded_and_excludes_scanner_output() -> None:
    records = []
    for index in range(3):
        item = _scan(f"scan_{index:016d}", status=RECOVERY_REQUIRED_STATUS)
        item["scanner_results"] = [{"safe_output_preview": "sensitive-output"}]
        records.append(item)
    store = _MemoryStore(records, durable=False)

    result = scanner_recovery_inventory(store=store, limit=2)
    rendered = repr(result)

    assert result["counts"]["recovery_required"] == 3
    assert len(result["recovery_required"]) == 2
    assert "scanner_results" not in rendered
    assert "sensitive-output" not in rendered
    assert result["client_delivery_allowed"] is False


def test_routes_require_admin_validate_limits_and_install_idempotently(monkeypatch) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    monkeypatch.setattr(
        recovery,
        "reconcile_interrupted_scanner_runs",
        lambda **kwargs: {
            "artifact_schema": recovery.SCANNER_RECOVERY_SCHEMA,
            "status": "clear",
            "recovery_required": 0,
            "automatic_resume": False,
        },
    )
    monkeypatch.setattr(
        recovery,
        "scanner_recovery_inventory",
        lambda **kwargs: {
            "artifact_schema": recovery.SCANNER_RECOVERY_SCHEMA,
            "status": "clear",
            "counts": {"recovery_required": 0},
            "automatic_resume": False,
            "client_delivery_allowed": False,
        },
    )

    app = FastAPI()
    first = install_scanner_recovery(app)
    second = install_scanner_recovery(app)
    client = TestClient(app)

    denied = client.get("/operations/recovery")
    assert denied.status_code == 403
    invalid = client.get(
        "/operations/recovery?limit=501",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert invalid.status_code == 400
    allowed = client.get(
        "/operations/recovery?refresh=true&limit=100",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "clear"

    route_pairs = {
        (str(method).upper(), str(getattr(route, "path", "")))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert first["routes_reused"] is False
    assert second["routes_reused"] is True
    assert SCANNER_RECOVERY_ROUTE in route_pairs
    assert SCANNER_RESUME_ROUTE in route_pairs
    assert REQUIRED_SCANNER_RECOVERY_ROUTE_NAMES <= REQUIRED_OPERATION_ROUTES
