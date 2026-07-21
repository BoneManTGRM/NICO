from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import (
    ComprehensiveApiController,
    _display_progress,
    _ordered_record,
)
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_production_capabilities import build_production_capability_executors
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


def _controller(path: Path) -> ComprehensiveApiController:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    executors = {}
    for item in execution_plan():
        capability = str(item["capability"])

        def execute(context, *, _capability=capability):
            return {
                "status": "complete",
                "capability": _capability,
                "summary": f"Completed {_capability} for the exact run.",
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
            }

        executors[capability] = execute
    return ComprehensiveApiController(ComprehensiveRunService(store, executors))


def _payload() -> dict:
    return {
        "run_id": "comprun_live_truth_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_live_truth_001",
        "customer_id": "customer_live_truth",
        "project_id": "project_live_truth",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_status_and_continue_keep_durable_runtime_truth(tmp_path: Path) -> None:
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "durability_verified": True,
        "persistence_adapter": "sqlite",
        "storage_source": "test_sqlite",
    }
    register_comprehensive_api_routes(
        app,
        controller=_controller(tmp_path / "live-truth.db"),
    )
    client = TestClient(app)

    started = client.post("/assessment/comprehensive-run", json=_payload())
    status = client.get("/assessment/comprehensive-run/comprun_live_truth_001")
    continued = client.post(
        "/assessment/comprehensive-run/comprun_live_truth_001/continue",
        json={"max_stages": 2},
    )

    for response in (started, status, continued):
        assert response.status_code == 200
        persistence = response.json()["persistence"]
        assert persistence == {
            "recorded": True,
            "durable": True,
            "adapter": "sqlite",
            "storage_source": "test_sqlite",
        }
        assert response.json()["human_review_required"] is True
        assert response.json()["client_delivery_allowed"] is False


def test_response_stage_results_are_reordered_after_jsonb_style_shuffle() -> None:
    shuffled = {
        "stage_results": {
            "dependency_security_static_analysis": {"status": "running"},
            "repository_and_delivery_evidence": {"status": "complete"},
            "authorization_and_scope": {"status": "complete"},
            "immutable_repository_snapshot": {"status": "complete"},
        }
    }

    ordered = _ordered_record(shuffled)

    assert list(ordered["stage_results"]) == list(COMPREHENSIVE_STAGES[:4])
    assert list(shuffled["stage_results"])[0] == "dependency_security_static_analysis"


def test_active_scanner_progress_moves_response_without_mutating_record_progress() -> None:
    canonical = round((3 / len(COMPREHENSIVE_STAGES)) * 100, 2)
    record = {
        "terminal": False,
        "current_stage": "dependency_security_static_analysis",
        "progress_percent": canonical,
        "stage_results": {
            "dependency_security_static_analysis": {
                "status": "running",
                "scanner": {"progress_percent": 64},
            }
        },
    }

    display, active = _display_progress(record)

    assert active == 64.0
    assert display > canonical
    assert display < round((4 / len(COMPREHENSIVE_STAGES)) * 100, 2)
    assert record["progress_percent"] == canonical


def test_terminal_progress_never_uses_active_stage_interpolation() -> None:
    display, active = _display_progress(
        {
            "terminal": True,
            "progress_percent": 100,
            "current_stage": "client_acceptance_pending",
            "stage_results": {
                "client_acceptance_pending": {
                    "status": "review_required",
                    "stage_progress_percent": 25,
                }
            },
        }
    )

    assert display == 100.0
    assert active is None


def test_native_authorization_stage_has_customer_readable_summary_and_evidence() -> None:
    app = FastAPI()
    executor = build_production_capability_executors(app)["authorization"]
    result = executor(
        {
            "service_id": "comprehensive",
            "run_id": "comprun_authorization_truth_001",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "evidence_ledger_id": "ledger_authorization_truth_001",
        }
    )

    assert result["status"] == "complete"
    assert "read-only scope" in result["summary"]
    assert result["evidence"]["authorization_confirmed"] is True
    assert result["evidence"]["repository"] == "BoneManTGRM/NICO"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
