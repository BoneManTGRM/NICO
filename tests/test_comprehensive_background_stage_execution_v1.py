from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest

from nico.comprehensive_background_stage_execution_v1 import (
    BACKGROUND_STAGE_IDS,
    execute_background_stage,
    is_background_stage_in_progress,
    reset_background_stage_tasks_for_tests,
)
from nico.comprehensive_stage_watchdog_v1 import STALL_REASON


@pytest.fixture(autouse=True)
def _reset_tasks() -> None:
    reset_background_stage_tasks_for_tests()
    yield
    reset_background_stage_tasks_for_tests()


def _context(*, previous: dict | None = None, recovery_history: list[dict] | None = None) -> dict:
    token = uuid4().hex
    return {
        "run_id": f"comprun_{token}",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": f"ledger_{token}",
        "customer_id": f"customer_{token}",
        "project_id": f"project_{token}",
        "prior_stage_results": previous or {},
        "recovery_history": recovery_history or [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_configures_known_long_stages_for_background_polling() -> None:
    assert {
        "dependency_security_static_analysis",
        "deep_scanner_triage",
        "risk_reduction_and_executive_briefing",
        "final_comprehensive_report_generation",
    } <= BACKGROUND_STAGE_IDS


def test_fast_provider_completes_inline_with_exact_identity() -> None:
    context = _context()

    def executor(payload: dict) -> dict:
        return {
            "status": "complete",
            "run_id": payload["run_id"],
            "repository": payload["repository"],
            "commit_sha": payload["commit_sha"],
            "evidence_ledger_id": payload["evidence_ledger_id"],
            "evidence": {"verified": True},
        }

    result = execute_background_stage(
        executor,
        context,
        stage_id="dependency_security_static_analysis",
        inline_grace_seconds=1.0,
        max_runtime_seconds=5.0,
    )

    assert result["status"] == "complete"
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        assert result[field] == context[field]
    execution = result["stage_execution"]
    assert execution["background_poll_iteration"] == 1
    assert execution["completed_within_boundary"] is True
    assert execution["canonical_run_written_only_by_request_thread"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_slow_provider_returns_immediately_and_is_not_duplicated() -> None:
    context = _context()
    release = threading.Event()
    calls = 0

    def executor(payload: dict) -> dict:
        nonlocal calls
        calls += 1
        release.wait(2.0)
        return {"status": "complete", "evidence": {"calls": calls}}

    started = time.monotonic()
    first = execute_background_stage(
        executor,
        context,
        stage_id="dependency_security_static_analysis",
        inline_grace_seconds=0.01,
        max_runtime_seconds=5.0,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert is_background_stage_in_progress(first) is True
    second = execute_background_stage(
        executor,
        context,
        stage_id="dependency_security_static_analysis",
        inline_grace_seconds=0.01,
        max_runtime_seconds=5.0,
    )
    assert is_background_stage_in_progress(second) is True
    assert first["stage_execution"]["task_id"] == second["stage_execution"]["task_id"]
    assert calls == 1

    release.set()
    deadline = time.monotonic() + 2.0
    completed = second
    while time.monotonic() < deadline:
        completed = execute_background_stage(
            executor,
            context,
            stage_id="dependency_security_static_analysis",
            inline_grace_seconds=0.02,
            max_runtime_seconds=5.0,
        )
        if completed["status"] == "complete":
            break
        time.sleep(0.02)

    assert completed["status"] == "complete"
    assert completed["evidence"]["calls"] == 1
    assert calls == 1


def test_running_provider_result_advances_poll_iteration_without_duplicate_work() -> None:
    context = _context()
    calls = 0

    def executor(payload: dict) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "status": "running",
                "scan_id": "scan_exact_1",
                "scanner": {"status": "running", "progress_percent": 42},
            }
        return {
            "status": "complete",
            "scan_id": "scan_exact_1",
            "scanner": {"status": "complete", "progress_percent": 100},
        }

    running = execute_background_stage(
        executor,
        context,
        stage_id="dependency_security_static_analysis",
        inline_grace_seconds=1.0,
        max_runtime_seconds=5.0,
    )
    assert running["status"] == "running"
    assert is_background_stage_in_progress(running) is False
    assert running["stage_execution"]["background_poll_iteration"] == 1
    assert calls == 1

    next_context = {**context, "prior_stage_results": {"dependency_security_static_analysis": running}}
    complete = execute_background_stage(
        executor,
        next_context,
        stage_id="dependency_security_static_analysis",
        inline_grace_seconds=1.0,
        max_runtime_seconds=5.0,
    )
    assert complete["status"] == "complete"
    assert complete["stage_execution"]["background_poll_iteration"] == 2
    assert calls == 2


def test_provider_timeout_is_fail_closed_and_late_result_is_ignored() -> None:
    context = _context()
    release = threading.Event()

    def executor(_payload: dict) -> dict:
        release.wait(2.0)
        return {"status": "complete", "evidence": {"late": True}}

    first = execute_background_stage(
        executor,
        context,
        stage_id="risk_reduction_and_executive_briefing",
        inline_grace_seconds=0.01,
        max_runtime_seconds=0.08,
    )
    assert is_background_stage_in_progress(first) is True
    time.sleep(0.12)

    timed_out = execute_background_stage(
        executor,
        context,
        stage_id="risk_reduction_and_executive_briefing",
        inline_grace_seconds=0.0,
        max_runtime_seconds=0.08,
    )
    assert timed_out["status"] == "blocked"
    assert timed_out["reason"] == STALL_REASON
    assert timed_out["error_code"] == "background_stage_execution_timeout"
    assert timed_out["retryable"] is True
    assert timed_out["client_delivery_allowed"] is False

    release.set()
    time.sleep(0.05)
    repeated = execute_background_stage(
        executor,
        context,
        stage_id="risk_reduction_and_executive_briefing",
        inline_grace_seconds=0.0,
        max_runtime_seconds=0.08,
    )
    assert repeated["status"] == "blocked"
    assert repeated["error_code"] == "background_stage_execution_timeout"
    assert repeated.get("evidence", {}).get("late") is not True


def test_recovery_attempt_gets_new_task_identity() -> None:
    context = _context()
    release = threading.Event()

    def blocked(_payload: dict) -> dict:
        release.wait(2.0)
        return {"status": "complete"}

    first = execute_background_stage(
        blocked,
        context,
        stage_id="final_comprehensive_report_generation",
        inline_grace_seconds=0.0,
        max_runtime_seconds=0.05,
    )
    first_task = first["stage_execution"]["task_id"]
    time.sleep(0.07)
    timeout = execute_background_stage(
        blocked,
        context,
        stage_id="final_comprehensive_report_generation",
        inline_grace_seconds=0.0,
        max_runtime_seconds=0.05,
    )
    assert timeout["status"] == "blocked"

    recovered_context = {
        **context,
        "recovery_history": [
            {
                "stage_id": "final_comprehensive_report_generation",
                "recovery_type": STALL_REASON,
            }
        ],
    }

    def recovered(_payload: dict) -> dict:
        return {"status": "complete", "evidence": {"recovered": True}}

    completed = execute_background_stage(
        recovered,
        recovered_context,
        stage_id="final_comprehensive_report_generation",
        inline_grace_seconds=1.0,
        max_runtime_seconds=1.0,
    )
    assert completed["status"] == "complete"
    assert completed["evidence"]["recovered"] is True
    assert completed["stage_execution"]["task_id"] != first_task
    assert completed["stage_execution"]["recovery_attempt"] == 1
    release.set()
