from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.comprehensive_api_routes as routes
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import COMPREHENSIVE_API_ROUTES, register_comprehensive_api_routes
from nico.comprehensive_capability_registry import execution_plan
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
        "run_id": "comprun_http_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "abc123",
        "evidence_ledger_id": "ledger_http_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _pairs(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method.upper(), str(getattr(route, "path", "")))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }


def test_routes_start_status_and_continue_one_canonical_run(tmp_path: Path) -> None:
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=_controller(tmp_path / "runs.db"))
    client = TestClient(app)

    started = client.post("/assessment/comprehensive-run", json=_payload())
    assert started.status_code == 200
    assert started.json()["run_id"] == "comprun_http_001"
    assert started.json()["service_id"] == "comprehensive"

    status = client.get("/assessment/comprehensive-run/comprun_http_001")
    assert status.status_code == 200
    assert status.json()["integrity_sha256"] == started.json()["integrity_sha256"]

    continued = client.post(
        "/assessment/comprehensive-run/comprun_http_001/continue",
        json={"max_stages": 2},
    )
    assert continued.status_code == 200
    assert len(continued.json()["completed_stages"]) == 2
    assert continued.json()["human_review_required"] is True
    assert continued.json()["client_delivery_allowed"] is False


def test_intake_preserves_explicit_exact_commit_as_first_class_snapshot_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    expected = "a" * 40
    captured: dict = {}

    def fake_snapshot(context: dict) -> dict:
        captured.update(context)
        return {
            "status": "attached",
            "snapshot_id": "snapshot_exact",
            "run_id": context["run_id"],
            "repository": context["repository"],
            "commit_sha": expected,
            "expected_commit_sha": expected,
            "exact_commit_verified": True,
            "human_review_required": True,
        }

    monkeypatch.setattr(routes, "capture_repository_snapshot", fake_snapshot)
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "postgres",
        "durability_verified": False,
        "storage_source": "DATABASE_URL",
    }
    register_comprehensive_api_routes(app, controller=_controller(tmp_path / "intake.db"))

    response = TestClient(app).post(
        "/assessment/comprehensive-intake",
        json={
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_intake",
            "project_id": "project_intake",
            "client_name": "Client",
            "project_name": "Project",
            "expected_commit_sha": expected,
            "authorized_by": f"production_acceptance;expected_commit_sha={expected}",
            "authorization_scope": "authorized defensive repository assessment",
            "authorized": True,
            "authorization_confirmed": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert captured["expected_commit_sha"] == expected
    assert body["repository_snapshot"]["commit_sha"] == expected
    assert body["commit_sha"] == expected
    assert body["persistence"] == {
        "recorded": True,
        "durable": True,
        "adapter": "postgres",
        "storage_source": "DATABASE_URL",
    }
    assert body["human_review_required"] is True
    assert body["client_delivery_allowed"] is False


def test_active_durable_adapter_overrides_stale_false_legacy_flag(tmp_path: Path) -> None:
    for index, adapter in enumerate(("postgres", "sqlite"), start=1):
        app = FastAPI()
        app.state.comprehensive_runtime = {
            "configured": True,
            "persistence_adapter": adapter,
            "durability_verified": False,
            "storage_source": adapter,
        }
        register_comprehensive_api_routes(
            app,
            controller=_controller(tmp_path / f"durable-{adapter}.db"),
        )
        payload = _payload()
        payload["run_id"] = f"comprun_durable_{index}"
        response = TestClient(app).post("/assessment/comprehensive-run", json=payload)
        assert response.status_code == 200
        assert response.json()["persistence"]["recorded"] is True
        assert response.json()["persistence"]["durable"] is True
        assert response.json()["persistence"]["adapter"] == adapter


def test_routes_fail_closed_without_runtime_controller() -> None:
    app = FastAPI()
    register_comprehensive_api_routes(app)
    response = TestClient(app).post("/assessment/comprehensive-run", json=_payload())
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "comprehensive_service_not_configured"
    assert detail["retryable"] is True
    assert detail["human_review_required"] is True
    assert detail["client_delivery_allowed"] is False
    assert "temporarily unavailable" in detail["message"]


def test_routes_translate_validation_missing_and_conflict(tmp_path: Path) -> None:
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=_controller(tmp_path / "runs.db"))
    client = TestClient(app)

    invalid = _payload()
    invalid["commit_sha"] = ""
    assert client.post("/assessment/comprehensive-run", json=invalid).status_code == 422

    assert client.get("/assessment/comprehensive-run/missing").status_code == 404

    assert client.post("/assessment/comprehensive-run", json=_payload()).status_code == 200
    duplicate = client.post("/assessment/comprehensive-run", json=_payload())
    assert duplicate.status_code == 409


def test_registration_is_complete_and_idempotent(tmp_path: Path) -> None:
    app = FastAPI()
    controller = _controller(tmp_path / "runs.db")
    register_comprehensive_api_routes(app, controller=controller)
    register_comprehensive_api_routes(app, controller=controller)

    pairs = _pairs(app)
    assert COMPREHENSIVE_API_ROUTES <= pairs
    for route in COMPREHENSIVE_API_ROUTES:
        assert sum(1 for candidate in pairs if candidate == route) == 1
