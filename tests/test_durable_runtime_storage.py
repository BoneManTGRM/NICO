from __future__ import annotations

from pathlib import Path

from nico.durable_runtime_storage import SQLiteRuntimeAdapter


def test_sqlite_runtime_adapter_persists_exact_run_across_adapter_restart(tmp_path: Path) -> None:
    database = tmp_path / "nico-runtime.sqlite3"
    first = SQLiteRuntimeAdapter(database)
    payload = {
        "run_id": "midrun_sqlite_persistence",
        "workflow": "mid_assessment",
        "status": "running",
        "customer_id": "customer_sqlite",
        "project_id": "project_sqlite",
        "repository": "owner/repository",
        "response": {
            "run_id": "midrun_sqlite_persistence",
            "status": "running",
            "current_stage": "scanner_worker",
            "progress_percent": 47,
        },
    }

    written = first.put("assessment_runs", payload["run_id"], payload)
    second = SQLiteRuntimeAdapter(database)
    retained = second.get("assessment_runs", payload["run_id"])

    assert written["run_id"] == payload["run_id"]
    assert retained is not None
    assert retained["run_id"] == payload["run_id"]
    assert retained["response"]["progress_percent"] == 47
    assert second.status()["adapter"] == "sqlite"
    assert second.status()["persistence_available"] is True


def test_sqlite_runtime_adapter_filters_scope_without_cross_tenant_leakage(tmp_path: Path) -> None:
    adapter = SQLiteRuntimeAdapter(tmp_path / "scope.sqlite3")
    adapter.put(
        "assessment_runs",
        "express_run_customer_a",
        {
            "run_id": "express_run_customer_a",
            "workflow": "express",
            "status": "running",
            "customer_id": "customer_a",
            "project_id": "project_shared",
        },
    )
    adapter.put(
        "assessment_runs",
        "express_run_customer_b",
        {
            "run_id": "express_run_customer_b",
            "workflow": "express",
            "status": "running",
            "customer_id": "customer_b",
            "project_id": "project_shared",
        },
    )

    customer_a = adapter.list(
        "assessment_runs",
        customer_id="customer_a",
        project_id="project_shared",
    )

    assert [item["run_id"] for item in customer_a] == ["express_run_customer_a"]


def test_sqlite_runtime_adapter_updates_heartbeat_atomically(tmp_path: Path) -> None:
    adapter = SQLiteRuntimeAdapter(tmp_path / "heartbeat.sqlite3")
    run_id = "express_run_heartbeat_sqlite"
    adapter.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "running",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "heartbeat_sequence": 1,
        },
    )
    adapter.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "running",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "heartbeat_sequence": 2,
            "heartbeat_at": "2026-07-15T19:30:00Z",
        },
    )

    retained = adapter.get("assessment_runs", run_id)
    assert retained is not None
    assert retained["heartbeat_sequence"] == 2
    assert retained["heartbeat_at"] == "2026-07-15T19:30:00Z"
