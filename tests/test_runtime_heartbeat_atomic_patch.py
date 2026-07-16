from __future__ import annotations

from pathlib import Path

from nico.durable_runtime_storage import SQLiteRuntimeAdapter
from nico.runtime_heartbeat_atomic_patch import install_runtime_heartbeat_atomic_patch
from nico.storage import MemoryAdapter


def test_assessment_heartbeat_preserves_latest_stage_and_nested_payload() -> None:
    install_runtime_heartbeat_atomic_patch()
    store = MemoryAdapter()
    run_id = "express_run_atomic_stage"
    store.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "running",
            "current_stage": "report_generation",
            "progress_percent": 86,
            "response": {
                "run_id": run_id,
                "status": "running",
                "current_stage": "report_generation",
                "progress_percent": 86,
                "reports": {"markdown": "draft"},
                "human_review_required": True,
                "client_ready": False,
            },
        },
    )

    updated = store.patch_heartbeat(
        "assessment_runs",
        run_id,
        patch={"heartbeat_at": "2099-01-01T00:00:00Z", "heartbeat_process_id": 123},
        active_statuses={"queued", "running"},
        nested_key="response",
    )

    assert updated is not None
    assert updated["status"] == "running"
    assert updated["current_stage"] == "report_generation"
    assert updated["progress_percent"] == 86
    assert updated["response"]["current_stage"] == "report_generation"
    assert updated["response"]["reports"]["markdown"] == "draft"
    assert updated["response"]["heartbeat_process_id"] == 123
    assert updated["heartbeat_sequence"] == 1


def test_heartbeat_cannot_reopen_terminal_assessment_or_scanner() -> None:
    install_runtime_heartbeat_atomic_patch()
    store = MemoryAdapter()
    store.put(
        "assessment_runs",
        "express_run_terminal",
        {
            "run_id": "express_run_terminal",
            "workflow": "express",
            "status": "complete",
            "response": {"status": "complete", "current_stage": "complete", "progress_percent": 100},
        },
    )
    store.put(
        "scanner_runs",
        "scan_terminal",
        {
            "scan_id": "scan_terminal",
            "status": "failed",
            "current_stage": "worker_failed",
            "failure_type": "RuntimeError",
        },
    )

    assessment = store.patch_heartbeat(
        "assessment_runs",
        "express_run_terminal",
        patch={"heartbeat_at": "2099-01-01T00:00:00Z"},
        active_statuses={"queued", "running"},
        nested_key="response",
    )
    scanner = store.patch_heartbeat(
        "scanner_runs",
        "scan_terminal",
        patch={"heartbeat_at": "2099-01-01T00:00:00Z"},
        active_statuses={"queued", "running"},
        nested_key=None,
    )

    assert assessment is None
    assert scanner is None
    assert store.get("assessment_runs", "express_run_terminal")["status"] == "complete"
    assert store.get("scanner_runs", "scan_terminal")["status"] == "failed"
    assert "heartbeat_at" not in store.get("scanner_runs", "scan_terminal")


def test_sqlite_atomic_heartbeat_preserves_stage_across_fresh_adapter_instances(tmp_path: Path) -> None:
    install_runtime_heartbeat_atomic_patch()
    path = tmp_path / "runtime.sqlite3"
    first = SQLiteRuntimeAdapter(path)
    run_id = "express_run_sqlite_atomic"
    first.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "running",
            "current_stage": "scanner_reconciliation",
            "response": {
                "status": "running",
                "current_stage": "scanner_reconciliation",
                "scanner": {"status": "running", "active_tool": "semgrep"},
            },
        },
    )

    second = SQLiteRuntimeAdapter(path)
    second.patch_heartbeat(
        "assessment_runs",
        run_id,
        patch={"heartbeat_at": "2099-01-01T00:00:00Z", "heartbeat_thread": "test"},
        active_statuses={"running"},
        nested_key="response",
    )
    retained = first.get("assessment_runs", run_id)

    assert retained is not None
    assert retained["current_stage"] == "scanner_reconciliation"
    assert retained["response"]["scanner"]["active_tool"] == "semgrep"
    assert retained["response"]["heartbeat_thread"] == "test"
