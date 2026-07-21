from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_production_bootstrap import install_comprehensive_production_bootstrap


def _executors() -> dict:
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
    return executors


def _payload(run_id: str = "comprun_bootstrap_001") -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "immutable-bootstrap",
        "evidence_ledger_id": f"ledger_{run_id}",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_missing_capabilities_mount_complete_routes_but_fail_closed() -> None:
    app = FastAPI()
    controller = install_comprehensive_production_bootstrap(app)

    assert controller is None
    assert app.state.comprehensive_runtime["configured"] is False
    assert app.state.comprehensive_runtime["status"] == "blocked"
    assert app.state.comprehensive_runtime["client_delivery_allowed"] is False

    response = TestClient(app).post("/assessment/comprehensive-run", json=_payload())
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "comprehensive_service_not_configured"
    assert detail["retryable"] is True
    assert detail["human_review_required"] is True
    assert detail["client_delivery_allowed"] is False


def test_missing_durable_storage_fails_closed_without_leaking_credentials(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "false")
    app = FastAPI()
    controller = install_comprehensive_production_bootstrap(app, capability_executors=_executors())

    assert controller is None
    metadata = app.state.comprehensive_runtime
    assert metadata["reason"] == "comprehensive_durable_storage_required"
    assert metadata["persistence_adapter"] == "unavailable"
    assert "database_url" not in metadata
    assert metadata["human_review_required"] is True
    assert metadata["client_delivery_allowed"] is False


def test_explicit_sqlite_durable_fallback_activates_without_database_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "production-fallback.sqlite3"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "true")
    monkeypatch.setenv("NICO_SQLITE_PATH", str(path))
    app = FastAPI()

    controller = install_comprehensive_production_bootstrap(
        app,
        capability_executors=_executors(),
    )

    assert controller is not None
    runtime = app.state.comprehensive_runtime
    assert runtime["configured"] is True
    assert runtime["status"] == "ready"
    assert runtime["persistence_adapter"] == "sqlite"
    assert runtime["storage_source"] == "configured_durable_sqlite"
    assert runtime["durability_verified"] is True
    assert runtime["human_review_required"] is True
    assert runtime["client_delivery_allowed"] is False
    assert path.exists()

    client = TestClient(app)
    started = client.post("/assessment/comprehensive-run", json=_payload())
    assert started.status_code == 200
    completed = client.post("/assessment/comprehensive-run/comprun_bootstrap_001/continue")
    assert completed.status_code == 200
    assert completed.json()["status"] == "review_required"
    assert completed.json()["progress_percent"] == 100.0


def test_later_installation_upgrades_existing_routes_to_durable_controller(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.db"
    app = FastAPI()
    install_comprehensive_production_bootstrap(app)

    controller = install_comprehensive_production_bootstrap(
        app,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    assert controller is not None
    assert app.state.comprehensive_runtime["configured"] is True
    assert app.state.comprehensive_runtime["status"] == "ready"

    client = TestClient(app)
    started = client.post("/assessment/comprehensive-run", json=_payload())
    assert started.status_code == 200
    completed = client.post("/assessment/comprehensive-run/comprun_bootstrap_001/continue")
    assert completed.status_code == 200
    assert completed.json()["status"] == "review_required"
    assert completed.json()["progress_percent"] == 100.0
    assert completed.json()["human_review_required"] is True
    assert completed.json()["client_delivery_allowed"] is False


def test_restart_reuses_exact_persisted_record(tmp_path: Path) -> None:
    path = tmp_path / "restart.db"
    app = FastAPI()
    install_comprehensive_production_bootstrap(
        app,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    client = TestClient(app)
    assert client.post("/assessment/comprehensive-run", json=_payload()).status_code == 200
    terminal = client.post("/assessment/comprehensive-run/comprun_bootstrap_001/continue").json()

    restarted = FastAPI()
    install_comprehensive_production_bootstrap(
        restarted,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    restored = TestClient(restarted).get("/assessment/comprehensive-run/comprun_bootstrap_001")
    assert restored.status_code == 200
    assert restored.json()["revision"] == terminal["revision"]
    assert restored.json()["integrity_sha256"] == terminal["integrity_sha256"]


def test_environment_sqlite_fallback_survives_process_restart(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "environment-restart.sqlite3"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "true")
    monkeypatch.setenv("NICO_SQLITE_PATH", str(path))

    first = FastAPI()
    install_comprehensive_production_bootstrap(first, capability_executors=_executors())
    first_client = TestClient(first)
    assert first_client.post(
        "/assessment/comprehensive-run",
        json=_payload("comprun_environment_restart"),
    ).status_code == 200
    terminal = first_client.post(
        "/assessment/comprehensive-run/comprun_environment_restart/continue"
    ).json()

    restarted = FastAPI()
    install_comprehensive_production_bootstrap(restarted, capability_executors=_executors())
    restored = TestClient(restarted).get(
        "/assessment/comprehensive-run/comprun_environment_restart"
    )
    assert restored.status_code == 200
    assert restored.json()["revision"] == terminal["revision"]
    assert restored.json()["integrity_sha256"] == terminal["integrity_sha256"]


def test_repeated_ready_install_is_idempotent(tmp_path: Path) -> None:
    app = FastAPI()
    first = install_comprehensive_production_bootstrap(
        app,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(tmp_path / "idempotent.db"),
        dialect="sqlite",
    )
    second = install_comprehensive_production_bootstrap(app)

    assert second is first
    paths = [str(getattr(route, "path", "")) for route in app.routes]
    assert paths.count("/assessment/comprehensive-run") == 1
    assert paths.count("/assessment/comprehensive-run/{run_id}") == 1
    assert paths.count("/assessment/comprehensive-run/{run_id}/continue") == 1
