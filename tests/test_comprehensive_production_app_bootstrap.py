from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.api.comprehensive_production_bootstrap import install_comprehensive_on_production_app


def _payload() -> dict:
    return {
        "run_id": "comprun_prod_mount_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "immutable-prod-mount",
        "evidence_ledger_id": "ledger_prod_mount_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_production_mount_exposes_complete_fail_closed_routes() -> None:
    app = FastAPI()
    status = install_comprehensive_on_production_app(app)

    assert status["status"] == "blocked"
    assert status["configured"] is False
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
    assert all(count == 1 for count in status["route_counts"].values())

    response = TestClient(app).post("/assessment/comprehensive-run", json=_payload())
    assert response.status_code == 503
    assert response.json()["detail"] == "comprehensive_service_not_configured"


def test_production_mount_is_idempotent_and_preserves_route_identity() -> None:
    app = FastAPI()
    first = install_comprehensive_on_production_app(app)
    second = install_comprehensive_on_production_app(app)

    assert first["route_counts"] == second["route_counts"]
    assert all(count == 1 for count in second["route_counts"].values())
    assert app.state.nico_comprehensive_production_runtime == second


def test_docker_entrypoint_targets_comprehensive_bootstrap() -> None:
    dockerfile = open("Dockerfile", encoding="utf-8").read()
    assert "nico.api.comprehensive_production_bootstrap:app" in dockerfile
    assert "nico.api.production_bootstrap:app --host" not in dockerfile
