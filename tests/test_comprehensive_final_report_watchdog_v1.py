from __future__ import annotations

import base64
import hashlib
import sqlite3
import threading
import time
from pathlib import Path

import nico.comprehensive_final_report_background_v1 as background
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_final_report_background_v1 import FinalReportPublicationCoordinator
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


REPOSITORY = "BoneManTGRM/NICO"
COMMIT_SHA = "c" * 40


def _store(tmp_path: Path) -> ComprehensiveRunStore:
    path = tmp_path / "watchdog.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _record(run_id: str) -> dict:
    identity = {
        "run_id": run_id,
        "repository": REPOSITORY,
        "commit_sha": COMMIT_SHA,
        "evidence_ledger_id": f"ledger_{run_id}",
    }
    record = create_comprehensive_run_record(
        **identity,
        customer_id="customer_watchdog",
        project_id="project_watchdog",
        authorized=True,
    )
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id == FINAL_REPORT_STAGE_ID:
            break
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result={"status": "complete", **identity},
        )
    return record


def _context(record: dict) -> dict:
    identity = record["identity"]
    completed = list(record["completed_stages"])
    stage_results = record["stage_results"]
    return {
        "service_id": "comprehensive",
        "stage_id": FINAL_REPORT_STAGE_ID,
        "run_id": identity["run_id"],
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "evidence_ledger_id": identity["evidence_ledger_id"],
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
        "recovery_history": list(record.get("recovery_history") or []),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _valid_result(context: dict, *, suffix: str = "ok") -> dict:
    pdf_bytes = b"%PDF-1.4\n%%EOF\n"
    identity = {
        key: context[key]
        for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
    }
    canonical = {"identity": identity}
    return {
        "status": "complete",
        **identity,
        "report_package": {
            "report_id": f"report_{context['run_id']}_{suffix}",
            "markdown": "# NICO Comprehensive\n",
            "html": "<h1>NICO Comprehensive</h1>",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "canonical_truth_sha256": canonical_sha256(canonical),
            "json": canonical,
        },
    }


def _wait_for_complete(store: ComprehensiveRunStore, run_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    last = store.load(run_id)
    while time.time() < deadline:
        last = store.load(run_id)
        if FINAL_REPORT_STAGE_ID in set(last.get("completed_stages") or []):
            return last
        time.sleep(0.02)
    raise AssertionError(f"final report did not complete: {run_id}: {last.get('status')}")


def _wait_for_exhausted_failure(
    store: ComprehensiveRunStore,
    run_id: str,
    *,
    timeout: float = 2.0,
) -> dict:
    deadline = time.time() + timeout
    last = store.load(run_id)
    while time.time() < deadline:
        last = store.load(run_id)
        history = list(last.get("recovery_history") or [])
        result = (last.get("stage_results") or {}).get(FINAL_REPORT_STAGE_ID) or {}
        if (
            last.get("terminal") is True
            and last.get("status") == "blocked"
            and len(history) == 1
            and result.get("reason") == "final_report_publication_deadline_exceeded"
        ):
            return last
        time.sleep(0.02)
    raise AssertionError(f"bounded recovery did not exhaust: {run_id}: {last.get('status')}")


def _accelerate_watchdog(monkeypatch) -> None:
    monkeypatch.setattr(background, "_heartbeat_seconds", lambda: 0.02)
    monkeypatch.setattr(background, "_max_publication_seconds", lambda: 0.12)
    monkeypatch.setattr(background, "_max_queue_seconds", lambda: 5.0)


def test_watchdog_automatically_recovers_hung_renderer_without_second_advance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    background.reset_final_report_publication_tasks_for_tests()
    _accelerate_watchdog(monkeypatch)
    store = _store(tmp_path)
    record = _record("comprun_watchdog_auto_recovery")
    store.create(record)
    coordinator = FinalReportPublicationCoordinator(store)

    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    call_lock = threading.Lock()
    calls = 0

    def executor(context: dict) -> dict:
        nonlocal calls
        with call_lock:
            calls += 1
            attempt = calls
        if attempt == 1:
            first_started.set()
            assert release_first.wait(3.0)
            return _valid_result(context, suffix="stale")
        if attempt == 2:
            second_started.set()
            return _valid_result(context, suffix="recovered")
        raise AssertionError("bounded final-report recovery launched more than once")

    claimed = coordinator.advance(record, executor, _context(record))
    assert first_started.wait(1.0)
    first_lease = claimed["stage_results"][FINAL_REPORT_STAGE_ID]["stage_execution"]["lease_id"]

    assert second_started.wait(1.5), "watchdog must relaunch the bounded recovery automatically"
    completed = _wait_for_complete(store, record["identity"]["run_id"])
    assert len(completed.get("recovery_history") or []) == 1
    assert completed["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]["report_id"].endswith(
        "_recovered"
    )
    assert store.load_final_report_job(first_lease)["status"] == "expired"

    release_first.set()
    time.sleep(0.1)
    persisted = store.load(record["identity"]["run_id"])
    assert persisted["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]["report_id"].endswith(
        "_recovered"
    )
    assert calls == 2
    assert store.load_final_report_job(first_lease)["status"] == "expired"
    background.reset_final_report_publication_tasks_for_tests()


def test_watchdog_stops_after_single_bounded_recovery_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    background.reset_final_report_publication_tasks_for_tests()
    _accelerate_watchdog(monkeypatch)
    store = _store(tmp_path)
    record = _record("comprun_watchdog_exhausted")
    store.create(record)
    coordinator = FinalReportPublicationCoordinator(store)

    release_first = threading.Event()
    release_second = threading.Event()
    first_started = threading.Event()
    second_started = threading.Event()
    third_started = threading.Event()
    call_lock = threading.Lock()
    calls = 0

    def executor(context: dict) -> dict:
        nonlocal calls
        with call_lock:
            calls += 1
            attempt = calls
        if attempt == 1:
            first_started.set()
            assert release_first.wait(3.0)
            return _valid_result(context, suffix="late-first")
        if attempt == 2:
            second_started.set()
            assert release_second.wait(3.0)
            return _valid_result(context, suffix="late-second")
        third_started.set()
        return _valid_result(context, suffix="unexpected-third")

    coordinator.advance(record, executor, _context(record))
    assert first_started.wait(1.0)
    assert second_started.wait(1.5)
    terminal = _wait_for_exhausted_failure(store, record["identity"]["run_id"])
    assert len(terminal.get("recovery_history") or []) == 1
    assert terminal["stage_results"][FINAL_REPORT_STAGE_ID]["status"] == "blocked"
    assert terminal["stage_results"][FINAL_REPORT_STAGE_ID]["reason"] == (
        "final_report_publication_deadline_exceeded"
    )
    time.sleep(0.2)
    assert calls == 2
    assert not third_started.is_set()

    release_first.set()
    release_second.set()
    time.sleep(0.1)
    persisted = store.load(record["identity"]["run_id"])
    assert persisted["status"] == "blocked"
    assert persisted["terminal"] is True
    assert calls == 2
    background.reset_final_report_publication_tasks_for_tests()


def test_status_load_reclaims_stale_final_report_lease_after_process_restart(
    tmp_path: Path,
    monkeypatch,
) -> None:
    background.reset_final_report_publication_tasks_for_tests()
    monkeypatch.setattr(background, "_heartbeat_seconds", lambda: 0.02)
    monkeypatch.setattr(background, "_orphan_seconds", lambda: 0.05)
    monkeypatch.setattr(background, "_max_publication_seconds", lambda: 5.0)
    monkeypatch.setattr(background, "_max_queue_seconds", lambda: 5.0)
    store = _store(tmp_path)
    record = _record("comprun_status_restart_recovery")
    store.create(record)

    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    call_lock = threading.Lock()
    calls = 0

    def final_report_capability(context: dict) -> dict:
        nonlocal calls
        with call_lock:
            calls += 1
            attempt = calls
        if attempt == 1:
            first_started.set()
            assert release_first.wait(3.0)
            return _valid_result(context, suffix="stale-process")
        if attempt == 2:
            second_started.set()
            return _valid_result(context, suffix="restart-recovered")
        raise AssertionError("status maintenance launched an unexpected extra renderer")

    service = ComprehensiveRunService(
        store,
        {"final_report_generation": final_report_capability},
    )
    claimed = service.resume(record["identity"]["run_id"], max_stages=1)
    assert first_started.wait(1.0)
    first_lease = claimed["stage_results"][FINAL_REPORT_STAGE_ID]["stage_execution"]["lease_id"]

    # Simulate a replaced process: the local worker/watchdog disappears while the
    # durable exact-run marker and lease row survive in Postgres/SQLite.
    background.reset_final_report_publication_tasks_for_tests()
    assert store.update_final_report_job(
        first_lease,
        status="rendering",
        heartbeat_epoch=1.0,
        updated_at="2026-08-20T00:00:01+00:00",
    ) is True

    replacement_service = ComprehensiveRunService(
        store,
        {"final_report_generation": final_report_capability},
    )
    replacement_service.load(record["identity"]["run_id"])
    assert second_started.wait(1.0), "status polling must reclaim a stale durable final-report lease"
    completed = _wait_for_complete(store, record["identity"]["run_id"])
    assert completed["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]["report_id"].endswith(
        "_restart-recovered"
    )

    release_first.set()
    time.sleep(0.1)
    persisted = store.load(record["identity"]["run_id"])
    assert persisted["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]["report_id"].endswith(
        "_restart-recovered"
    )
    assert calls == 2
    background.reset_final_report_publication_tasks_for_tests()


def test_final_report_job_terminal_status_cannot_be_reopened(tmp_path: Path) -> None:
    store = _store(tmp_path)
    lease_id = "frpub_terminal_fence"
    store.create_final_report_job(
        lease_id=lease_id,
        run_id="comprun_terminal_fence",
        started_epoch=10.0,
        heartbeat_epoch=10.0,
        updated_at="2026-08-20T00:00:00+00:00",
        status="rendering",
    )
    assert store.update_final_report_job(
        lease_id,
        status="expired",
        heartbeat_epoch=20.0,
        updated_at="2026-08-20T00:00:20+00:00",
    ) is True
    assert store.update_final_report_job(
        lease_id,
        status="rendering",
        heartbeat_epoch=30.0,
        updated_at="2026-08-20T00:00:30+00:00",
    ) is False
    assert store.update_final_report_job(
        lease_id,
        status="failed",
        heartbeat_epoch=40.0,
        updated_at="2026-08-20T00:00:40+00:00",
    ) is False
    job = store.load_final_report_job(lease_id)
    assert job is not None
    assert job["status"] == "expired"
    assert job["heartbeat_epoch"] == 20.0
