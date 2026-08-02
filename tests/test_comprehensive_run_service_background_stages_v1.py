from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from nico.comprehensive_background_stage_execution_v1 import (
    reset_background_stage_tasks_for_tests,
)
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


def _store(path: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def test_dependency_stage_polls_in_background_without_blocking_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reset_background_stage_tasks_for_tests()
    monkeypatch.setenv("NICO_COMPREHENSIVE_BACKGROUND_INLINE_GRACE_SECONDS", "0.01")
    monkeypatch.setenv("NICO_COMPREHENSIVE_BACKGROUND_MAX_RUNTIME_SECONDS", "5")
    monkeypatch.setenv("NICO_COMPREHENSIVE_BACKGROUND_HEARTBEAT_SECONDS", "0.02")

    release = threading.Event()
    scanner_calls = 0
    executors: dict[str, object] = {}
    for item in execution_plan():
        capability = item["capability"]

        if capability == "scanner_suite":
            def scanner(context: dict) -> dict:
                nonlocal scanner_calls
                scanner_calls += 1
                release.wait(2.0)
                return {
                    "status": "complete",
                    "scan_id": "scan_background_exact",
                    "scanner": {"status": "complete", "progress_percent": 100},
                    "evidence": {"exact_commit_match": True},
                }

            executors[capability] = scanner
            continue

        def complete(context: dict, *, _capability: str = capability) -> dict:
            return {
                "status": "complete",
                "capability": _capability,
                "evidence": {"capability": _capability},
            }

        executors[capability] = complete

    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), executors)
    service.start(
        run_id="comprun_background_service",
        repository="BoneManTGRM/NICO",
        commit_sha="b" * 40,
        evidence_ledger_id="ledger_background_service",
        customer_id="customer_background_service",
        project_id="project_background_service",
        authorized=True,
    )

    before_scanner = service.resume("comprun_background_service", max_stages=3)
    assert before_scanner["completed_stages"] == list(COMPREHENSIVE_STAGES[:3])
    preserved = before_scanner["stage_results"]["repository_and_delivery_evidence"]

    started = time.monotonic()
    polling = service.resume("comprun_background_service", max_stages=1)
    request_elapsed = time.monotonic() - started

    assert request_elapsed < 0.5
    assert polling["status"] == "running"
    assert polling["current_stage"] == "dependency_security_static_analysis"
    assert polling["completed_stages"] == list(COMPREHENSIVE_STAGES[:3])
    stage = polling["stage_results"]["dependency_security_static_analysis"]
    assert stage["status"] == "running"
    assert stage["reason"] == "background_stage_execution_in_progress"
    assert stage["stage_execution"]["canonical_run_written_only_by_request_thread"] is True
    assert polling["stage_results"]["repository_and_delivery_evidence"] == preserved
    assert scanner_calls == 1

    second = service.resume("comprun_background_service", max_stages=1)
    assert second["status"] == "running"
    assert scanner_calls == 1

    release.set()
    deadline = time.monotonic() + 2.0
    completed = second
    while time.monotonic() < deadline:
        completed = service.resume("comprun_background_service", max_stages=1)
        if "dependency_security_static_analysis" in completed["completed_stages"]:
            break
        time.sleep(0.02)

    assert "dependency_security_static_analysis" in completed["completed_stages"]
    assert completed["stage_results"]["dependency_security_static_analysis"]["scan_id"] == "scan_background_exact"
    assert completed["stage_results"]["repository_and_delivery_evidence"] == preserved
    assert scanner_calls == 1
    assert completed["human_review_required"] is True
    assert completed["client_delivery_allowed"] is False
    reset_background_stage_tasks_for_tests()
