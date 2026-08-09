from __future__ import annotations

import base64
import sqlite3
import threading
import time
from pathlib import Path

import nico.comprehensive_final_report_execution_boundary_v4 as boundary
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


REPOSITORY = "BoneManTGRM/NICO"
COMMIT_SHA = "a" * 40


def _store(tmp_path: Path) -> ComprehensiveRunStore:
    path = tmp_path / "comprehensive.sqlite3"
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


def _valid_result(context: dict) -> dict:
    pdf = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii")
    identity = {
        key: context[key]
        for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
    }
    return {
        "status": "complete",
        **identity,
        "report_package": {
            "report_id": f"report_{context['run_id']}",
            "markdown": "# NICO Comprehensive\n",
            "html": "<h1>NICO Comprehensive</h1>",
            "pdf_base64": pdf,
            "canonical_truth_sha256": "b" * 64,
            "json": {"identity": identity},
        },
    }


def _wait_for_final(
    store: ComprehensiveRunStore,
    run_id: str,
    timeout: float = 4.0,
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = store.load(run_id)
        if FINAL_REPORT_STAGE_ID in set(current.get("completed_stages") or []):
            return current
        time.sleep(0.02)
    raise AssertionError(f"final report did not publish for {run_id}")


def test_durable_coordinator_owns_provider_lifetime_without_nested_timeout(
    monkeypatch,
) -> None:
    record = _record("comprun_durable_boundary")
    context = _context(record)

    def forbidden_bounded_execution(*_args, **_kwargs):
        raise AssertionError("durable publication must not create a nested timeout worker")

    monkeypatch.setattr(boundary, "_execute_bounded", forbidden_bounded_execution)
    result = boundary.execute_final_report_stage(
        lambda supplied: _valid_result(supplied),
        context,
        timeout_seconds=1,
        durable_coordinator_owns_lifetime=True,
    )

    assert result["status"] == "complete"
    assert result["artifacts_available"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    execution = result["stage_execution"]
    assert execution["provider_lifetime_owner"] == "durable_final_report_coordinator"
    assert execution["durable_coordinator_owns_lifetime"] is True
    assert execution["nested_timeout_thread"] is False
    assert execution["execution_timeout_seconds"] is None
    assert execution["canonical_run_written_only_by_request_thread"] is False


def test_concurrent_final_reports_are_serialized_without_losing_exact_runs(
    tmp_path: Path,
) -> None:
    reset_final_report_publication_tasks_for_tests()
    store = _store(tmp_path)
    first = _record("comprun_capacity_first")
    second = _record("comprun_capacity_second")
    store.create(first)
    store.create(second)

    coordinator = FinalReportPublicationCoordinator(store)
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    release_second = threading.Event()
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def first_executor(context: dict) -> dict:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        first_started.set()
        assert release_first.wait(3.0)
        try:
            return _valid_result(context)
        finally:
            with lock:
                active -= 1

    def second_executor(context: dict) -> dict:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        second_started.set()
        assert release_second.wait(3.0)
        try:
            return _valid_result(context)
        finally:
            with lock:
                active -= 1

    first_claim = coordinator.advance(first, first_executor, _context(first))
    second_claim = coordinator.advance(second, second_executor, _context(second))

    assert first_started.wait(1.0)
    assert second_started.wait(0.15) is False
    assert first_claim["identity"]["run_id"] == "comprun_capacity_first"
    assert second_claim["identity"]["run_id"] == "comprun_capacity_second"
    assert first_claim["client_delivery_allowed"] is False
    assert second_claim["client_delivery_allowed"] is False

    release_first.set()
    first_final = _wait_for_final(store, "comprun_capacity_first")
    assert second_started.wait(1.0)
    release_second.set()
    second_final = _wait_for_final(store, "comprun_capacity_second")

    assert maximum_active == 1
    for final, run_id in (
        (first_final, "comprun_capacity_first"),
        (second_final, "comprun_capacity_second"),
    ):
        assert final["identity"]["run_id"] == run_id
        assert final["identity"]["commit_sha"] == COMMIT_SHA
        result = final["stage_results"][FINAL_REPORT_STAGE_ID]
        assert result["status"] == "complete"
        assert result["report_package"]["pdf_base64"].startswith("JVBER")
        assert result["human_review_required"] is True
        assert result["client_delivery_allowed"] is False
        assert result["stage_execution"]["nested_timeout_thread"] is False
        assert (
            result["stage_execution"]["provider_lifetime_owner"]
            == "durable_final_report_coordinator"
        )

    reset_final_report_publication_tasks_for_tests()
