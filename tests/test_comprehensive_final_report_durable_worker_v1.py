from __future__ import annotations

import base64
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nico.comprehensive_final_report_durable_worker_v1 import (
    DurableFinalReportWorker,
)
from nico.comprehensive_final_report_job_store_v1 import (
    ComprehensiveFinalReportJobStore,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
from nico.comprehensive_run_store import ComprehensiveRunStore


def _run_store(path: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(
        lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    store.ensure_schema()
    return store


def _record() -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun_worker_001",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_worker_001",
        customer_id="customer_worker_001",
        project_id="project_worker_001",
        authorized=True,
    )
    for stage_id in COMPREHENSIVE_STAGES[:-1]:
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result={
                "status": "complete",
                "run_id": "comprun_worker_001",
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "a" * 40,
                "evidence_ledger_id": "ledger_worker_001",
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    return record


def _report(context: dict) -> dict:
    identity = {
        key: context[key]
        for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
    }
    return {
        "status": "complete",
        **identity,
        "report_package": {
            "report_id": "report_worker_001",
            "markdown": "# NICO Comprehensive Technical Assessment\nCLIENT DELIVERY NOT AUTHORIZED",
            "html": "<html><body>NICO Comprehensive Technical Assessment</body></html>",
            "json": {"identity": identity},
            "pdf_base64": base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii"),
            "pdf_page_count": 1,
            "canonical_truth_sha256": "b" * 64,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _wait_for_terminal(store: ComprehensiveRunStore, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = store.load("comprun_worker_001")
        if record.get("terminal"):
            return record
        time.sleep(0.03)
    raise AssertionError("durable final report worker did not reach terminal state")


def test_immediate_provider_preserves_one_call_review_contract(tmp_path: Path) -> None:
    store = _run_store(tmp_path / "runs.db")
    record = store.create(_record())
    worker = DurableFinalReportWorker(
        store,
        _report,
        inline_grace_seconds=1.0,
        heartbeat_seconds=5,
    )

    result = worker.advance(record)

    assert result["status"] == "review_required"
    assert result["completed_stages"] == list(COMPREHENSIVE_STAGES)
    final = result["stage_results"]["final_comprehensive_report_generation"]
    assert final["report_package"]["report_id"] == "report_worker_001"
    assert final["stage_execution"]["mode"] == "durable_final_report_worker"
    assert final["stage_execution"]["request_lifetime_independent"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_slow_provider_returns_running_while_status_remains_readable(tmp_path: Path) -> None:
    store = _run_store(tmp_path / "runs.db")
    record = store.create(_record())
    release = threading.Event()

    def slow(context: dict) -> dict:
        assert release.wait(6)
        return _report(context)

    worker = DurableFinalReportWorker(
        store,
        slow,
        inline_grace_seconds=0.05,
        heartbeat_seconds=1,
        lease_seconds=30,
    )
    started = time.monotonic()

    running = worker.advance(record)

    assert time.monotonic() - started < 0.8
    assert running["status"] == "running"
    assert running["terminal"] is False
    stage = running["stage_results"]["final_comprehensive_report_generation"]
    assert stage["reason"] == "durable_final_report_worker_running"
    assert stage["stage_execution"]["durable_lease"] is True
    assert stage["stage_execution"]["orphan_timeout_thread_absent"] is True

    read_started = time.monotonic()
    readable = store.load("comprun_worker_001")
    assert time.monotonic() - read_started < 0.5
    assert readable["status"] == "running"
    assert worker.job("comprun_worker_001")["state"] == "running"

    release.set()
    terminal = _wait_for_terminal(store)
    assert terminal["status"] == "review_required"
    assert terminal["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]["report_id"] == "report_worker_001"
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = worker.job("comprun_worker_001")
        if job and job["state"] == "complete":
            break
        time.sleep(0.03)
    assert worker.job("comprun_worker_001")["state"] == "complete"


def test_expired_lease_is_reclaimed_after_worker_process_loss(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    store = _run_store(path)
    record = store.create(_record())
    job_store = ComprehensiveFinalReportJobStore(
        lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    job_store.ensure_schema()
    identity = record["identity"]
    job_store.claim(
        run_id=identity["run_id"],
        repository=identity["repository"],
        commit_sha=identity["commit_sha"],
        evidence_ledger_id=identity["evidence_ledger_id"],
        lease_owner="lost-process",
        lease_seconds=90,
    )
    expired = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE nico_comprehensive_final_report_jobs "
        "SET lease_expires_at = ?, heartbeat_at = ?, updated_at = ? "
        "WHERE run_id = ?",
        (expired, expired, expired, identity["run_id"]),
    )
    connection.commit()
    connection.close()

    replacement = DurableFinalReportWorker(
        store,
        _report,
        inline_grace_seconds=1.0,
        heartbeat_seconds=5,
    )
    result = replacement.advance(record)

    assert result["status"] == "review_required"
    job = replacement.job(identity["run_id"])
    assert job is not None
    assert job["state"] == "complete"
    assert job["attempt"] == 2


def test_unexpired_foreign_lease_prevents_duplicate_provider_execution(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    store = _run_store(path)
    record = store.create(_record())
    job_store = ComprehensiveFinalReportJobStore(
        lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    job_store.ensure_schema()
    identity = record["identity"]
    job_store.claim(
        run_id=identity["run_id"],
        repository=identity["repository"],
        commit_sha=identity["commit_sha"],
        evidence_ledger_id=identity["evidence_ledger_id"],
        lease_owner="active-other-process",
        lease_seconds=90,
    )
    calls = 0

    def should_not_run(context: dict) -> dict:
        nonlocal calls
        calls += 1
        return _report(context)

    contender = DurableFinalReportWorker(
        store,
        should_not_run,
        inline_grace_seconds=0.05,
        heartbeat_seconds=5,
    )

    running = contender.advance(record)

    assert calls == 0
    assert running["status"] == "running"
    assert running["stage_results"]["final_comprehensive_report_generation"][
        "stage_execution"
    ]["durable_lease"] is True
