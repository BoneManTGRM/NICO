from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.specialist_access_v1 import install_specialist_access
from nico.specialist_all_assessment_gate_v1 import install_all_assessment_access_gate


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/assessment/comprehensive-intake")
    def comprehensive_intake() -> dict[str, str]:
        return {"status": "comprehensive_started"}

    @app.post("/assessment/full-run")
    def full_run() -> dict[str, str]:
        return {"status": "full_started"}

    @app.post("/assessment/mid-run")
    def mid_run() -> dict[str, str]:
        return {"status": "mid_started"}

    @app.post("/assessment/express")
    def express_run() -> dict[str, str]:
        return {"status": "express_started"}

    @app.get("/assessment/full-run/{run_id}/status")
    def full_status(run_id: str) -> dict[str, str]:
        return {"status": "complete", "run_id": run_id}

    @app.get("/reports/{run_id}/approved-delivery")
    def approved_report(run_id: str) -> dict[str, str]:
        return {"status": "available", "run_id": run_id}

    install_specialist_access(app)
    install_all_assessment_access_gate(app)
    return app


def _session(client: TestClient) -> str:
    response = client.post(
        "/assessment/comprehensive-operator/session",
        headers={"X-NICO-Admin-Token": "specialist-password"},
    )
    assert response.status_code == 200
    return str(response.json()["session_token"])


def test_all_assessment_and_report_routes_fail_closed_without_authentication(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "specialist-password")
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "independent-test-signing-secret-with-at-least-thirty-two-bytes",
    )
    client = TestClient(_app())

    assert client.get("/health").status_code == 200
    requests = (
        ("POST", "/assessment/comprehensive-intake"),
        ("POST", "/assessment/full-run"),
        ("POST", "/assessment/mid-run"),
        ("POST", "/assessment/express"),
        ("GET", "/assessment/full-run/full_test/status"),
        ("GET", "/reports/full_test/approved-delivery"),
    )
    for method, path in requests:
        response = client.request(method, path)
        assert response.status_code == 401, (method, path, response.text)
        assert response.json()["detail"]["code"] == "specialist_authentication_required"
        assert response.headers["cache-control"] == "no-store, private, max-age=0"


def test_signed_specialist_session_reaches_every_protected_route(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "specialist-password")
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "independent-test-signing-secret-with-at-least-thirty-two-bytes",
    )
    client = TestClient(_app())
    session = _session(client)
    headers = {"X-NICO-Operator-Session": session}

    expected = (
        ("POST", "/assessment/comprehensive-intake", "comprehensive_started"),
        ("POST", "/assessment/full-run", "full_started"),
        ("POST", "/assessment/mid-run", "mid_started"),
        ("POST", "/assessment/express", "express_started"),
        ("GET", "/assessment/full-run/full_test/status", "complete"),
        ("GET", "/reports/full_test/approved-delivery", "available"),
    )
    for method, path, status in expected:
        response = client.request(method, path, headers=headers)
        assert response.status_code == 200, (method, path, response.text)
        assert response.json()["status"] == status


def test_invalid_raw_or_signed_credentials_fail_closed(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "specialist-password")
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "independent-test-signing-secret-with-at-least-thirty-two-bytes",
    )
    client = TestClient(_app())

    invalid_raw = client.post(
        "/assessment/full-run",
        headers={"X-NICO-Admin-Token": "wrong"},
    )
    assert invalid_raw.status_code == 403
    assert invalid_raw.json()["detail"]["code"] == "specialist_operator_authentication_invalid"

    invalid_session = client.get(
        "/reports/full_test/approved-delivery",
        headers={"X-NICO-Operator-Session": "tampered.session"},
    )
    assert invalid_session.status_code == 401
    assert invalid_session.json()["detail"]["code"] == "specialist_session_invalid_or_expired"
