from __future__ import annotations

import base64
import sqlite3
import threading
import time
from pathlib import Path

import nico.comprehensive_final_report_background_v1 as background
from nico.comprehensive_blocked_run_recovery_v1 import (
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_final_report_background_v1 import FinalReportPublicationCoordinator
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
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
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _valid_result(context: dict, *, suffix: str = "ok") -> dict:
    pdf = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii")
    identity = {
        key: context[key]
        for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
    }
    return {
        "status": "complete",
        **identity,
        "report_package": {
            "report_id": f"report_{context['run_id']}_{suffix}",
            "markdown": "# NICO Comprehensive\n",
            "html": "<h1>NICO Comprehensive</h1>",
            "pdf_base64": pdf,
            "canonical_truth_sha256": "d" * 64,
            "json": {"identity": identity},
        },
    }


def _wait_for_terminal(store: ComprehensiveRunStore, run_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    last = store.load(run_id)
    while time.time() < deadline:
        last = store.load(run_id)
        if last.get("terminal") is True:
            return last
        time.sleep(0.02)
    raise AssertionError(f"run did not become terminal: {run_id}: {last.get('status')}")


def _wait_for_complete(store: ComprehensiveRunStore, run_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    last = store.load(run_id)
    while time.time() < deadline:
        last = store.load(run_id)
        if FINAL_REPORT_STAGE_ID in set(last.get("completed_stages") or []):
            return last
        time.sleep(0.02)
    raise AssertionError(f"final report did not complete: {run_id}: {last.get('status')}")


def _accelerate_watchdog(monkeypatch) -> None:
    monkeypatch.setattr(background, "_heartbeat_seconds", lambda: 0.02)
    monkeypatch.setattr(background, "_max_publication_seconds", lambda: 0.12)
    monkeypatch.setattr(background, "_max_queue_seconds", lambda: 5.0)


def test_watchdog_expires_hung_renderer_without_second_advance(tmp_path: Path, monkeypatch) -> None:
    background.reset_final_report_publication_tasks_for_tests()
    _accelerate_watchdog(monkeypatch)
    store = _store(tmp_path)
    record = _record("comprun_watchdog_hung")
    store.create(record)
    coordinator = FinalReportPublicationCoordinator(store)
    started = threading.Event()
    release = threading.Event()

    def hung_executor(context: dict) -> dict:
        started.set()
        assert release.wait(3.0)
        return _valid_result(context, suffix="late")

    claimed = coordinator.advance(record, hung_executor, _context(record))
    assert started.wait(1.0)
    lease_id = claimed["stage_results"][FINAL_REPORT_STAGE_ID]["stage_execution"]["lease_id"]

    terminal = _wait_for_terminal(store, record["identity"]["run_id"])
    result = terminal["stage_results"][FINAL_REPORT_STAGE_ID]
    assert terminal["status"] == "blocked"
    assert result["status"] == "blocked"
    assert result["reason"] == "final_report_publication_deadline_exceeded"
    assert result["stage_execution"]["deadline_enforcement_mode"] == (
        "autonomous_watchdog_and_advance"
    )
    assert store.load_final_report_job(lease_id)["status"] == "expired"

    release.set()
    time.sleep(0.1)
    persisted = store.load(record["identity"]["run_id"])
    assert persisted["status"] == "blocked"
    assert persisted["stage_results"][FINAL_REPORT_STAGE_ID]["reason"] == (
        "final_report_publication_deadline_exceeded"
    )
    assert store.load_final_report_job(lease_id)["status"] == "expired"
    background.reset_final_report_publication_tasks_for_tests()


def test_expired_renderer_reclaims_capacity_and_late_result_is_fenced(tmp_path: Path, monkeypatch) -> None:
    background.reset_final_report_publication_tasks_for_tests()
    _accelerate_watchdog(monkeypatch)
    store = _store(tmp_path)
    record = _record("comprun_watchdog_recovery")
    store.create(record)
    coordinator = FinalReportPublicationCoordinator(store)

    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()

    def first_executor(context: dict) -> dict:
        first_started.set()
        assert release_first.wait(3.0)
        return _valid_result(context, suffix="stale")

    claimed = coordinator.advance(record, first_executor, _context(record))
    assert first_started.wait(1.0)
    first_lease = claimed["stage_results"][FINAL_REPORT_STAGE_ID]["stage_execution"]["lease_id"]
    blocked = _wait_for_terminal(store, record["identity"]["run_id"])
    assert blocked["stage_results"][FINAL_REPORT_STAGE_ID]["reason"] == (
        "final_report_publication_deadline_exceeded"
    )

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)
    recovered = store.save(recovered, expected_revision=int(blocked["revision"]))

    def second_executor(context: dict) -> dict:
        second_started.set()
        return _valid_result(context, suffix="recovered")

    coordinator.advance(recovered, second_executor, _context(recovered))
    assert second_started.wait(1.0), "expired renderer must not keep logical capacity forever"
    completed = _wait_for_complete(store, record["identity"]["run_id"])
    assert completed["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]["report_id"].endswith(
        "_recovered"
    )

    release_first.set()
    time.sleep(0.1)
    persisted = store.load(record["identity"]["run_id"])
    assert persisted["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]["report_id"].endswith(
        "_recovered"
    )
    assert store.load_final_report_job(first_lease)["status"] == "expired"
    background.reset_final_report_publication_tasks_for_tests()
