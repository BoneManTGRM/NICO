from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.final_review_operator_api as operator


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    app = FastAPI()

    @app.post("/reports/final-review/{approval_id}/{state}")
    def legacy_transition(approval_id: str, state: str):
        return {"approval_id": approval_id, "state": state}

    operator.register_final_review_operator_routes(app)
    return TestClient(app)


def test_operator_routes_require_admin_token(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/operations/final-review/express/run_1")

    assert response.status_code == 403
    assert response.json()["detail"]["status"] == "blocked"


def test_legacy_final_review_write_is_also_admin_gated(monkeypatch) -> None:
    client = _client(monkeypatch)

    blocked = client.post("/reports/final-review/approval_1/approved")
    allowed = client.post(
        "/reports/final-review/approval_1/approved",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert blocked.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["state"] == "approved"


def test_operator_status_supports_express_and_comprehensive(monkeypatch) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        operator,
        "_review_status",
        lambda service, run_id, customer_id, project_id: {
            "status": "ok",
            "service": service,
            "run_id": run_id,
            "customer_id": customer_id,
            "project_id": project_id,
        },
    )

    express = client.get(
        "/operations/final-review/express/express_run_1?customer_id=c1&project_id=p1",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    comprehensive = client.get(
        "/operations/final-review/comprehensive/comprun_1?customer_id=c2&project_id=p2",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert express.status_code == 200
    assert express.json()["service"] == "express"
    assert comprehensive.status_code == 200
    assert comprehensive.json()["service"] == "comprehensive"


def test_operator_review_requires_supported_service(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get(
        "/operations/final-review/mid/midrun_1",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert response.status_code == 400
    assert "express or comprehensive" in response.json()["detail"]["message"]


def test_operator_transition_requires_reviewer_note_for_rejection(monkeypatch) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        operator,
        "_transition_review",
        lambda service, approval_id, state, actor, note: {
            "status": "ok",
            "service": service,
            "approval_id": approval_id,
            "state": state,
            "actor": actor,
            "note": note,
        },
    )

    response = client.post(
        "/operations/final-review/express/approval_1/rejected",
        headers={"X-NICO-Admin-Token": "operator-secret"},
        json={"actor": "Reviewer", "note": "Evidence is incomplete."},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "rejected"
    assert response.json()["actor"] == "Reviewer"
