from __future__ import annotations

import base64
import sqlite3
import time
from pathlib import Path

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_final_report_execution_boundary_v3 import (
    FINAL_REPORT_STAGE_ID,
    execute_final_report_stage,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


def _context() -> dict:
    return {
        "run_id": "comprun_atomic_report",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_atomic_report",
        "customer_id": "customer_atomic_report",
        "project_id": "project_atomic_report",
        "prior_stage_results": {},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _report_result(context: dict) -> dict:
    identity = {
        "run_id": context["run_id"],
        "repository": context["repository"],
        "commit_sha": context["commit_sha"],
        "evidence_ledger_id": context["evidence_ledger_id"],
    }
    pdf = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii")
    return {
        "status": "complete",
        **identity,
        "report_package": {
            "report_id": "report_atomic_exact",
            "markdown": "# NICO Comprehensive Technical Assessment\n\nCLIENT DELIVERY NOT AUTHORIZED\n",
            "html": "<html><body>NICO Comprehensive Technical Assessment</body></html>",
            "pdf_base64": pdf,
            "pdf_page_count": 1,
            "json": {"identity": identity},
            "canonical_truth_sha256": "b" * 64,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_final_report_completes_inside_atomic_request_boundary() -> None:
    context = _context()
    calls = 0

    def executor(payload: dict) -> dict:
        nonlocal calls
        calls += 1
        return _report_result(payload)

    result = execute_final_report_stage(
        executor,
        context,
        timeout_seconds=5,
    )

    assert calls == 1
    assert result["status"] == "complete"
    assert result["report_package"]["report_id"] == "report_atomic_exact"
    assert result["artifacts_available"] is True
    assert result["stage_execution"]["mode"] == "atomic_final_report_publication"
    assert result["stage_execution"]["detached_background_execution"] is False
    assert result["stage_execution"]["canonical_run_written_only_by_request_thread"] is True
    assert result["stage_execution"]["artifact_validation_complete"] is True
    assert result["evidence"]["pdf_valid"] is True
    assert result["evidence"]["exact_run_identity_verified"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_final_report_cannot_return_background_in_progress() -> None:
    context = _context()

    def executor(payload: dict) -> dict:
        return _report_result(payload)

    result = execute_final_report_stage(executor, context, timeout_seconds=5)
    assert result.get("reason") != "background_stage_execution_in_progress"
    assert result["status"] in {"complete", "blocked"}


def test_invalid_or_identity_mismatched_report_fails_closed() -> None:
    context = _context()

    def executor(payload: dict) -> dict:
        result = _report_result(payload)
        result["report_package"]["json"]["identity"]["commit_sha"] = "c" * 40
        return result

    blocked = execute_final_report_stage(executor, context, timeout_seconds=5)
    assert blocked["status"] == "blocked"
    assert blocked["reason"] == "final_report_identity_mismatch"
    assert blocked["retryable"] is True
    assert blocked["human_review_required"] is True
    assert blocked["client_delivery_allowed"] is False


def test_non_returning_report_fails_closed_instead_of_remaining_at_83_percent() -> None:
    context = _context()

    def executor(_payload: dict) -> dict:
        time.sleep(2)
        return {"status": "complete"}

    started = time.monotonic()
    blocked = execute_final_report_stage(
        executor,
        context,
        timeout_seconds=1,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 1.5
    assert blocked["status"] == "blocked"
    assert blocked["error_code"] == "stage_execution_timeout"
    assert blocked["stage_execution"]["mode"] == "atomic_final_report_publication"
    assert blocked["stage_execution"]["detached_background_execution"] is False
    assert blocked["client_delivery_allowed"] is False


def _store(path: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def test_run_service_atomically_persists_final_report_and_advances(monkeypatch, tmp_path: Path) -> None:
    import nico.comprehensive_run_service as run_service

    # Keep this proof deterministic: earlier long-stage behavior is covered separately.
    monkeypatch.setattr(run_service, "BACKGROUND_STAGE_IDS", frozenset())
    calls: dict[str, int] = {}
    executors: dict[str, object] = {}
    for item in execution_plan():
        capability = item["capability"]

        if capability == "final_report_generation":
            def final_report(context: dict) -> dict:
                calls["final_report_generation"] = calls.get("final_report_generation", 0) + 1
                return _report_result(context)

            executors[capability] = final_report
            continue

        def complete(context: dict, *, _capability: str = capability) -> dict:
            calls[_capability] = calls.get(_capability, 0) + 1
            return {
                "status": "complete",
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
                "evidence": {"capability": _capability},
                "human_review_required": True,
                "client_delivery_allowed": False,
            }

        executors[capability] = complete

    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), executors)
    service.start(
        run_id="comprun_atomic_service",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_atomic_service",
        customer_id="customer_atomic_service",
        project_id="project_atomic_service",
        authorized=True,
    )

    final_index = COMPREHENSIVE_STAGES.index(FINAL_REPORT_STAGE_ID)
    before = service.resume("comprun_atomic_service", max_stages=final_index)
    assert len(before["completed_stages"]) == final_index
    prior_results = dict(before["stage_results"])

    after = service.resume("comprun_atomic_service", max_stages=1)
    assert FINAL_REPORT_STAGE_ID in after["completed_stages"]
    final = after["stage_results"][FINAL_REPORT_STAGE_ID]
    assert final["status"] == "complete"
    assert final["report_package"]["report_id"] == "report_atomic_exact"
    assert final["stage_execution"]["mode"] == "atomic_final_report_publication"
    assert final["stage_execution"]["detached_background_execution"] is False
    assert calls["final_report_generation"] == 1
    for stage_id, value in prior_results.items():
        assert after["stage_results"][stage_id] == value
    assert after["human_review_required"] is True
    assert after["client_delivery_allowed"] is False

    reloaded = service.load("comprun_atomic_service")
    assert reloaded["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]["report_id"] == "report_atomic_exact"
    assert calls["final_report_generation"] == 1
