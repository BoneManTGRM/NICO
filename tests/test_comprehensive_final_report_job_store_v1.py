from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nico.comprehensive_final_report_job_store_v1 import (
    ComprehensiveFinalReportJobStore,
)


def _store(path: Path) -> ComprehensiveFinalReportJobStore:
    store = ComprehensiveFinalReportJobStore(
        lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    store.ensure_schema()
    return store


def _identity() -> dict[str, str]:
    return {
        "run_id": "comprun_job_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_job_001",
    }


def test_only_one_unexpired_owner_can_claim(tmp_path: Path) -> None:
    store = _store(tmp_path / "jobs.db")

    first = store.claim(**_identity(), lease_owner="worker-one", lease_seconds=90)
    second = store.claim(**_identity(), lease_owner="worker-two", lease_seconds=90)

    assert first["claimed"] is True
    assert first["state"] == "running"
    assert first["attempt"] == 1
    assert second["claimed"] is False
    assert second["lease_owner"] == "worker-one"
    assert second["attempt"] == 1


def test_heartbeat_extends_matching_lease_only(tmp_path: Path) -> None:
    store = _store(tmp_path / "jobs.db")
    claimed = store.claim(
        **_identity(),
        lease_owner="worker-one",
        lease_seconds=30,
    )
    before = claimed["lease_expires_at"]

    assert store.heartbeat(
        "comprun_job_001",
        lease_owner="worker-two",
        lease_seconds=120,
    ) is False
    assert store.heartbeat(
        "comprun_job_001",
        lease_owner="worker-one",
        lease_seconds=120,
    ) is True

    after = store.load("comprun_job_001")
    assert after is not None
    assert after["lease_expires_at"] > before
    assert after["heartbeat_at"] is not None


def test_expired_lease_can_be_reclaimed_after_process_loss(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"
    store = _store(path)
    store.claim(**_identity(), lease_owner="dead-worker", lease_seconds=90)
    expired = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE nico_comprehensive_final_report_jobs "
        "SET lease_expires_at = ?, heartbeat_at = ?, updated_at = ? "
        "WHERE run_id = ?",
        (expired, expired, expired, "comprun_job_001"),
    )
    connection.commit()
    connection.close()

    reclaimed = store.claim(
        **_identity(),
        lease_owner="replacement-worker",
        lease_seconds=90,
    )

    assert reclaimed["claimed"] is True
    assert reclaimed["lease_owner"] == "replacement-worker"
    assert reclaimed["attempt"] == 2


def test_terminal_complete_job_cannot_be_reclaimed(tmp_path: Path) -> None:
    store = _store(tmp_path / "jobs.db")
    store.claim(**_identity(), lease_owner="worker-one", lease_seconds=90)
    assert store.finish(
        "comprun_job_001",
        lease_owner="worker-one",
        state="complete",
    ) is True

    retry = store.claim(
        **_identity(),
        lease_owner="worker-two",
        lease_seconds=90,
    )

    assert retry["claimed"] is False
    assert retry["state"] == "complete"
    assert retry["lease_owner"] is None
