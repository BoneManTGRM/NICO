from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_runtime import configure_comprehensive_runtime


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


def _payload() -> dict:
    return {
        "run_id": "comprun_runtime_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "immutable123",
        "evidence_ledger_id": "ledger_runtime_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_runtime_mounts_durable_native_routes(tmp_path: Path) -> None:
    path = tmp_path / "comprehensive.db"
    app = FastAPI()
    configure_comprehensive_runtime(
        app,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(path),
        dialect="sqlite",
    )

    client = TestClient(app)
    started = client.post("/assessment/comprehensive-run", json=_payload())
    assert started.status_code == 200
    assert started.json()["run_id"] == "comprun_runtime_001"

    completed = client.post("/assessment/comprehensive-run/comprun_runtime_001/continue")
    assert completed.status_code == 200
    assert completed.json()["status"] == "review_required"
    assert completed.json()["progress_percent"] == 100.0
    assert completed.json()["human_review_required"] is True
    assert completed.json()["client_delivery_allowed"] is False

    restarted = FastAPI()
    configure_comprehensive_runtime(
        restarted,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    restored = TestClient(restarted).get("/assessment/comprehensive-run/comprun_runtime_001")
    assert restored.status_code == 200
    assert restored.json()["integrity_sha256"] == completed.json()["integrity_sha256"]
    assert restored.json()["revision"] == completed.json()["revision"]


def test_runtime_rejects_missing_capabilities(tmp_path: Path) -> None:
    app = FastAPI()
    executors = _executors()
    executors.pop(next(iter(executors)))

    with pytest.raises(RuntimeError, match="comprehensive_capabilities_missing"):
        configure_comprehensive_runtime(
            app,
            capability_executors=executors,
            connection_factory=lambda: sqlite3.connect(tmp_path / "missing.db"),
            dialect="sqlite",
        )

    assert not any(str(getattr(route, "path", "")).startswith("/assessment/comprehensive-run") for route in app.routes)


def test_runtime_requires_postgres_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="comprehensive_database_url_required"):
        configure_comprehensive_runtime(FastAPI(), capability_executors=_executors())

    with pytest.raises(RuntimeError, match="comprehensive_database_url_must_be_postgres"):
        configure_comprehensive_runtime(
            FastAPI(),
            capability_executors=_executors(),
            database_url="sqlite:///unsafe.db",
        )


def test_runtime_metadata_discloses_durable_boundary_without_secrets(tmp_path: Path) -> None:
    app = FastAPI()
    configure_comprehensive_runtime(
        app,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(tmp_path / "metadata.db"),
        dialect="sqlite",
    )

    metadata = app.state.comprehensive_runtime
    assert metadata["service_id"] == "comprehensive"
    assert metadata["configured"] is True
    assert metadata["persistence_adapter"] == "sqlite"
    assert metadata["required_capability_count"] == len(execution_plan())
    assert metadata["human_review_required"] is True
    assert metadata["client_delivery_allowed"] is False
    assert "database_url" not in metadata
