from __future__ import annotations

import sqlite3
from pathlib import Path

from nico.comprehensive_final_report_background_v1 import _job_deadline_state
from nico.comprehensive_run_store import ComprehensiveRunStore


def _store(tmp_path: Path) -> ComprehensiveRunStore:
    path = tmp_path / "queue-deadline.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def test_queue_wait_does_not_consume_renderer_execution_deadline(monkeypatch) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_MAX_PUBLICATION_SECONDS", "120")
    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_MAX_QUEUE_SECONDS", "600")
    now_epoch = 1_000.0
    started_epoch = 800.0

    queued = _job_deadline_state(
        {
            "status": "queued",
            "started_epoch": started_epoch,
            "heartbeat_epoch": now_epoch,
        },
        now_epoch=now_epoch,
    )
    rendering = _job_deadline_state(
        {
            "status": "rendering",
            "started_epoch": started_epoch,
            "heartbeat_epoch": now_epoch,
        },
        now_epoch=now_epoch,
    )

    assert queued["phase"] == "queued"
    assert queued["deadline_seconds"] == 600.0
    assert queued["elapsed_seconds"] == 200.0
    assert queued["overdue"] is False

    assert rendering["phase"] == "rendering"
    assert rendering["deadline_seconds"] == 120.0
    assert rendering["elapsed_seconds"] == 200.0
    assert rendering["overdue"] is True


def test_durable_render_transition_resets_started_epoch_without_schema_change(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    queue_started_epoch = 100.0
    render_started_epoch = 900.0
    store.create_final_report_job(
        lease_id="frpub_queue_transition",
        run_id="comprun_queue_transition",
        started_epoch=queue_started_epoch,
        heartbeat_epoch=queue_started_epoch,
        updated_at="2026-08-09T00:00:00+00:00",
        status="queued",
    )

    changed = store.transition_final_report_job_to_rendering(
        "frpub_queue_transition",
        started_epoch=render_started_epoch,
        heartbeat_epoch=render_started_epoch,
        updated_at="2026-08-09T00:15:00+00:00",
    )
    job = store.load_final_report_job("frpub_queue_transition")

    assert changed is True
    assert job is not None
    assert job["status"] == "rendering"
    assert job["started_epoch"] == render_started_epoch
    assert job["heartbeat_epoch"] == render_started_epoch


def test_legacy_running_lease_remains_bounded_as_renderer_execution(monkeypatch) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_MAX_PUBLICATION_SECONDS", "120")
    state = _job_deadline_state(
        {
            "status": "running",
            "started_epoch": 100.0,
            "heartbeat_epoch": 300.0,
        },
        now_epoch=300.0,
    )

    assert state["active"] is True
    assert state["phase"] == "rendering"
    assert state["deadline_seconds"] == 120.0
    assert state["overdue"] is True
