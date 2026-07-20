from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_production_bootstrap import install_comprehensive_production_bootstrap
from nico.comprehensive_production_capabilities import (
    PROVIDER_STATE_KEY,
    build_production_capability_executors,
)


def _payload() -> dict:
    return {
        "run_id": "comprun_provider_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "immutable-provider",
        "evidence_ledger_id": "ledger_provider_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_provider_map_is_complete_but_missing_evidence_fails_closed(tmp_path: Path) -> None:
    app = FastAPI()
    executors = build_production_capability_executors(app)
    assert set(executors) == {str(item["capability"]) for item in execution_plan()}

    controller = install_comprehensive_production_bootstrap(
        app,
        capability_executors=executors,
        connection_factory=lambda: sqlite3.connect(tmp_path / "providers.db"),
        dialect="sqlite",
    )
    assert controller is not None

    client = TestClient(app)
    assert client.post("/assessment/comprehensive-run", json=_payload()).status_code == 200

    authorization = client.post(
        "/assessment/comprehensive-run/comprun_provider_001/continue",
        json={"max_stages": 1},
    )
    assert authorization.status_code == 200
    assert authorization.json()["completed_stages"] == ["authorization_and_scope"]

    blocked = client.post(
        "/assessment/comprehensive-run/comprun_provider_001/continue",
        json={"max_stages": 1},
    )
    assert blocked.status_code == 200
    body = blocked.json()
    record = body["record"]
    assert body["status"] == "blocked"
    assert body["current_stage"] == "immutable_repository_snapshot"
    assert record["status"] == "blocked"
    assert record["terminal"] is True
    assert record["completed_stages"] == ["authorization_and_scope"]
    result = record["stage_results"]["immutable_repository_snapshot"]
    assert result["status"] == "blocked"
    assert result["reason"] == "comprehensive_provider_missing:snapshot"
    assert result["evidence_available"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_dynamic_provider_is_used_without_remounting_routes(tmp_path: Path) -> None:
    app = FastAPI()
    executors = build_production_capability_executors(app)
    app.state.__setattr__(
        PROVIDER_STATE_KEY,
        {
            "snapshot": lambda context: {
                "status": "complete",
                "snapshot_verified": True,
                "observed_commit_sha": context["commit_sha"],
            }
        },
    )
    install_comprehensive_production_bootstrap(
        app,
        capability_executors=executors,
        connection_factory=lambda: sqlite3.connect(tmp_path / "dynamic.db"),
        dialect="sqlite",
    )

    client = TestClient(app)
    assert client.post("/assessment/comprehensive-run", json=_payload()).status_code == 200
    continued = client.post(
        "/assessment/comprehensive-run/comprun_provider_001/continue",
        json={"max_stages": 2},
    )
    assert continued.status_code == 200
    body = continued.json()
    assert body["completed_stages"] == [
        "authorization_and_scope",
        "immutable_repository_snapshot",
    ]
    snapshot = body["record"]["stage_results"]["immutable_repository_snapshot"]
    assert snapshot["snapshot_verified"] is True
    assert snapshot["observed_commit_sha"] == "immutable-provider"


def test_provider_status_is_sanitized_and_truthful() -> None:
    app = FastAPI()
    app.state.__setattr__(PROVIDER_STATE_KEY, {"snapshot": lambda context: {"status": "complete"}})
    build_production_capability_executors(app)

    status = app.state.nico_comprehensive_capability_provider_status
    assert status["fail_closed"] is True
    assert "authorization" in status["available_capabilities"]
    assert "snapshot" in status["available_capabilities"]
    assert "report_generation" in status["missing_capabilities"]
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
    assert "DATABASE_URL" not in repr(status)
