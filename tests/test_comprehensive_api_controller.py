from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


def _controller(path: Path) -> ComprehensiveApiController:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    executors = {}
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

        executors[capability] = execute
    return ComprehensiveApiController(ComprehensiveRunService(store, executors))


def _payload() -> dict:
    return {
        "run_id": "comprun_api_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "abc123",
        "evidence_ledger_id": "ledger_api_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_start_returns_canonical_two_service_identity(tmp_path: Path) -> None:
    response = _controller(tmp_path / "runs.db").start(_payload())

    assert response["service_id"] == "comprehensive"
    assert response["operation"] == "started"
    assert response["run_id"] == "comprun_api_001"
    assert response["repository"] == "BoneManTGRM/NICO"
    assert response["status"] == "ready"
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False
    assert "mid" not in response
    assert "full" not in response
    assert "deep" not in response


def test_start_requires_explicit_authorization(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    payload = _payload()
    payload["authorization_confirmed"] = False

    with pytest.raises(ValueError, match="explicit_authorization_required"):
        controller.start(payload)


def test_status_returns_exact_persisted_run(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    started = controller.start(_payload())
    status = controller.status(started["run_id"])

    assert status["operation"] == "status"
    assert status["integrity_sha256"] == started["integrity_sha256"]
    assert status["revision"] == started["revision"]
    assert status["record"] == started["record"]


def test_continue_can_advance_bounded_number_of_stages(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    controller.start(_payload())

    response = controller.continue_run("comprun_api_001", {"max_stages": 2})

    assert response["operation"] == "continued"
    assert response["completed_stages"] == list(COMPREHENSIVE_STAGES[:2])
    assert response["revision"] == 3
    assert response["terminal"] is False
    assert response["client_delivery_allowed"] is False


def test_continue_without_bound_runs_to_human_review(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    controller.start(_payload())

    response = controller.continue_run("comprun_api_001")

    assert response["status"] == "review_required"
    assert response["progress_percent"] == 100.0
    assert response["completed_stages"] == list(COMPREHENSIVE_STAGES)
    assert response["terminal"] is True
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False


def test_request_validation_rejects_missing_identity_and_invalid_bounds(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    payload = _payload()
    payload["commit_sha"] = ""

    with pytest.raises(ValueError, match="commit_sha_required"):
        controller.start(payload)

    controller.start(_payload())
    with pytest.raises(ValueError, match="max_stages_must_be_non_negative"):
        controller.continue_run("comprun_api_001", {"max_stages": -1})
