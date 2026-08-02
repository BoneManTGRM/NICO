from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest

from nico import comprehensive_background_stage_execution_v1 as background
from nico.comprehensive_background_terminal_order_v2 import (
    background_terminal_ordering_installed,
    install_background_terminal_ordering,
    reset_background_terminal_ordering_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_background_state() -> None:
    install_background_terminal_ordering()
    background.reset_background_stage_tasks_for_tests()
    reset_background_terminal_ordering_for_tests()
    yield
    background.reset_background_stage_tasks_for_tests()
    reset_background_terminal_ordering_for_tests()


def _context() -> dict:
    token = uuid4().hex
    return {
        "run_id": f"comprun_{token}",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "b" * 40,
        "evidence_ledger_id": f"ledger_{token}",
        "customer_id": f"customer_{token}",
        "project_id": f"project_{token}",
        "prior_stage_results": {},
        "recovery_history": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_terminal_ordering_is_installed_idempotently() -> None:
    assert background_terminal_ordering_installed() is True
    assert install_background_terminal_ordering() is False


def test_delayed_heartbeat_cannot_overwrite_completed_final_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    provider_release = threading.Event()
    heartbeat_write_entered = threading.Event()
    heartbeat_write_release = threading.Event()
    calls = 0
    running_writes = 0

    monkeypatch.setattr(background, "_heartbeat_seconds", lambda: 0.01)
    original_store_put = background.STORE.put

    def blocking_store_put(
        table: str,
        item_id: str,
        payload: dict,
    ) -> dict:
        nonlocal running_writes
        if table == "client_jobs" and payload.get("status") == "running":
            running_writes += 1
            if running_writes == 2:
                heartbeat_write_entered.set()
                assert heartbeat_write_release.wait(3.0)
        return original_store_put(table, item_id, payload)

    monkeypatch.setattr(background.STORE, "put", blocking_store_put)

    def final_report_provider(payload: dict) -> dict:
        nonlocal calls
        calls += 1
        assert provider_release.wait(3.0)
        return {
            "status": "complete",
            "run_id": payload["run_id"],
            "repository": payload["repository"],
            "commit_sha": payload["commit_sha"],
            "evidence_ledger_id": payload["evidence_ledger_id"],
            "report_package": {
                "report_id": "report_exact",
                "pdf_base64": "JVBERi0xLjQ=",
                "markdown": "final report",
                "html": "<p>final report</p>",
            },
        }

    first = background.execute_background_stage(
        final_report_provider,
        context,
        stage_id="final_comprehensive_report_generation",
        inline_grace_seconds=0.0,
        max_runtime_seconds=5.0,
    )
    assert background.is_background_stage_in_progress(first) is True
    task_id = first["stage_execution"]["task_id"]

    assert heartbeat_write_entered.wait(3.0)
    provider_release.set()
    time.sleep(0.05)
    heartbeat_write_release.set()

    completed = first
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        completed = background.execute_background_stage(
            final_report_provider,
            context,
            stage_id="final_comprehensive_report_generation",
            inline_grace_seconds=0.02,
            max_runtime_seconds=5.0,
        )
        if completed.get("status") == "complete":
            break
        time.sleep(0.02)

    assert completed["status"] == "complete"
    assert completed["report_package"]["report_id"] == "report_exact"
    assert calls == 1

    durable = background.STORE.get("client_jobs", task_id)
    assert durable is not None
    assert durable["status"] == "complete"
    assert durable["result"]["report_package"]["report_id"] == "report_exact"

    # Simulate a later request landing in another worker process. Local task and
    # terminal caches are removed, so the result must be recovered from durable state
    # without invoking report generation again.
    background.reset_background_stage_tasks_for_tests()
    reset_background_terminal_ordering_for_tests()

    recovered = background.execute_background_stage(
        final_report_provider,
        context,
        stage_id="final_comprehensive_report_generation",
        inline_grace_seconds=0.0,
        max_runtime_seconds=5.0,
    )
    assert recovered["status"] == "complete"
    assert recovered["report_package"]["report_id"] == "report_exact"
    assert calls == 1


def test_terminal_task_rejects_later_running_write() -> None:
    task_id = f"task_{uuid4().hex}"
    terminal = background._put_job(
        task_id,
        {
            "job_id": task_id,
            "workflow": "comprehensive_background_stage",
            "status": "complete",
            "result": {"status": "complete", "evidence": {"ready": True}},
        },
    )
    repeated = background._put_job(
        task_id,
        {
            "job_id": task_id,
            "workflow": "comprehensive_background_stage",
            "status": "running",
            "heartbeat_epoch": time.time(),
        },
    )
    assert terminal["status"] == "complete"
    assert repeated["status"] == "complete"
    durable = background.STORE.get("client_jobs", task_id)
    assert durable is not None
    assert durable["status"] == "complete"
