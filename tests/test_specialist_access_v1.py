from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.specialist_access_v1 import (
    PRODUCTION_PROOF_SCOPE,
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

    @app.post("/assessment/github")
    def legacy_assessment() -> dict[str, str]:
        return {"status": "started"}

    @app.get("/assessment/comprehensive-run/{run_id}")
    def status(run_id: str) -> dict[str, str]:
        return {"status": "running", "run_id": run_id}

    @app.get("/assessment/comprehensive-run/{run_id}/report/pdf")
    def report_pdf(run_id: str) -> dict[str, str]:
        return {"status": "available", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/review")
    def review(run_id: str) -> dict[str, str]:
        return {"status": "reviewed", "run_id": run_id}

    @app.get("/reports/{run_id}/approved-delivery")
    def approved_delivery(run_id: str) -> dict[str, str]:
        return {"status": "available", "run_id": run_id}

    install_specialist_access(app)
    return app


def test_all_assessment_and_report_routes_require_authenticated_specialist(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "test-only-session-secret-with-sufficient-entropy")
    client = TestClient(_app())

    assert client.get("/health").status_code == 200
    requests = (
        ("POST", "/assessment/comprehensive-intake"),
        ("POST", "/assessment/github"),
        ("GET", "/assessment/comprehensive-run/comprun_test/report/pdf"),
        ("GET", "/reports/comprun_test/approved-delivery"),
    )
    for method, path in requests:
        blocked = client.request(method, path)
        assert blocked.status_code == 401, (method, path, blocked.text)
        assert blocked.json()["detail"]["code"] == "specialist_authentication_required"

    wrong = client.post(
        "/assessment/comprehensive-intake",
        headers={"X-NICO-Admin-Token": "wrong"},
    )
    assert wrong.status_code == 403

    for method, path in requests:
        allowed = client.request(
            method,
            path,
            headers={"X-NICO-Admin-Token": "correct horse battery staple"},
        )
        assert allowed.status_code == 200, (method, path, allowed.text)


def test_signed_http_session_authorizes_exact_run_and_report_reads(monkeypatch):
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
    assert login.json()["scope"] == "nico_specialist_operation"

    validation = client.get(
        "/assessment/comprehensive-operator/session",
        headers={"X-NICO-Operator-Session": token},
    )
    assert validation.status_code == 200
    assert validation.json()["scope"] == "nico_specialist_operation"

    for path in (
        "/assessment/comprehensive-run/comprun_test",
        "/assessment/comprehensive-run/comprun_test/report/pdf",
        "/reports/comprun_test/approved-delivery",
    ):
        response = client.get(path, headers={"X-NICO-Operator-Session": token})
        assert response.status_code == 200, (path, response.text)

    tampered = client.get(
        "/assessment/comprehensive-run/comprun_test",
        headers={"X-NICO-Operator-Session": f"{token}x"},
    )
    assert tampered.status_code == 401


def test_production_proof_session_cannot_review_deliver_or_use_unrelated_assessments(monkeypatch):
    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "bounded-proof-session-test-signing-secret")
    client = TestClient(_app())
    claims = {
        "repository": "BoneManTGRM/NICO",
        "repository_id": "1282576027",
        "release_sha": "a" * 40,
        "workflow_ref": "BoneManTGRM/NICO/.github/workflows/spanish-comprehensive-production-proof.yml@refs/heads/main",
        "workflow_sha": "a" * 40,
        "workflow_file": ".github/workflows/spanish-comprehensive-production-proof.yml",
        "run_id": "123456789",
        "run_attempt": "1",
    }
    token, _ = issue_specialist_session(
        {"authority": "github_actions_production_proof"},
        scope=PRODUCTION_PROOF_SCOPE,
        retained_claims=claims,
    )
    headers = {"X-NICO-Operator-Session": token}

    assert client.post("/assessment/comprehensive-intake", headers=headers).status_code == 200
    assert client.get("/assessment/comprehensive-run/comprun_test", headers=headers).status_code == 200
    assert client.get(
        "/assessment/comprehensive-run/comprun_test/report/pdf",
        headers=headers,
    ).status_code == 200

    forbidden = (
        ("POST", "/assessment/comprehensive-run/comprun_test/review"),
        ("GET", "/reports/comprun_test/approved-delivery"),
        ("POST", "/assessment/github"),
    )
    for method, path in forbidden:
        response = client.request(method, path, headers=headers)
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["detail"]["code"] == "production_proof_session_scope_forbidden"


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


def test_session_signing_never_reuses_operator_or_admin_credentials(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "operator-password")
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "site-wide-admin-token")
    monkeypatch.delenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="specialist_session_signing_secret_unavailable"):
        issue_specialist_session({"authority": "nico_comprehensive_operator"})

    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "too-short")
    with pytest.raises(RuntimeError, match="specialist_session_signing_secret_unavailable"):
        issue_specialist_session({"authority": "nico_comprehensive_operator"})
