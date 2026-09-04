from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.specialist_access_v1 import (
    install_specialist_access,
    issue_specialist_session,
    validate_specialist_session,
)


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/assessment/comprehensive-intake")
    def intake() -> dict[str, str]:
        return {"status": "started"}

    @app.get("/assessment/comprehensive-run/{run_id}")
    def status(run_id: str) -> dict[str, str]:
        return {"status": "running", "run_id": run_id}

    install_specialist_access(app)
    return app


def test_comprehensive_routes_require_authenticated_specialist(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "test-only-session-secret-with-sufficient-entropy")
    client = TestClient(_app())

    assert client.get("/health").status_code == 200
    blocked = client.post("/assessment/comprehensive-intake")
    assert blocked.status_code == 401
    assert blocked.json()["detail"]["code"] == "specialist_authentication_required"

    wrong = client.post(
        "/assessment/comprehensive-intake",
        headers={"X-NICO-Admin-Token": "wrong"},
    )
    assert wrong.status_code == 403

    allowed = client.post(
        "/assessment/comprehensive-intake",
        headers={"X-NICO-Admin-Token": "correct horse battery staple"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "started"


def test_signed_http_session_authorizes_exact_run_reads(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "operator-password")
    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "separate-test-session-signing-secret")
    client = TestClient(_app())

    login = client.post(
        "/assessment/comprehensive-operator/session",
        headers={"X-NICO-Admin-Token": "operator-password"},
    )
    assert login.status_code == 200
    token = login.json()["session_token"]
    assert token and "operator-password" not in token

    validation = client.get(
        "/assessment/comprehensive-operator/session",
        headers={"X-NICO-Operator-Session": token},
    )
    assert validation.status_code == 200

    status = client.get(
        "/assessment/comprehensive-run/comprun_test",
        headers={"X-NICO-Operator-Session": token},
    )
    assert status.status_code == 200
    assert status.json()["run_id"] == "comprun_test"

    tampered = client.get(
        "/assessment/comprehensive-run/comprun_test",
        headers={"X-NICO-Operator-Session": f"{token}x"},
    )
    assert tampered.status_code == 401


def test_session_expiration_and_tamper_fail_closed(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "operator-password")
    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "another-test-session-signing-secret")
    token, _ = issue_specialist_session(
        {"authority": "nico_comprehensive_operator"},
        now=1_000,
    )
    assert validate_specialist_session(token, now=1_001) is not None
    assert validate_specialist_session(token, now=100_000) is None
    assert validate_specialist_session(f"{token[:-1]}x", now=1_001) is None
