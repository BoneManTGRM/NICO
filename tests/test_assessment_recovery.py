from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.assessment_recovery as recovery
from nico.assessment_recovery import (
    ASSESSMENT_RECOVERY_INVENTORY_ROUTE,
    ASSESSMENT_RECOVERY_RESUME_ROUTE,
    RECOVERY_REQUIRED_STATUS,
    REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES,
    assessment_is_stale,
    assessment_recovery_inventory,
    atomic_assessment_transition,
    install_assessment_recovery,
    reconcile_interrupted_assessment_runs,
    resume_interrupted_assessment_run,
)
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES


NOW = datetime(2026, 7, 12, 22, 30, 0, tzinfo=timezone.utc)


def _run(
    run_id: str = "fullrun_1234567890abcdef",
    *,
    workflow: str = "full_assessment",
    status: str = "running",
    updated_at: str = "2026-07-12T22:00:00Z",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "id": run_id,
        "workflow": workflow,
        "service_tier": "mid" if workflow == "mid_assessment" else "full",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "repository": "BoneManTGRM/NICO",
        "status": status,
        "scan_id": "",
        "snapshot_id": "",
        "snapshot_commit_sha": "",
        "report_id": "report_1",
        "approval_id": "approval_1",
        "created_at": "2026-07-12T21:30:00Z",
        "updated_at": updated_at,
        "request": {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_1",
            "project_id": "project_1",
            "authorized_by": "owner",
            "authorization_scope": "repository assessment only",
            "authorization_confirmed": True,
            "authorized": True,
            "build_reports": True,
            "create_final_review_request": True,
            "auto_continue": True,
        },
        "response": {
            "status": status,
            "run_id": run_id,
            "execution_checkpoint": {
                "current_step": "scanner_worker",
                "phase": "step_started",
                "heartbeat_at": updated_at,
                "completed_steps": ["authorization", "repo_evidence"],
                "progress_sha256": "a" * 64,
            },
            "recovery": {"state": "active", "attempt": 0},
            "private_payload": "must-not-appear",
        },
    }


class _Jsonb:
    def __init__(self, value: dict[str, Any]) -> None:
        self.obj = deepcopy(value)


class _PostgresAdapter:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = {str(item["run_id"]): deepcopy(item) for item in records}
        self._jsonb = _Jsonb
        self.transition_calls = 0

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        assert "UPDATE assessment_runs" in sql
        self.transition_calls += 1
        new_status, patch_jsonb, run_id, expected = params
        current = self.records.get(str(run_id))
        if not current or str(current.get("status")) not in set(expected):
            return []
        current.update(deepcopy(patch_jsonb.obj))
        current["status"] = new_status
        self.records[str(run_id)] = current
        return [
            {
                "run_id": run_id,
                "customer_id": current.get("customer_id"),
                "project_id": current.get("project_id"),
                "workflow": current.get("workflow"),
                "status": new_status,
                "payload": deepcopy(current),
                "created_at": current.get("created_at"),
            }
        ]

    def _normalize_jsonb(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        assert table == "assessment_runs"
        payload = deepcopy(row["payload"])
        payload.update(
            {
                "run_id": row["run_id"],
                "customer_id": row["customer_id"],
                "project_id": row["project_id"],
                "workflow": row["workflow"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
        )
        return payload


class _Store:
    def __init__(self, records: list[dict[str, Any]], *, durable: bool = True) -> None:
        self.durable = durable
        self.adapter = _PostgresAdapter(records)
        self.records = self.adapter.records
        self.audit_events: list[tuple[str, dict[str, Any]]] = []

    def status(self) -> dict[str, Any]:
        return {
            "adapter": "postgres" if self.durable else "memory",
            "persistence_available": self.durable,
        }

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        if table == "assessment_runs":
            value = self.records.get(item_id)
            return deepcopy(value) if value else None
        if table == "scanner_runs":
            return None
        raise AssertionError(table)

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert table == "assessment_runs"
        self.records[item_id] = deepcopy(payload)
        return deepcopy(payload)

    def list(self, table: str, customer_id=None, project_id=None) -> list[dict[str, Any]]:
        assert table == "assessment_runs"
        values = list(self.records.values())
        if customer_id:
            values = [item for item in values if item.get("customer_id") == customer_id]
        if project_id:
            values = [item for item in values if item.get("project_id") == project_id]
        return deepcopy(values)

    def audit(self, action: str, payload: dict[str, Any], customer_id=None, project_id=None) -> dict[str, Any]:
        self.audit_events.append((action, deepcopy(payload)))
        return {"action": action}


class _StoreWithScans(_Store):
    def __init__(self, records: list[dict[str, Any]], scans: dict[str, dict[str, Any]]) -> None:
        super().__init__(records)
        self.scans = deepcopy(scans)

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        if table == "scanner_runs":
            value = self.scans.get(item_id)
            return deepcopy(value) if value else None
        return super().get(table, item_id)


def test_stale_detection_requires_supported_active_workflow() -> None:
    stale = _run(updated_at="2026-07-12T22:00:00Z")
    fresh = _run(updated_at="2026-07-12T22:29:30Z")
    complete = _run(status="complete", updated_at="2026-07-12T22:00:00Z")
    unrelated = _run(workflow="express_assessment", updated_at="2026-07-12T22:00:00Z")

    assert assessment_is_stale(stale, stale_seconds=900, now=NOW) is True
    assert assessment_is_stale(fresh, stale_seconds=900, now=NOW) is False
    assert assessment_is_stale(complete, stale_seconds=900, now=NOW) is False
    assert assessment_is_stale(unrelated, stale_seconds=900, now=NOW) is False


def test_memory_fallback_never_reconciles_as_restart_safe() -> None:
    store = _Store([_run()], durable=False)

    result = reconcile_interrupted_assessment_runs(
        store=store,
        stale_seconds=900,
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["durable_postgres_required"]
    assert store.records["fullrun_1234567890abcdef"]["status"] == "running"


def test_stale_mid_and_full_runs_reconcile_while_fresh_and_terminal_runs_are_preserved() -> None:
    stale_full = _run("fullrun_1234567890abcdef", updated_at="2026-07-12T22:00:00Z")
    stale_mid = _run(
        "midrun_1234567890abcdef",
        workflow="mid_assessment",
        updated_at="2026-07-12T21:55:00Z",
    )
    fresh = _run("fullrun_abcdef1234567890", updated_at="2026-07-12T22:29:30Z")
    complete = _run("fullrun_complete123456", status="complete", updated_at="2026-07-12T21:00:00Z")
    store = _Store([stale_full, stale_mid, fresh, complete])

    result = reconcile_interrupted_assessment_runs(
        store=store,
        stale_seconds=900,
        now=NOW,
    )

    assert result["status"] == "attention_required"
    assert result["reconciled"] == 2
    assert result["fresh_active"] == 1
    assert result["recovery_required"] == 2
    assert store.records[stale_full["run_id"]]["status"] == RECOVERY_REQUIRED_STATUS
    assert store.records[stale_mid["run_id"]]["status"] == RECOVERY_REQUIRED_STATUS
    assert store.records[fresh["run_id"]]["status"] == "running"
    assert store.records[complete["run_id"]]["status"] == "complete"
    assert len(store.audit_events) == 2


def test_atomic_transition_is_compare_and_set() -> None:
    record = _run(status=RECOVERY_REQUIRED_STATUS)
    store = _Store([record])

    first = atomic_assessment_transition(
        record["run_id"],
        {RECOVERY_REQUIRED_STATUS},
        "resuming",
        {"updated_at": "2026-07-12T22:31:00Z", "claim": "one"},
        store=store,
    )
    second = atomic_assessment_transition(
        record["run_id"],
        {RECOVERY_REQUIRED_STATUS},
        "resuming",
        {"updated_at": "2026-07-12T22:31:01Z", "claim": "two"},
        store=store,
    )

    assert first is not None
    assert first["status"] == "resuming"
    assert first["claim"] == "one"
    assert second is None
    assert store.records[record["run_id"]]["claim"] == "one"


def test_same_run_resume_is_idempotent_and_preserves_artifact_ids() -> None:
    record = _run(status=RECOVERY_REQUIRED_STATUS)
    record["recovery"] = {
        "state": RECOVERY_REQUIRED_STATUS,
        "reason": "stale_assessment_execution",
        "attempt": 0,
        "resume_allowed": True,
    }
    store = _Store([record])
    calls = {"count": 0}

    def invoker(claimed: dict[str, Any], req: Any) -> dict[str, Any]:
        calls["count"] += 1
        updated = deepcopy(claimed)
        updated["status"] = "complete"
        updated["updated_at"] = "2026-07-12T22:32:00Z"
        store.put("assessment_runs", claimed["run_id"], updated)
        return {
            "status": "complete",
            "run_id": claimed["run_id"],
            "reports": {"report_id": claimed["report_id"], "idempotent_reuse": True},
            "approval": {"approval_id": claimed["approval_id"], "idempotent_reuse": True},
        }

    first = resume_interrupted_assessment_run(
        record["run_id"],
        actor="operator-one",
        store=store,
        invoker=invoker,
    )
    second = resume_interrupted_assessment_run(
        record["run_id"],
        actor="operator-two",
        store=store,
        invoker=invoker,
    )

    assert first["status"] == "complete"
    assert first["idempotent_reuse"] is False
    assert first["resume"]["same_run_id"] is True
    assert first["run"]["run_id"] == record["run_id"]
    assert first["run"]["report_id"] == "report_1"
    assert first["run"]["approval_id"] == "approval_1"
    assert second["status"] == "complete"
    assert second["idempotent_reuse"] is True
    assert calls["count"] == 1


def test_resume_validates_authorization_snapshot_and_scanner_identity() -> None:
    missing_auth = _run(status=RECOVERY_REQUIRED_STATUS)
    missing_auth["request"]["authorized_by"] = ""
    result = resume_interrupted_assessment_run(
        missing_auth["run_id"],
        actor="operator",
        store=_Store([missing_auth]),
        invoker=lambda record, req: {},
    )
    assert result["code"] == "authorized_by_missing"

    incomplete_snapshot = _run(status=RECOVERY_REQUIRED_STATUS)
    incomplete_snapshot["snapshot_id"] = "snapshot_1"
    result = resume_interrupted_assessment_run(
        incomplete_snapshot["run_id"],
        actor="operator",
        store=_Store([incomplete_snapshot]),
        invoker=lambda record, req: {},
    )
    assert result["code"] == "snapshot_identity_incomplete"

    scanner_blocked = _run(status=RECOVERY_REQUIRED_STATUS)
    scanner_blocked["scan_id"] = "scan_1"
    store = _StoreWithScans(
        [scanner_blocked],
        {"scan_1": {"scan_id": "scan_1", "run_id": scanner_blocked["run_id"], "status": RECOVERY_REQUIRED_STATUS}},
    )
    result = resume_interrupted_assessment_run(
        scanner_blocked["run_id"],
        actor="operator",
        store=store,
        invoker=lambda record, req: {},
    )
    assert result["code"] == "scanner_recovery_required"


def test_failed_resume_returns_to_recovery_without_raw_exception() -> None:
    record = _run(status=RECOVERY_REQUIRED_STATUS)
    store = _Store([record])

    def fail(claimed: dict[str, Any], req: Any) -> dict[str, Any]:
        raise RuntimeError("secret=must-not-leak")

    result = resume_interrupted_assessment_run(
        record["run_id"],
        actor="operator",
        store=store,
        invoker=fail,
    )
    rendered = repr(result)

    assert result["status"] == "blocked"
    assert result["code"] == "assessment_resume_failed"
    assert result["error_type"] == "RuntimeError"
    assert store.records[record["run_id"]]["status"] == RECOVERY_REQUIRED_STATUS
    assert "must-not-leak" not in rendered
    assert "secret=" not in rendered


def test_inventory_is_bounded_and_excludes_saved_response_payloads() -> None:
    records = []
    for index in range(3):
        prefix = "midrun" if index % 2 else "fullrun"
        workflow = "mid_assessment" if index % 2 else "full_assessment"
        item = _run(
            f"{prefix}_{index:016d}",
            workflow=workflow,
            status=RECOVERY_REQUIRED_STATUS,
        )
        records.append(item)
    store = _Store(records)

    result = assessment_recovery_inventory(store=store, limit=2)
    rendered = repr(result)

    assert result["counts"]["recovery_required"] == 3
    assert len(result["recovery_required"]) == 2
    assert "private_payload" not in rendered
    assert "must-not-appear" not in rendered
    assert result["client_delivery_allowed"] is False


def test_routes_require_admin_validate_limits_and_install_idempotently(monkeypatch) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    monkeypatch.setattr(
        recovery,
        "reconcile_interrupted_assessment_runs",
        lambda **kwargs: {
            "artifact_schema": recovery.ASSESSMENT_RECOVERY_SCHEMA,
            "status": "clear",
            "recovery_required": 0,
            "automatic_resume": False,
        },
    )
    monkeypatch.setattr(
        recovery,
        "assessment_recovery_inventory",
        lambda **kwargs: {
            "artifact_schema": recovery.ASSESSMENT_RECOVERY_SCHEMA,
            "status": "clear",
            "counts": {"recovery_required": 0},
            "automatic_resume": False,
            "client_delivery_allowed": False,
        },
    )

    app = FastAPI()
    first = install_assessment_recovery(app)
    second = install_assessment_recovery(app)
    client = TestClient(app)

    denied = client.get("/operations/recovery/assessments")
    assert denied.status_code == 403
    invalid = client.get(
        "/operations/recovery/assessments?limit=501",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert invalid.status_code == 400
    allowed = client.get(
        "/operations/recovery/assessments?refresh=true&limit=100",
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
    assert ASSESSMENT_RECOVERY_INVENTORY_ROUTE in route_pairs
    assert ASSESSMENT_RECOVERY_RESUME_ROUTE in route_pairs
    assert REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES <= REQUIRED_OPERATION_ROUTES
