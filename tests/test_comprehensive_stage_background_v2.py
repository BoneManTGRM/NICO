from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.comprehensive_runtime import _DetachedProductionComprehensiveRunService


def _store(path: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(
        lambda: sqlite3.connect(path, check_same_thread=False),
        dialect="sqlite",
    )
    store.ensure_schema()
    return store


def _executors(calls: dict[str, int]) -> dict:
    executors = {}
    for item in execution_plan():
        capability = str(item["capability"])

        def execute(context, *, _capability=capability):
            calls[_capability] = calls.get(_capability, 0) + 1
            if _capability == "authorization":
                time.sleep(0.15)
            return {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }

        executors[capability] = execute
    return executors


def _start(service: _DetachedProductionComprehensiveRunService) -> None:
    service.start(
        run_id="comprun_detached_boundary",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_detached_boundary",
        customer_id="customer",
        project_id="project",
        authorized=True,
    )


def test_continuation_returns_running_marker_before_provider_finishes(tmp_path: Path) -> None:
    calls: dict[str, int] = {}
    service = _DetachedProductionComprehensiveRunService(
        _store(tmp_path / "detached.db"),
        _executors(calls),
    )
    _start(service)

    started = time.monotonic()
    response = service.resume("comprun_detached_boundary", max_stages=1)
    elapsed = time.monotonic() - started

    first_stage = COMPREHENSIVE_STAGES[0]
    assert elapsed < 0.10
    assert response["status"] == "running"
    assert response["terminal"] is False
    assert response["revision"] == 2
    assert response["current_stage"] == first_stage
    marker = response["stage_results"][first_stage]
    assert marker["status"] == "running"
    assert marker["reason"] == "comprehensive_stage_background_execution_in_progress"
    assert marker["stage_execution"]["detached_background_execution"] is True
    assert marker["stage_execution"]["duplicate_execution_prevented"] is True


def test_repeated_continue_does_not_launch_duplicate_stage(tmp_path: Path) -> None:
    calls: dict[str, int] = {}
    service = _DetachedProductionComprehensiveRunService(
        _store(tmp_path / "dedupe.db"),
        _executors(calls),
    )
    _start(service)

    first = service.resume("comprun_detached_boundary", max_stages=1)
    second = service.resume("comprun_detached_boundary", max_stages=1)
    assert second["revision"] == first["revision"]

    deadline = time.monotonic() + 3.0
    completed = service.load("comprun_detached_boundary")
    while COMPREHENSIVE_STAGES[0] not in completed["completed_stages"]:
        assert time.monotonic() < deadline
        time.sleep(0.02)
        completed = service.load("comprun_detached_boundary")

    assert calls.get("authorization") == 1
    assert completed["revision"] == 3
    assert completed["completed_stages"] == [COMPREHENSIVE_STAGES[0]]
    assert completed["terminal"] is False
