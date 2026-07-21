from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.monitor_approval_governance import (
    ApprovalGovernanceError,
    ApprovalRevocationStore,
    GovernedMonitorExecuteService,
)
from nico.monitor_execute_service import MonitorExecuteStore
from nico.monitor_governed_api import register_governed_monitor_routes


def _service(path: Path, *, now: datetime) -> GovernedMonitorExecuteService:
    connection_factory = lambda: sqlite3.connect(path)
    store = MonitorExecuteStore(connection_factory, dialect="sqlite")
    store.ensure_schema()
    revocations = ApprovalRevocationStore(connection_factory, dialect="sqlite")
    revocations.ensure_schema()
    return GovernedMonitorExecuteService(store, revocations, clock=lambda: now)


def _create_and_approve(service: GovernedMonitorExecuteService, *, expires_at: str) -> None:
    service.create(
        {
            "work_item_id": "work-1",
            "repository": "BoneManTGRM/NICO",
            "immutable_sha": "a" * 40,
            "customer_id": "customer-1",
            "project_id": "project-1",
            "evidence_id": "evidence-1",
            "finding": {"finding_id": "F-1", "severity": "high"},
        }
    )
    service.propose(
        "work-1",
        {
            "proposal_id": "proposal-1",
            "finding_id": "F-1",
            "title": "Bounded repair",
            "rationale": "Exact evidence supports the repair.",
            "smallest_reversible_change": "Change one file.",
            "affected_paths": ["nico/example.py"],
            "verification_plan": "Run tests.",
            "rollback_plan": "Revert commit.",
            "risk_level": "moderate",
            "requested_by": "monitor",
            "production_impacting": True,
            "created_at": "2026-07-21T00:00:00Z",
        },
    )
    service.approve(
        "work-1",
        {
            "approver_id": "human-1",
            "approved": True,
            "scope": ["nico/example.py"],
            "reason": "Approved exact scope.",
            "approved_at": "2026-07-21T00:01:00Z",
            "expires_at": expires_at,
        },
    )


def test_active_approval_allows_execution(tmp_path: Path) -> None:
    service = _service(tmp_path / "active.db", now=datetime(2026, 7, 21, 1, tzinfo=timezone.utc))
    _create_and_approve(service, expires_at="2026-07-22T00:00:00Z")

    result = service.begin(
        "work-1",
        {
            "executor_id": "worker-1",
            "requested_paths": ["nico/example.py"],
            "current_sha": "a" * 40,
        },
    )
    assert result["state"] == "executing"


def test_expired_approval_blocks_execution(tmp_path: Path) -> None:
    service = _service(tmp_path / "expired.db", now=datetime(2026, 7, 23, tzinfo=timezone.utc))
    _create_and_approve(service, expires_at="2026-07-22T00:00:00Z")

    with pytest.raises(ApprovalGovernanceError, match="monitor_execution_approval_expired"):
        service.begin(
            "work-1",
            {
                "executor_id": "worker-1",
                "requested_paths": ["nico/example.py"],
                "current_sha": "a" * 40,
            },
        )


def test_revocation_is_durable_and_blocks_restart_execution(tmp_path: Path) -> None:
    path = tmp_path / "revoked.db"
    now = datetime(2026, 7, 21, 1, tzinfo=timezone.utc)
    service = _service(path, now=now)
    _create_and_approve(service, expires_at="2026-07-22T00:00:00Z")
    revoked = service.revoke(
        "work-1",
        {
            "revoked_by": "human-2",
            "reason": "Conditions changed.",
            "revoked_at": "2026-07-21T00:30:00Z",
        },
    )
    assert revoked["approval_active"] is False
    assert revoked["approval_revocation"]["revocation_sha256"].startswith("sha256:")

    restarted = _service(path, now=now)
    status = restarted.approval_status("work-1")
    assert status["approval_active"] is False
    assert status["approval_reason"] == "monitor_execution_approval_revoked"
    with pytest.raises(ApprovalGovernanceError, match="monitor_execution_approval_revoked"):
        restarted.begin(
            "work-1",
            {
                "executor_id": "worker-1",
                "requested_paths": ["nico/example.py"],
                "current_sha": "a" * 40,
            },
        )


def test_governance_api_exposes_status_and_revocation(tmp_path: Path) -> None:
    service = _service(tmp_path / "api.db", now=datetime(2026, 7, 21, 1, tzinfo=timezone.utc))
    _create_and_approve(service, expires_at="2026-07-22T00:00:00Z")
    app = FastAPI()
    register_governed_monitor_routes(app, service=service)
    client = TestClient(app)

    status = client.get("/monitor/work-items/work-1/approval")
    revoked = client.post(
        "/monitor/work-items/work-1/approval/revoke",
        json={
            "revoked_by": "human-2",
            "reason": "Withdraw approval.",
            "revoked_at": "2026-07-21T00:30:00Z",
        },
    )
    after = client.get("/monitor/work-items/work-1/approval")

    assert status.status_code == 200
    assert status.json()["approval_active"] is True
    assert revoked.status_code == 200
    assert revoked.json()["approval_active"] is False
    assert after.json()["approval_active"] is False
    assert after.json()["client_delivery_allowed"] is False
