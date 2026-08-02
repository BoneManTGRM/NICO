from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.comprehensive_stage_execution_timeout_v1 import (
    VERSION,
    execute_stage_with_timeout,
)
from nico.comprehensive_stage_watchdog_v1 import STALL_REASON


def _store(path: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _executors() -> dict[str, object]:
    result: dict[str, object] = {}
    for item in execution_plan():
        capability = item["capability"]

        def execute(context, *, _capability=capability):
            return {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
            }

        result[capability] = execute
    return result


def _start(service: ComprehensiveRunService) -> None:
    service.start(
        run_id="comprun_timeout",
        repository="BoneManTGRM/NICO",
        commit_sha="abc123",
        evidence_ledger_id="ledger_timeout",
        customer_id="customer_timeout",
        project_id="project_timeout",
        authorized=True,
    )


def test_fast_stage_retains_bounded_execution_metadata() -> None:
    result = execute_stage_with_timeout(
        lambda context: {"status": "complete", "value": context["value"]},
        {"value": 7},
        stage_id="fast_stage",
        timeout_seconds=1,
    )
    assert result["status"] == "complete"
    assert result["value"] == 7
    assert result["stage_execution"]["artifact_schema"] == VERSION
    assert result["stage_execution"]["completed_within_boundary"] is True
    assert result["stage_execution"]["execution_timeout_seconds"] == 1


def test_non_returning_stage_becomes_truthful_terminal_result() -> None:
    release = threading.Event()

    def blocked(_context):
        release.wait(30)
        return {"status": "complete"}

    result = execute_stage_with_timeout(
        blocked,
        {},
        stage_id="risk_reduction_and_executive_briefing",
        timeout_seconds=1,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == STALL_REASON
    assert result["error_code"] == "stage_execution_timeout"
    assert result["retryable"] is True
    assert result["cancelable"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["watchdog"]["provider_thread_daemonized"] is True
    assert result["watchdog"]["stalled"] is True
    release.set()


def test_service_persists_timeout_and_retries_exact_stage_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_STAGE_EXECUTION_TIMEOUT_SECONDS", "1")
    executors = _executors()
    first_capability = execution_plan()[0]["capability"]
    attempts = 0
    release = threading.Event()

    def timeout_once(context):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            release.wait(30)
        return {
            "status": "complete",
            "run_id": context["run_id"],
            "repository": context["repository"],
            "commit_sha": context["commit_sha"],
            "evidence_ledger_id": context["evidence_ledger_id"],
            "attempt": attempts,
        }

    executors[first_capability] = timeout_once
    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), executors)
    _start(service)

    blocked = service.resume("comprun_timeout", max_stages=1)
    first_stage = COMPREHENSIVE_STAGES[0]
    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert blocked["completed_stages"] == []
    assert blocked["stage_results"][first_stage]["reason"] == STALL_REASON
    assert blocked["stage_results"][first_stage]["error_code"] == "stage_execution_timeout"
    assert blocked["identity"]["run_id"] == "comprun_timeout"
    assert blocked["identity"]["commit_sha"] == "abc123"
    assert blocked["client_delivery_allowed"] is False

    recovered = service.resume("comprun_timeout", max_stages=1)
    assert recovered["completed_stages"] == [first_stage]
    assert recovered["stage_results"][first_stage]["attempt"] == 2
    assert recovered["terminal"] is False
    assert recovered["recovery_history"][-1]["recovery_type"] == STALL_REASON
    assert recovered["recovery_history"][-1]["completed_stage_evidence_preserved"] is True
    assert recovered["identity"] == blocked["identity"]
    release.set()


def test_completed_stage_evidence_survives_timeout_in_later_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_STAGE_EXECUTION_TIMEOUT_SECONDS", "1")
    executors = _executors()
    second_capability = execution_plan()[1]["capability"]
    release = threading.Event()

    def blocked_second(_context):
        release.wait(30)
        return {"status": "complete"}

    executors[second_capability] = blocked_second
    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), executors)
    _start(service)

    blocked = service.resume("comprun_timeout", max_stages=2)
    first_stage, second_stage = COMPREHENSIVE_STAGES[:2]
    assert blocked["completed_stages"] == [first_stage]
    assert blocked["stage_results"][first_stage]["status"] == "complete"
    assert blocked["stage_results"][second_stage]["error_code"] == "stage_execution_timeout"
    assert blocked["terminal"] is True
    assert blocked["client_delivery_allowed"] is False
    release.set()
