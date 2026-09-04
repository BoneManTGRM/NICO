from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nico.github_actions_proof_auth_v1 import (
    FINALIZER_WORKFLOW_PATH,
    validate_github_actions_claims,
)
from nico.specialist_access_v1 import (
    GITHUB_ACTIONS_SESSION_ROUTE,
    PRODUCTION_PROOF_SCOPE,
    install_specialist_access,
    issue_specialist_session,
    validate_specialist_session,
)
from scripts.github_actions_nico_proof_auth_v1 import AuthenticatedBrowser


SHA = "a" * 40
WORKFLOW_REF = (
    "BoneManTGRM/NICO/.github/workflows/"
    "spanish-comprehensive-production-proof.yml@refs/heads/main"
)
FINALIZER_WORKFLOW_REF = f"BoneManTGRM/NICO/{FINALIZER_WORKFLOW_PATH}@refs/heads/main"
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
FINALIZER_CLAIMS = {
    **CLAIMS,
    "event_name": "workflow_run",
    "workflow_ref": FINALIZER_WORKFLOW_REF,
    "run_id": "33899900002",
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

    @app.post("/assessment/comprehensive-run/{run_id}/authorize-delivery")
    def authorize_delivery(run_id: str) -> dict[str, str]:
        return {"status": "authorized", "run_id": run_id}

    @app.get("/assessment/comprehensive-run/{run_id}/approved-delivery-package")
    def approved_delivery(run_id: str) -> dict[str, str]:
        return {"status": "client_final", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/automated-delivery-package")
    def automated_delivery(run_id: str) -> dict[str, str]:
        return {"status": "automated", "run_id": run_id}

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


def test_exact_workflow_run_finalizer_identity_is_allowed(monkeypatch: pytest.MonkeyPatch):
    _environment(monkeypatch)
    accepted = validate_github_actions_claims(FINALIZER_CLAIMS)
    assert accepted["workflow_ref"] == FINALIZER_WORKFLOW_REF
    assert accepted["event_name"] == "workflow_run"

    wrong_event = {**FINALIZER_CLAIMS, "event_name": "push"}
    with pytest.raises(ValueError, match="github_actions_oidc_claim_mismatch:event_name"):
        validate_github_actions_claims(wrong_event)

    wrong_subject = {**FINALIZER_CLAIMS, "sub": "repo:BoneManTGRM/NICO:environment:production"}
    with pytest.raises(ValueError, match="github_actions_oidc_claim_mismatch:sub"):
        validate_github_actions_claims(wrong_subject)


def test_production_proof_session_can_scan_but_cannot_approve_or_deliver(
    monkeypatch: pytest.MonkeyPatch,
):
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

    protected_actions = (
        ("post", "/assessment/comprehensive-run/comprun_test/review"),
        ("post", "/assessment/comprehensive-run/comprun_test/authorize-delivery"),
        ("get", "/assessment/comprehensive-run/comprun_test/approved-delivery-package"),
        ("post", "/assessment/comprehensive-run/comprun_test/automated-delivery-package"),
    )
    for method, path in protected_actions:
        forbidden = getattr(client, method)(path, headers=headers)
        assert forbidden.status_code == 403
        assert (
            forbidden.json()["detail"]["code"]
            == "production_proof_session_scope_forbidden"
        )


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


class _FakeContext:
    def __init__(self) -> None:
        self.cookies: list[dict[str, object]] = []

    def add_cookies(self, cookies):
        self.cookies.extend(cookies)


class _FakeBrowser:
    def __init__(self) -> None:
        self.kwargs = None
        self.context = _FakeContext()

    def new_context(self, *args, **kwargs):
        self.kwargs = kwargs
        return self.context


def test_browser_auth_is_cookie_scoped_and_never_global_header():
    raw = _FakeBrowser()
    wrapped = AuthenticatedBrowser(
        raw,
        session="scoped-session-token",
        frontend_url="https://app.nicoaudit.com",
    )
    wrapped.new_context(extra_http_headers={"Cache-Control": "no-store"})
    assert raw.kwargs == {"extra_http_headers": {"Cache-Control": "no-store"}}
    assert raw.context.cookies == [
        {
            "name": "nico-specialist-session",
            "value": "scoped-session-token",
            "url": "https://app.nicoaudit.com",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Strict",
        }
    ]
