from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nico.github_actions_proof_auth_v1 import validate_github_actions_claims
from nico.specialist_access_v1 import (
    GITHUB_ACTIONS_SESSION_ROUTE,
    PRODUCTION_PROOF_SCOPE,
    install_specialist_access,
    issue_specialist_session,
    validate_specialist_session,
)


SHA = "a" * 40
WORKFLOW_REF = (
    "BoneManTGRM/NICO/.github/workflows/"
    "spanish-comprehensive-production-proof.yml@refs/heads/main"
)
CLAIMS = {
    "repository": "BoneManTGRM/NICO",
    "ref": "refs/heads/main",
    "sha": SHA,
    "event_name": "push",
    "sub": "repo:BoneManTGRM/NICO:ref:refs/heads/main",
    "workflow_ref": WORKFLOW_REF,
    "run_id": "33899900001",
    "run_attempt": "1",
    "actor": "BoneManTGRM",
}


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/assessment/comprehensive-intake")
    def intake() -> dict[str, str]:
        return {"status": "started"}

    @app.get("/assessment/comprehensive-run/{run_id}")
    def status(run_id: str) -> dict[str, str]:
        return {"status": "running", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/continue")
    def continuation(run_id: str) -> dict[str, str]:
        return {"status": "running", "run_id": run_id}

    @app.get("/assessment/comprehensive-run/{run_id}/report/json")
    def report(run_id: str) -> dict[str, str]:
        return {"status": "draft", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/review")
    def review(run_id: str) -> dict[str, str]:
        return {"status": "approved", "run_id": run_id}

    install_specialist_access(app)
    return app


def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "test-signing-secret-with-at-least-thirty-two-bytes",
    )
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", SHA)


def test_exact_github_actions_claims_are_required(monkeypatch: pytest.MonkeyPatch):
    _environment(monkeypatch)
    accepted = validate_github_actions_claims(CLAIMS)
    assert accepted["sha"] == SHA
    assert accepted["workflow_ref"] == WORKFLOW_REF

    for field, wrong in (
        ("repository", "other/repo"),
        ("ref", "refs/heads/feature"),
        ("sha", "b" * 40),
        ("event_name", "pull_request"),
        ("workflow_ref", "BoneManTGRM/NICO/.github/workflows/other.yml@refs/heads/main"),
        ("run_id", "not-a-run"),
    ):
        candidate = {**CLAIMS, field: wrong}
        with pytest.raises(ValueError, match="github_actions_oidc_claim_mismatch"):
            validate_github_actions_claims(candidate)


def test_production_proof_session_can_scan_but_cannot_review(monkeypatch: pytest.MonkeyPatch):
    _environment(monkeypatch)
    token, _ = issue_specialist_session(
        {"authority": "github_actions_production_proof"},
        scope=PRODUCTION_PROOF_SCOPE,
        ttl_seconds=10_800,
        retained_claims=CLAIMS,
    )
    assert validate_specialist_session(token)["scope"] == PRODUCTION_PROOF_SCOPE
    client = TestClient(_app())
    headers = {"X-NICO-Operator-Session": token}

    assert client.post("/assessment/comprehensive-intake", headers=headers).status_code == 200
    assert client.get("/assessment/comprehensive-run/comprun_test", headers=headers).status_code == 200
    assert client.post("/assessment/comprehensive-run/comprun_test/continue", headers=headers).status_code == 200
    assert client.get("/assessment/comprehensive-run/comprun_test/report/json", headers=headers).status_code == 200

    forbidden = client.post("/assessment/comprehensive-run/comprun_test/review", headers=headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "production_proof_session_scope_forbidden"


def test_oidc_exchange_issues_only_restricted_session(monkeypatch: pytest.MonkeyPatch):
    _environment(monkeypatch)
    monkeypatch.setattr(
        "nico.specialist_access_v1.verify_github_actions_oidc_token",
        lambda _token: dict(CLAIMS),
    )
    client = TestClient(_app())
    response = client.post(
        GITHUB_ACTIONS_SESSION_ROUTE,
        headers={"Authorization": "Bearer cryptographically-verified-by-test-double"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == PRODUCTION_PROOF_SCOPE
    assert payload["release_sha"] == SHA
    assert payload["workflow_ref"] == WORKFLOW_REF
    session = validate_specialist_session(payload["session_token"])
    assert session is not None
    assert session["scope"] == PRODUCTION_PROOF_SCOPE
    assert session["sha"] == SHA
