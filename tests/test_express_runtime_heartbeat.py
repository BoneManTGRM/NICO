from __future__ import annotations

import nico.express_runtime_heartbeat as heartbeat
from nico.storage import MemoryAdapter


def test_express_heartbeat_updates_durable_run_record(monkeypatch) -> None:
    store = MemoryAdapter()
    run_id = "express_run_heartbeat_test"
    store.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "running",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "response": {
                "run_id": run_id,
                "status": "running",
                "current_stage": "repository_evidence",
                "progress_percent": 14,
                "human_review_required": True,
                "client_ready": False,
            },
        },
    )
    monkeypatch.setattr(heartbeat, "STORE", store)

    heartbeat._pulse(run_id)
    retained = store.get("assessment_runs", run_id)

    assert retained is not None
    assert retained["heartbeat_at"]
    assert retained["heartbeat_sequence"] == 1
    assert retained["response"]["heartbeat_at"] == retained["heartbeat_at"]
    assert retained["response"]["heartbeat_sequence"] == 1
    assert retained["response"]["client_ready"] is False


def test_express_heartbeat_does_not_reopen_terminal_run(monkeypatch) -> None:
    store = MemoryAdapter()
    run_id = "express_run_complete_heartbeat_test"
    store.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "complete",
            "response": {
                "run_id": run_id,
                "status": "complete",
                "current_stage": "complete",
                "progress_percent": 100,
            },
        },
    )
    monkeypatch.setattr(heartbeat, "STORE", store)

    heartbeat._pulse(run_id)
    retained = store.get("assessment_runs", run_id)

    assert retained is not None
    assert retained["status"] == "complete"
    assert "heartbeat_sequence" not in retained
