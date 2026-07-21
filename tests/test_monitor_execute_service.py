from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.monitor_execute_api import register_monitor_execute_routes
from nico.monitor_execute_service import (
    MonitorExecuteService,
    MonitorExecuteStore,
    MonitorIntegrityError,
    MonitorRevisionConflict,
)


def _store(path: Path) -> MonitorExecuteStore:
    store = MonitorExecuteStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _create_payload() -> dict:
    return {
        "work_item_id": "work-1",
        "repository": "BoneManTGRM/NICO",
        "immutable_sha": "a" * 40,
        "customer_id": "customer-1",
        "project_id": "project-1",
        "evidence_id": "evidence-1",
        "finding": {"finding_id": "F-1", "severity": "high"},
    }


def _proposal_payload() -> dict:
    return {
        "proposal_id": "proposal-1",
        "finding_id": "F-1",
        "title": "Bounded repair",
        "rationale": "Exact evidence supports the repair.",
        "smallest_reversible_change": "Change one guarded path.",
        "affected_paths": ["nico/example.py"],
        "verification_plan": "Run focused and full tests.",
        "rollback_plan": "Revert the exact commit.",
        "risk_level": "moderate",
        "requested_by": "nico-monitor",
        "production_impacting": True,
        "created_at": "2026-07-21T00:00:00Z",
    }


def test_durable_service_survives_restart_with_identity_and_integrity(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    service = MonitorExecuteService(_store(path))
    created = service.create(_create_payload())
    proposed = service.propose("work-1", _proposal_payload())
    loaded = MonitorExecuteService(_store(path)).status("work-1")

    assert created["identity"]["work_item_id"] == "work-1"
    assert loaded["identity"] == proposed["identity"]
    assert loaded["revision"] == 2
    assert loaded["state"] == "proposed"
    assert loaded["integrity_sha256"].startswith("sha256:")
    assert loaded["client_delivery_allowed"] is False


def test_store_rejects_stale_revision_and_tampering(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    store = _store(path)
    service = MonitorExecuteService(store)
    service.create(_create_payload())
    stored = store.load("work-1")
    with pytest.raises(MonitorRevisionConflict, match="monitor_revision_increment_invalid"):
        store.save(stored.item, expected_revision=stored.item.revision)

    connection = sqlite3.connect(path)
    connection.execute("UPDATE nico_monitor_work_items SET payload_json = ? WHERE work_item_id = ?", ('{"state":"closed"}', "work-1"))
    connection.commit()
    connection.close()
    with pytest.raises(MonitorIntegrityError, match="monitor_work_item_integrity_mismatch"):
        store.load("work-1")


def test_api_requires_approval_and_exact_verification(tmp_path: Path) -> None:
    app = FastAPI()
    register_monitor_execute_routes(app, service=MonitorExecuteService(_store(tmp_path / "api.db")))
    client = TestClient(app)

    assert client.post("/monitor/work-items", json=_create_payload()).status_code == 200
    assert client.post("/monitor/work-items/work-1/proposal", json=_proposal_payload()).status_code == 200
    premature = client.post(
        "/monitor/work-items/work-1/execution/begin",
        json={"executor_id": "worker-1", "requested_paths": ["nico/example.py"], "current_sha": "a" * 40},
    )
    assert premature.status_code == 422
    assert premature.json()["detail"] == "monitor_execution_requires_approval"

    approval = client.post(
        "/monitor/work-items/work-1/approval",
        json={
            "approver_id": "human-1",
            "approved": True,
            "scope": ["nico/example.py"],
            "reason": "Approved exact bounded change.",
            "approved_at": "2026-07-21T00:01:00Z",
            "expires_at": "2026-07-22T00:01:00Z",
        },
    )
    begin = client.post(
        "/monitor/work-items/work-1/execution/begin",
        json={"executor_id": "worker-1", "requested_paths": ["nico/example.py"], "current_sha": "a" * 40},
    )
    completed = client.post(
        "/monitor/work-items/work-1/execution/complete",
        json={
            "executor_id": "worker-1",
            "before_sha": "a" * 40,
            "after_sha": "b" * 40,
            "changed_paths": ["nico/example.py"],
            "command_fingerprint": "sha256:command",
            "outcome": "success",
            "logs_fingerprint": "sha256:logs",
            "started_at": "2026-07-21T00:02:00Z",
            "completed_at": "2026-07-21T00:03:00Z",
        },
    )
    verified = client.post(
        "/monitor/work-items/work-1/verification",
        json={
            "verifier_id": "verifier-1",
            "passed": True,
            "exact_sha": "b" * 40,
            "checks": ["focused-tests", "full-ci", "production-smoke"],
            "evidence_fingerprint": "sha256:evidence",
            "residual_risk": "low",
            "verified_at": "2026-07-21T00:04:00Z",
        },
    )

    assert approval.json()["state"] == "approved"
    assert begin.json()["state"] == "executing"
    assert completed.json()["state"] == "verifying"
    assert verified.json()["state"] == "closed"
    assert verified.json()["client_delivery_allowed"] is False


def test_route_registration_is_idempotent_and_partial_groups_fail(tmp_path: Path) -> None:
    service = MonitorExecuteService(_store(tmp_path / "routes.db"))
    app = FastAPI()
    register_monitor_execute_routes(app, service=service)
    count = len(app.routes)
    register_monitor_execute_routes(app, service=service)
    assert len(app.routes) == count

    partial = FastAPI()

    @partial.post("/monitor/work-items")
    async def existing():
        return {}

    with pytest.raises(RuntimeError, match="monitor_execute_partial_route_group_detected"):
        register_monitor_execute_routes(partial, service=service)
