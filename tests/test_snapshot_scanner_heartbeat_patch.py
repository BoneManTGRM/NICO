from __future__ import annotations

import time

import nico.snapshot_scanner_heartbeat_patch as heartbeat
from nico import scanner_tool_runners, scanner_worker, snapshot_scanner_worker
from nico.storage import MemoryAdapter


def test_heartbeat_updates_durable_scanner_record(monkeypatch) -> None:
    store = MemoryAdapter()
    scan_id = "scan_snapshot_heartbeat_test"
    record = {
        "scan_id": scan_id,
        "run_id": "midrun_heartbeat_test",
        "customer_id": "customer_heartbeat",
        "project_id": "project_heartbeat",
        "repository": "owner/repository",
        "status": "running",
        "current_stage": "scanner_suite",
        "progress_percent": 47,
        "active_tool": "trufflehog",
        "created_at": "2026-07-15T22:00:00Z",
        "updated_at": "2026-07-15T22:00:00Z",
    }
    store.put("scanner_runs", scan_id, record)
    monkeypatch.setattr(heartbeat, "STORE", store)
    scanner_worker.SCAN_JOBS[scan_id] = dict(record)

    try:
        heartbeat._write_heartbeat(scan_id, "trufflehog", time.monotonic() - 3)
        durable = store.get("scanner_runs", scan_id)
        assert durable["status"] == "running"
        assert durable["active_tool"] == "trufflehog"
        assert durable["heartbeat_at"]
        assert durable["updated_at"] == durable["heartbeat_at"]
        assert durable["tool_elapsed_seconds"] >= 3
    finally:
        scanner_worker.SCAN_JOBS.pop(scan_id, None)


def test_heartbeat_installer_wraps_worker_and_tool_without_changing_signatures(monkeypatch) -> None:
    def fake_worker(scan_id: str, payload: dict) -> None:
        return None

    def fake_tool(spec, workspace, *, runner=None):
        return {"tool": getattr(spec, "name", "unknown"), "status": "completed"}

    monkeypatch.setattr(snapshot_scanner_worker, "_run_snapshot_scan", fake_worker)
    monkeypatch.setattr(scanner_tool_runners, "run_scanner_tool", fake_tool)

    result = heartbeat.install_snapshot_scanner_heartbeat()

    assert result["status"] == "installed"
    assert result["durable_heartbeat"] is True
    assert getattr(snapshot_scanner_worker._run_snapshot_scan, "_nico_snapshot_scanner_heartbeat_worker_v1") is True
    assert getattr(scanner_tool_runners.run_scanner_tool, "_nico_snapshot_scanner_heartbeat_tool_v1") is True
    assert snapshot_scanner_worker._run_snapshot_scan.__name__ == "fake_worker"
    assert scanner_tool_runners.run_scanner_tool.__name__ == "fake_tool"
