from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nico.monitor_runtime import (
    MonitorDefinition,
    MonitorLeaseConflict,
    MonitorRuntimeError,
    MonitorRuntimeStore,
)
from nico.monitor_scheduler import MonitorCadence, RepositoryObservation


def _store(path: Path) -> MonitorRuntimeStore:
    store = MonitorRuntimeStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _definition() -> MonitorDefinition:
    return MonitorDefinition(
        monitor_id="monitor-1",
        repository="BoneManTGRM/NICO",
        customer_id="customer-1",
        project_id="project-1",
        cadence=MonitorCadence(interval_seconds=60, stale_after_seconds=600),
    )


def _observation(*, sha: str = "a" * 40, observed_at: str = "2026-07-21T00:01:00Z") -> RepositoryObservation:
    return RepositoryObservation(
        repository="BoneManTGRM/NICO",
        immutable_sha=sha,
        observed_at=observed_at,
        canonical_score=90,
        evidence_completeness=95,
        deployment_state="success",
        provider_state="ready",
        findings=(),
        artifact_digest="sha256:artifact",
    )


def test_definition_state_and_due_schedule_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "monitor-runtime.db"
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    store = _store(path)
    created = store.create_definition(_definition(), now=now)

    restarted = _store(path)
    loaded = restarted.load_definition("monitor-1")
    state = restarted.load_state("monitor-1")

    assert loaded == created
    assert state.monitor_id == "monitor-1"
    assert state.repository == "BoneManTGRM/NICO"
    assert restarted.due(now=now) == ("monitor-1",)
    assert restarted.due(now=now - timedelta(seconds=1)) == ()


def test_active_lease_blocks_second_worker_and_expired_lease_can_be_reacquired(tmp_path: Path) -> None:
    store = _store(tmp_path / "leases.db")
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    store.create_definition(_definition(), now=now)
    first = store.acquire_lease("monitor-1", owner_id="worker-1", lease_seconds=60, now=now)

    with pytest.raises(MonitorLeaseConflict, match="monitor_lease_active"):
        store.acquire_lease("monitor-1", owner_id="worker-2", lease_seconds=60, now=now + timedelta(seconds=30))

    second = store.acquire_lease(
        "monitor-1",
        owner_id="worker-2",
        lease_seconds=60,
        now=now + timedelta(seconds=61),
    )
    assert second.owner_id == "worker-2"
    assert second.lease_id != first.lease_id


def test_successful_completion_requires_observation_and_releases_lease(tmp_path: Path) -> None:
    path = tmp_path / "complete.db"
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    store = _store(path)
    store.create_definition(_definition(), now=now)
    lease = store.acquire_lease("monitor-1", owner_id="worker-1", lease_seconds=300, now=now)

    with pytest.raises(MonitorRuntimeError, match="monitor_success_observation_required"):
        store.complete_run(lease, success=True, now=now + timedelta(seconds=10))

    state = store.complete_run(
        lease,
        success=True,
        observation=_observation(),
        now=now + timedelta(seconds=20),
    )
    assert state.last_sha == "a" * 40
    assert state.consecutive_failures == 0
    assert state.last_error == ""
    assert state.revision == 2
    assert store.due(now=now + timedelta(seconds=79)) == ()
    assert store.due(now=now + timedelta(seconds=80)) == ("monitor-1",)

    replacement = store.acquire_lease(
        "monitor-1",
        owner_id="worker-2",
        lease_seconds=60,
        now=now + timedelta(seconds=21),
    )
    assert replacement.owner_id == "worker-2"


def test_failed_completion_increments_backoff_and_preserves_identity(tmp_path: Path) -> None:
    path = tmp_path / "failure.db"
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    store = _store(path)
    store.create_definition(_definition(), now=now)

    first_lease = store.acquire_lease("monitor-1", owner_id="worker-1", lease_seconds=300, now=now)
    first = store.complete_run(
        first_lease,
        success=False,
        error="provider_outage",
        now=now + timedelta(seconds=10),
    )
    assert first.consecutive_failures == 1
    assert first.last_error == "provider_outage"
    assert first.last_sha == ""

    second_lease = store.acquire_lease(
        "monitor-1",
        owner_id="worker-2",
        lease_seconds=300,
        now=now + timedelta(seconds=11),
    )
    second = store.complete_run(
        second_lease,
        success=False,
        error="provider_outage",
        now=now + timedelta(seconds=20),
    )
    assert second.consecutive_failures == 2
    assert second.repository == first.repository
    assert second.customer_id == first.customer_id
    assert second.project_id == first.project_id
    assert second.revision == 3


def test_expired_or_wrong_lease_cannot_complete(tmp_path: Path) -> None:
    store = _store(tmp_path / "expired.db")
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    store.create_definition(_definition(), now=now)
    lease = store.acquire_lease("monitor-1", owner_id="worker-1", lease_seconds=30, now=now)

    with pytest.raises(MonitorLeaseConflict, match="monitor_lease_missing_or_expired"):
        store.complete_run(
            lease,
            success=False,
            error="timeout",
            now=now + timedelta(seconds=31),
        )


def test_definition_and_state_tampering_are_detected(tmp_path: Path) -> None:
    path = tmp_path / "tamper.db"
    store = _store(path)
    store.create_definition(_definition(), now=datetime(2026, 7, 21, tzinfo=timezone.utc))

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE nico_monitor_definitions SET payload_json = ? WHERE monitor_id = ?",
        ('{"enabled":true}', "monitor-1"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(MonitorRuntimeError, match="monitor_definition_integrity_mismatch"):
        store.load_definition("monitor-1")

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE nico_monitor_runtime_state SET payload_json = ? WHERE monitor_id = ?",
        ('{"revision":99}', "monitor-1"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(MonitorRuntimeError, match="monitor_runtime_state_integrity_mismatch"):
        store.load_state("monitor-1")
