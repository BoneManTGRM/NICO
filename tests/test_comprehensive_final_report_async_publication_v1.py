from __future__ import annotations

import base64
import sqlite3
import threading
import time
from pathlib import Path

from nico.comprehensive_final_report_background_v1 import (
    FinalReportPublicationCoordinator,
    reset_final_report_publication_tasks_for_tests,
)
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
from nico.comprehensive_run_store import ComprehensiveRunStore


RUN_ID = "comprun_async_final_report_test"
IDENTITY = {
    "run_id": RUN_ID,
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "evidence_ledger_id": "ledger_async_final_report_test",
}


def _store(tmp_path: Path) -> ComprehensiveRunStore:
    path = tmp_path / "comprehensive.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _record_at_final_report() -> dict:
    record = create_comprehensive_run_record(
        **IDENTITY,
        customer_id="customer_test",
        project_id="project_test",
        authorized=True,
    )
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id == FINAL_REPORT_STAGE_ID:
            break
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result={"status": "complete", **IDENTITY},
        )
    return record


def _context(record: dict) -> dict:
    identity = record["identity"]
    completed = list(record["completed_stages"])
    stage_results = record["stage_results"]
    return {
        "service_id": "comprehensive",
        "stage_id": FINAL_REPORT_STAGE_ID,
        **IDENTITY,
        "customer_id": identity["customer_id"],
        "project_id": identity["project_id"],
        "assessment_depth": identity["assessment_depth"],
        "report_language": identity["report_language"],
        "human_evidence": record["human_evidence"],
        "prior_stage_results": {
            stage_id: stage_results[stage_id]
            for stage_id in completed
            if stage_id in stage_results
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _valid_final_result() -> dict:
    pdf = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii")
    return {
        "status": "complete",
        **IDENTITY,
        "report_package": {
            "report_id": "report_async_final_test",
            "markdown": "# NICO Comprehensive\n",
            "html": "<h1>NICO Comprehensive</h1>",
            "pdf_base64": pdf,
            "canonical_truth_sha256": "b" * 64,
            "json": {"identity": dict(IDENTITY)},
        },
    }


def _wait_for_final(store: ComprehensiveRunStore, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = store.load(RUN_ID)
        if FINAL_REPORT_STAGE_ID in current["completed_stages"]:
            return current
        time.sleep(0.02)
    raise AssertionError("final report did not publish within the test deadline")


def test_final_report_returns_running_marker_without_holding_request_open(tmp_path: Path) -> None:
    reset_final_report_publication_tasks_for_tests()
    store = _store(tmp_path)
    record = _record_at_final_report()
    store.create(record)
    coordinator = FinalReportPublicationCoordinator(store)
    started = threading.Event()
    release = threading.Event()

    def executor(_context: dict) -> dict:
        started.set()
        assert release.wait(2.0)
        return _valid_final_result()

    before = time.perf_counter()
    returned = coordinator.advance(record, executor, _context(record))
    elapsed = time.perf_counter() - before

    assert elapsed < 1.0
    assert returned["status"] == "running"
    marker = returned["stage_results"][FINAL_REPORT_STAGE_ID]
    assert marker["status"] == "running"
    assert marker["reason"] == "final_report_background_publication_in_progress"
    assert marker["client_delivery_allowed"] is False
    assert marker["human_review_required"] is True
    assert marker["stage_execution"]["full_result_job_serialization"] is False
    assert started.wait(1.0)

    release.set()
    final = _wait_for_final(store)
    assert final["status"] == "running"
    result = final["stage_results"][FINAL_REPORT_STAGE_ID]
    assert result["status"] == "complete"
    assert result["report_package"]["pdf_base64"].startswith("JVBER")
    assert result["stage_execution"]["detached_background_execution"] is True
    assert result["stage_execution"]["canonical_run_written_by_final_report_coordinator"] is True
    assert result["stage_execution"]["canonical_run_written_only_by_request_thread"] is False
    assert final["client_delivery_allowed"] is False


def test_repeated_continuation_does_not_launch_duplicate_final_report_worker(tmp_path: Path) -> None:
    reset_final_report_publication_tasks_for_tests()
    store = _store(tmp_path)
    record = _record_at_final_report()
    store.create(record)
    coordinator = FinalReportPublicationCoordinator(store)
    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def executor(_context: dict) -> dict:
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(2.0)
        return _valid_final_result()

    first = coordinator.advance(record, executor, _context(record))
    assert started.wait(1.0)
    second = coordinator.advance(store.load(RUN_ID), executor, _context(record))

    first_lease = first["stage_results"][FINAL_REPORT_STAGE_ID]["stage_execution"]["lease_id"]
    second_lease = second["stage_results"][FINAL_REPORT_STAGE_ID]["stage_execution"]["lease_id"]
    assert second_lease == first_lease
    with calls_lock:
        assert calls == 1

    release.set()
    _wait_for_final(store)
    with calls_lock:
        assert calls == 1


def test_final_report_lease_table_retains_only_small_recovery_metadata(tmp_path: Path) -> None:
    store = _store(tmp_path)
    now = time.time()
    job = store.create_final_report_job(
        lease_id="frpub_small_metadata_only",
        run_id=RUN_ID,
        started_epoch=now,
        heartbeat_epoch=now,
        updated_at="2026-08-08T00:00:00+00:00",
    )
    loaded = store.load_final_report_job(job["lease_id"])

    assert loaded is not None
    assert set(loaded) == {
        "lease_id",
        "run_id",
        "status",
        "started_epoch",
        "heartbeat_epoch",
        "updated_at",
    }
    assert "result" not in loaded
    assert "report_package" not in loaded
